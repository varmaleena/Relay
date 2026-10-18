"""Behavioral intake tests: isolation, replay, stale models, privacy, and durable jobs."""

import asyncio
import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from packages.intake.repository import MemoryRepository
from packages.intake.service import IntakeError, IntakeService, intake_history
from packages.intake.storage import LocalFileBlobStore
from packages.safety import Actor
from packages.schemas import EvidenceExtraction
from services.api.contracts import MessageRequest


class TextAgent:
    def __init__(self):
        self.calls = 0
        self.delta = {"payment": {"method": "upi"}}

    async def respond(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            text="Contact your bank using its official app.", facts_delta=self.delta, distress=False
        )


class EvidenceAgent:
    def __init__(self):
        self.calls = 0

    async def extract(self, **kwargs):
        self.calls += 1
        return EvidenceExtraction(
            evidenceId=kwargs["evidence_id"],
            documentType="payment_screenshot",
            entities=[
                {
                    "entityId": "e1",
                    "type": "upi_id",
                    "rawValue": "test@fakebank",
                    "normalizedValue": "test@fakebank",
                    "role": "scammer",
                    "confidence": 0.9,
                }
            ],
            summary="Synthetic payment evidence",
            confidence=0.9,
            model="fixture-model",
            promptVersion="evidence.v1",
        )


@pytest.fixture
def setup(tmp_path):
    repo = MemoryRepository()
    blobs = LocalFileBlobStore(tmp_path, "http://127.0.0.1:8000", b"t" * 32)
    text, evidence = TextAgent(), EvidenceAgent()
    clock = [datetime(2026, 10, 14, tzinfo=UTC)]
    service = IntakeService(repo, blobs, text, evidence, clock=lambda: clock[0])
    actor = Actor("synthetic-victim", "victim")
    case = service.create_case(actor, {"language": "en", "consentVersion": "1.0"}, str(uuid4()))
    return service, repo, blobs, text, evidence, actor, case["caseId"], clock


@pytest.mark.parametrize("expired", [False, True])
def test_orphan_or_expired_evidence_job_is_terminal_without_model_call(setup, expired):
    service, repo, _, _, evidence, actor, case_id, clock = setup
    if expired:
        clock[0] += timedelta(days=4)
    else:
        repo.delete(f"cases/{case_id}")
    repo.set(
        "jobs/job_orphan",
        {
            "jobId": "job_orphan",
            "caseId": case_id,
            "uid": actor.uid,
            "evidenceId": "ev_missing",
            "type": "process_evidence",
            "state": "queued",
        },
    )
    asyncio.run(service.process_evidence("job_orphan"))
    assert repo.get("jobs/job_orphan")["state"] == "failed"
    assert evidence.calls == 0


def test_creation_consent_idempotency_and_cross_owner(setup):
    service, repo, _, _, _, actor, case_id, _ = setup
    key = str(uuid4())
    body = {"language": "hi", "consentVersion": "1.0"}
    assert service.create_case(actor, body, key) == service.create_case(actor, body, key)
    with pytest.raises(IntakeError) as conflict:
        service.create_case(actor, {**body, "language": "en"}, key)
    assert conflict.value.code == "idempotency_conflict"
    with pytest.raises(IntakeError) as missing_consent:
        service.create_case(actor, {**body, "consentVersion": "old"}, str(uuid4()))
    assert missing_consent.value.code == "consent_required"
    for stranger in [Actor("another-victim", "victim"), Actor("receiver", "receiver", "org")]:
        with pytest.raises(IntakeError) as denied:
            service.get_case(stranger, case_id)
        assert denied.value.status == 403
    assert service.get_case(Actor("admin", "admin"), case_id)["caseId"] == case_id
    assert len([path for path in repo.documents if "/events/" in path]) == 2


def test_confirmed_fact_cannot_be_overwritten_by_model_and_retry_is_one_turn(setup):
    service, repo, _, text, _, actor, case_id, _ = setup
    service.update_facts(
        actor,
        case_id,
        {"facts": {"payment": {"method": "card"}}, "source": "confirmed", "ifRevision": 0},
    )
    key = str(uuid4())

    async def run():
        first = await service.message(actor, case_id, {"text": "A synthetic scam"}, key)
        repeated = await service.message(actor, case_id, {"text": "A synthetic scam"}, key)
        assert first == repeated

    asyncio.run(run())
    case = service.get_case(actor, case_id)
    assert case["facts"]["payment"]["method"] == "card"
    assert len(case["transcript"]) == 2 and text.calls == 1
    assert all("pin" not in item["text"].lower() for item in case["transcript"])
    assert len([path for path in repo.documents if "/transcript/" in path]) == 2


def test_model_inflight_edit_rejects_stale_commit(setup):
    service, _, _, agent, _, actor, case_id, _ = setup

    async def respond(**kwargs):
        service.update_facts(
            actor,
            case_id,
            {"facts": {"victimBank": "Synthetic Bank"}, "source": "confirmed", "ifRevision": 0},
        )
        return SimpleNamespace(
            text="A safe reply", facts_delta={"victimBank": "Wrong Bank"}, distress=False
        )

    agent.respond = respond
    with pytest.raises(IntakeError) as stale:
        asyncio.run(service.message(actor, case_id, {"text": "Synthetic input"}, str(uuid4())))
    assert stale.value.code == "version_conflict"
    assert service.get_case(actor, case_id)["facts"]["victimBank"] == "Synthetic Bank"


def test_volunteered_secret_is_scrubbed_before_transcript_and_durable_cache(setup):
    service, repo, _, _, _, actor, case_id, _ = setup
    asyncio.run(service.message(actor, case_id, {"text": "My OTP is 123456"}, str(uuid4())))
    serialized = repr(repo.documents)
    assert "123456" not in serialized
    assert "[REDACTED]" in service.get_case(actor, case_id)["transcript"][0]["text"]


def test_evidence_lifecycle_confirmation_and_delete_cascade(setup):
    from PIL import Image

    service, repo, blobs, _, evidence_agent, actor, case_id, _ = setup
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(buffer, format="PNG")
    raw = buffer.getvalue()
    uploaded = service.request_upload(
        actor,
        case_id,
        {"kind": "screenshot", "mime": "image/png", "sizeBytes": len(raw)},
        str(uuid4()),
    )
    evidence_id = uploaded["evidenceId"]
    path = f"quarantine/{case_id}/{evidence_id}"
    blobs.write(path, raw, "image/png")
    key = str(uuid4())
    job = service.finalize_upload(actor, case_id, evidence_id, key)
    asyncio.run(service.process_evidence(job["jobId"]))
    assert service.get_job(actor, job["jobId"])["state"] == "succeeded"
    assert service.finalize_upload(actor, case_id, evidence_id, key) == job
    asyncio.run(service.process_evidence(job["jobId"]))
    assert evidence_agent.calls == 1
    result = service.confirm_evidence(
        actor,
        case_id,
        evidence_id,
        {"items": [{"entityId": "e1", "decision": "confirm"}]},
        str(uuid4()),
    )
    assert result["entities"][0]["status"] == "confirmed"
    assert (
        service.get_case(actor, case_id)["facts"]["payment"]["recipientIdentifier"]["value"]
        == "test@fakebank"
    )
    service.confirm_evidence(
        actor,
        case_id,
        evidence_id,
        {"items": [{"entityId": "e1", "decision": "unrelated"}]},
        str(uuid4()),
    )
    assert service.get_case(actor, case_id)["facts"]["payment"]["recipientIdentifier"] is None
    assert not blobs.path(path).exists()
    service.delete_case(actor, case_id)
    assert not any(path.startswith(f"cases/{case_id}") for path in repo.documents)
    assert not any(path.startswith("idempotency/") for path in repo.documents)
    assert not blobs.path(f"validated/{case_id}/{evidence_id}").exists()
    assert len([path for path in repo.documents if path.startswith("deletionAudit/")]) == 1


def test_invalid_file_and_credential_file_never_promoted(setup):
    service, _, blobs, _, _, actor, case_id, _ = setup
    raw = b"My password is synthetic-secret"
    upload = service.request_upload(
        actor,
        case_id,
        {"kind": "chat_export", "mime": "text/plain", "sizeBytes": len(raw)},
        str(uuid4()),
    )
    path = f"quarantine/{case_id}/{upload['evidenceId']}"
    blobs.write(path, raw, "text/plain")
    with pytest.raises(IntakeError) as unsafe:
        service.finalize_upload(actor, case_id, upload["evidenceId"], str(uuid4()))
    assert unsafe.value.status == 422
    assert service.get_evidence(actor, case_id, upload["evidenceId"])["previewUrl"] == ""
    assert not blobs.path(path).exists()


def test_ttl_and_rate_limits_are_enforced(setup):
    service, _, _, _, _, actor, case_id, clock = setup
    for _ in range(30):
        service.rate_limit(actor)
    with pytest.raises(IntakeError) as rate:
        service.rate_limit(actor)
    assert rate.value.status == 429
    clock[0] += timedelta(hours=73)
    with pytest.raises(IntakeError) as expired:
        service.get_case(actor, case_id)
    assert expired.value.status == 404


def test_model_safety_failure_is_permanent_and_removes_quarantine(setup):
    from agents.intake.clients import ModelFailure

    service, _, blobs, _, agent, actor, case_id, _ = setup
    raw = b"Synthetic test receipt"
    upload = service.request_upload(
        actor,
        case_id,
        {"kind": "chat_export", "mime": "text/plain", "sizeBytes": len(raw)},
        str(uuid4()),
    )
    quarantine = f"quarantine/{case_id}/{upload['evidenceId']}"
    blobs.write(quarantine, raw, "text/plain")
    job = service.finalize_upload(actor, case_id, upload["evidenceId"], str(uuid4()))

    async def unsafe(**kwargs):
        raise ModelFailure("evidence_secret_rejected")

    agent.extract = unsafe
    asyncio.run(service.process_evidence(job["jobId"]))
    assert service.get_job(actor, job["jobId"])["state"] == "failed"
    assert not blobs.path(quarantine).exists()


def test_transient_model_failure_retries_without_losing_job_or_upload(setup):
    service, _, blobs, _, agent, actor, case_id, clock = setup
    raw = b"Synthetic test receipt"
    upload = service.request_upload(
        actor,
        case_id,
        {"kind": "chat_export", "mime": "text/plain", "sizeBytes": len(raw)},
        str(uuid4()),
    )
    quarantine = f"quarantine/{case_id}/{upload['evidenceId']}"
    blobs.write(quarantine, raw, "text/plain")
    job = service.finalize_upload(actor, case_id, upload["evidenceId"], str(uuid4()))
    good = agent.extract

    async def fail_once(**kwargs):
        raise RuntimeError("temporary_provider_failure")

    agent.extract = fail_once
    asyncio.run(service.process_evidence(job["jobId"]))
    assert service.get_job(actor, job["jobId"])["state"] == "queued"
    assert blobs.path(quarantine).exists()
    agent.extract = good
    clock[0] += timedelta(seconds=10)
    asyncio.run(service.process_evidence(job["jobId"]))
    assert service.get_job(actor, job["jobId"])["state"] == "succeeded"
    assert not blobs.path(quarantine).exists()


def test_multiturn_omitted_money_recovers_from_prior_statement_without_retiming(setup):
    service, _, _, agent, _, actor, case_id, clock = setup
    calls = []
    statement = "I sent 45000 to demo@fakebank 20 minutes ago."

    async def respond(**kwargs):
        calls.append(kwargs)
        delta = {"payment": {"method": "upi"}}
        if kwargs["text"] == "INR":
            prior = kwargs["history"]
            assert prior == [{"text": statement, "at": "2026-10-14T00:00:00Z"}]
            original_time = datetime.fromisoformat(prior[0]["at"].replace("Z", "+00:00"))
            delta["payment"].update(
                amount={"value": "45000", "currency": "INR"},
                recipientIdentifier={"type": "upi_id", "value": "demo@fakebank"},
                timestamp=(original_time - timedelta(minutes=20)).isoformat(),
            )
        else:
            # Provider latency must not shift the reporting time used to resolve
            # "20 minutes ago" on the next conversational turn.
            clock[0] += timedelta(seconds=15)
        return SimpleNamespace(text="A safe reply.", facts_delta=delta, distress=False)

    agent.respond = respond

    async def run():
        first = await service.message(actor, case_id, {"text": statement}, str(uuid4()))
        assert first["factsDelta"]["payment"]["amount"] is None
        clock[0] += timedelta(hours=1)
        key = str(uuid4())
        second = await service.message(actor, case_id, {"text": "INR"}, key)
        assert second["factsDelta"]["payment"]["amount"] == {"value": "45000", "currency": "INR"}
        assert second["factsDelta"]["payment"]["timestamp"] == "2026-10-13T23:40:00Z"
        assert second["factsDelta"]["payment"]["recipientIdentifier"]["value"] == "demo@fakebank"
        assert await service.message(actor, case_id, {"text": "INR"}, key) == second

    asyncio.run(run())
    assert len(calls) == 2


def test_history_helper_bounds_scope_credentials_and_excludes_assistant_content():
    actor = Actor("owner", "victim")
    case = {"victimUid": "owner", "transcript": []}
    for number in range(8):
        case["transcript"] += [
            {"role": "user", "text": f"Statement {number}", "ts": f"original-{number}"},
            {"role": "assistant", "text": "Invented amount 999999", "ts": "assistant-time"},
        ]
    case["transcript"][-2]["text"] = "My OTP is 123456"
    history = intake_history(case, actor)
    assert len(history) == 6 and history[0]["at"] == "original-2"
    assert "123456" not in repr(history) and "Invented" not in repr(history)
    assert history[-1]["at"] == "original-7"
    case["transcript"] = [{"role": "user", "text": "x" * 4000, "ts": str(n)} for n in range(8)]
    history = intake_history(case, actor)
    assert len(history) == 4 and sum(len(item["text"]) for item in history) == 16000
    assert [item["at"] for item in history] == ["4", "5", "6", "7"]
    with pytest.raises(IntakeError) as denied:
        intake_history(case, Actor("other-case-victim", "victim"))
    assert denied.value.code == "forbidden"


def test_history_does_not_override_confirmed_manual_money(setup):
    service, _, _, agent, _, actor, case_id, _ = setup
    service.update_facts(
        actor,
        case_id,
        {
            "facts": {"payment": {"amount": {"value": "123", "currency": "GBP"}}},
            "source": "confirmed",
            "ifRevision": 0,
        },
    )

    async def reply(**kwargs):
        return SimpleNamespace(
            text="A safe reply",
            facts_delta={"payment": {"amount": {"value": "45000", "currency": "INR"}}},
            distress=False,
        )

    agent.respond = reply
    asyncio.run(service.message(actor, case_id, {"text": "INR"}, str(uuid4())))
    assert service.get_case(actor, case_id)["facts"]["payment"]["amount"] == {
        "value": "123",
        "currency": "GBP",
    }


def test_history_is_not_a_client_message_contract_field():
    with pytest.raises(ValidationError):
        MessageRequest.model_validate(
            {
                "text": "INR",
                "history": [
                    {"text": "Another case's fabricated payment", "at": "2026-10-14T00:00:00Z"}
                ],
            }
        )
