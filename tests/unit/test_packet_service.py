"""Packet mutation and approval boundaries; synthetic content, actual ADK/MCP."""

import asyncio
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml

from agents.packets import PacketBuildResult
from agents.workflows.planning import PlanningWorkflow
from packages.delivery import MockDeliveryService
from packages.delivery.adapter import LocalMCPDeliveryAdapter
from packages.intake.repository import MemoryRepository
from packages.intake.service import IntakeError, IntakeService
from packages.intake.storage import LocalFileBlobStore
from packages.packets.service import PacketService
from packages.packs.registry import PackRegistry
from packages.planning.service import PlanningService
from packages.safety import Actor
from packages.schemas.models import PacketContent, PacketField, Provenance, VerificationCheck
from tests.unit.test_planning_service import SyntheticClassifier

ROOT = Path(__file__).resolve().parents[2]


class SyntheticPipeline:
    def __init__(self):
        self.calls = 0
        self.before = None
        self.block = False
        self.verifier = self

    async def verify(self, content, **context):
        return [
            VerificationCheck(
                id="synthetic",
                type="deterministic",
                passed=not self.block,
                detail="Synthetic verifier fixture.",
                severity="blocker",
            )
        ]

    async def build(self, **context):
        self.calls += 1
        if self.before:
            self.before()
        fields = [
            PacketField(
                key=name,
                label=name,
                value="SYNTHETIC-" + name,
                required=True,
                provenance=Provenance(source="confirmed"),
            )
            for name in context["recipient"].required_fields
        ]
        content = PacketContent(
            language="en",
            recipient_language="en",
            subject="Synthetic report",
            summary="Synthetic approved facts.",
            fields=fields,
            message="Please review this synthetic incident.",
            requested_actions=["Review this report"],
            citations=[],
            attachments=[],
            victim_copy={"lang": "en", "text": "Synthetic copy"},
            footer="Simulated; no recovery guarantee.",
            completeness={"score": 1.0},
        )
        return PacketBuildResult(
            content=content,
            checks=await self.verify(content),
            attempts=1,
            status="NEEDS_HUMAN_REVIEW" if self.block else "VERIFIED",
            model="synthetic-no-provider",
        )


class ObservedAdapter:
    def __init__(self, actual):
        self.actual, self.calls = actual, 0
        self.fail_before = self.fail_after = False
        self.before = self.after = None

    async def deliver(self, projection, key):
        self.calls += 1
        if self.before:
            self.before()
        if self.fail_before:
            raise OSError("Synthetic adapter unavailable")
        result = await self.actual.deliver(projection, key)
        if self.after:
            self.after()
        if self.fail_after:
            raise OSError("Synthetic API crash after durable mock receipt")
        return result


def make_packet_context(tmp_path, repository=None):
    repository = repository or MemoryRepository()
    clock = [datetime.now(UTC)]
    shutil.copytree(ROOT / "packs", tmp_path / "packs")
    shutil.copytree(ROOT / "docs/pack-sources", tmp_path / "docs/pack-sources")
    registry = PackRegistry(tmp_path / "packs")
    storage = LocalFileBlobStore(tmp_path / "blobs", "http://127.0.0.1:8000", b"p" * 32)
    intake = IntakeService(repository, storage, None, None, clock=lambda: clock[0])
    actor = Actor("synthetic-packets-" + uuid4().hex, "victim")
    case_id = intake.create_case(actor, {"language": "en", "consentVersion": "1.0"}, str(uuid4()))[
        "caseId"
    ]
    intake.update_facts(
        actor,
        case_id,
        {
            "facts": {
                "country": {"value": "IN", "provenance": {"source": "confirmed"}},
                "payment": {
                    "method": "upi",
                    "amount": {"value": "45000", "currency": "INR"},
                    "timestamp": (clock[0] - timedelta(minutes=20)).isoformat(),
                    "authorizedByVictim": True,
                },
                "contact": {"channel": "phone", "claimedIdentity": "bank"},
                "ongoingContact": False,
            }
        },
    )
    planning = PlanningService(
        intake, PlanningWorkflow(SyntheticClassifier(), registry, allow_draft_preview=True)
    )
    intake.planning = planning
    job = planning.enqueue(actor, case_id, {"previewDraft": True})
    asyncio.run(planning.process_case(job["jobId"]))
    mock = MockDeliveryService(
        repository,
        registry,
        allow_draft_preview=True,
        environment="local",
        demo_mode=True,
        clock=lambda: clock[0],
    )
    adapter = ObservedAdapter(LocalMCPDeliveryAdapter(mock))
    pipeline = SyntheticPipeline()
    packets = PacketService(intake, pipeline, adapter)
    intake.packets = packets
    return SimpleNamespace(
        intake=intake,
        planning=planning,
        repository=repository,
        actor=actor,
        case_id=case_id,
        packets=packets,
        pipeline=pipeline,
        adapter=adapter,
        mock=mock,
        registry=registry,
        clock=clock,
    )


@pytest.fixture
def setup(tmp_path):
    return make_packet_context(tmp_path)


def generate(context):
    plan = context.planning.get_plan(context.actor, context.case_id)
    body = {"planId": plan["planId"]}
    accepted = context.packets.generate(context.actor, context.case_id, body, str(uuid4()))
    asyncio.run(context.packets.process(accepted["jobId"]))
    case = context.repository.get(f"cases/{context.case_id}")
    assert case["packetIds"], context.repository.get(f"jobs/{accepted['jobId']}")
    return context.packets.get(context.actor, context.case_id, case["packetIds"][0])


def approval(packet):
    return {
        "packetVersion": packet["version"],
        "confirm": True,
        "confirmedRecipientId": packet["recipientId"],
    }


def test_generation_replay_edit_retains_immutable_content_and_requires_reverification(setup):
    c = setup
    plan = c.planning.get_plan(c.actor, c.case_id)
    body, key = {"planId": plan["planId"]}, str(uuid4())
    job = c.packets.generate(c.actor, c.case_id, body, key)
    assert c.packets.generate(c.actor, c.case_id, body, key) == job
    asyncio.run(c.packets.process(job["jobId"]))
    asyncio.run(c.packets.process(job["jobId"]))
    assert c.pipeline.calls == 3
    packet = c.packets.list(c.actor, c.case_id)["items"][0]
    original = c.packets.get(c.actor, c.case_id, packet["packetId"])
    edited = c.packets.edit(
        c.actor, c.case_id, packet["packetId"], {"ifVersion": 1, "message": "Synthetic correction."}
    )
    assert edited["version"] == 2 and edited["status"] == "DRAFT"
    path = f"cases/{c.case_id}/packets/{packet['packetId']}/versions/1"
    assert c.repository.get(path)["content"] == original["content"]
    with pytest.raises(IntakeError):
        asyncio.run(c.packets.approve(c.actor, c.case_id, packet["packetId"], approval(original)))
    asyncio.run(c.packets.process(edited["jobId"]))
    current = c.packets.get(c.actor, c.case_id, packet["packetId"])
    assert current["status"] == "VERIFIED" and current["version"] == 2
    assert c.adapter.calls == 0


def test_owner_and_verification_and_recipient_approval_gates_precede_adapter(setup):
    c = setup
    packet = generate(c)
    for actor, body in [
        (Actor("other", "victim"), approval(packet)),
        (c.actor, approval(packet) | {"confirm": False}),
        (c.actor, approval(packet) | {"confirmedRecipientId": "different"}),
    ]:
        with pytest.raises(IntakeError):
            asyncio.run(c.packets.approve(actor, c.case_id, packet["packetId"], body))
    c.pipeline.block = True
    edited = c.packets.edit(
        c.actor, c.case_id, packet["packetId"], {"ifVersion": 1, "message": "Edited"}
    )
    asyncio.run(c.packets.process(edited["jobId"]))
    packet = c.packets.get(c.actor, c.case_id, packet["packetId"])
    assert packet["status"] == "NEEDS_HUMAN_REVIEW"
    with pytest.raises(IntakeError):
        asyncio.run(c.packets.approve(c.actor, c.case_id, packet["packetId"], approval(packet)))
    assert c.adapter.calls == 0


def test_send_is_explicit_version_bound_and_duplicate_approval_replays_mcp_receipt(setup):
    c = setup
    packet = generate(c)
    first = asyncio.run(c.packets.approve(c.actor, c.case_id, packet["packetId"], approval(packet)))
    assert first["delivery"]["simulated"] and first["delivery"]["ticketRef"].startswith("SIM-")
    assert c.adapter.calls == 1
    assert (
        asyncio.run(c.packets.approve(c.actor, c.case_id, packet["packetId"], approval(packet)))
        == first
    )
    assert c.adapter.calls == 1
    assert len([p for p in c.repository.documents if p.startswith("mockDeliveries/")]) == 1


@pytest.mark.parametrize("change", ["source", "catalog"])
def test_source_or_catalog_change_blocks_generation_and_send(setup, change):
    c = setup
    packet = generate(c)
    if change == "source":
        c.intake.update_facts(
            c.actor, c.case_id, {"facts": {"victimBank": "Synthetic changed bank"}}
        )
    else:
        path = c.registry.root / "india-cyber-rail.yaml"
        pack = yaml.safe_load(path.read_text(encoding="utf-8"))
        pack["disclaimers"].append("Synthetic changed catalog")
        path.write_text(yaml.safe_dump(pack, allow_unicode=True), encoding="utf-8")
    assert c.packets.get(c.actor, c.case_id, packet["packetId"])["stale"]
    with pytest.raises(IntakeError):
        asyncio.run(c.packets.approve(c.actor, c.case_id, packet["packetId"], approval(packet)))
    assert c.adapter.calls == 0


def test_source_changes_during_generation_cannot_commit_packets(setup):
    c = setup
    c.pipeline.before = lambda: c.intake.update_facts(
        c.actor, c.case_id, {"facts": {"victimBank": "Synthetic new source"}}
    )
    plan = c.planning.get_plan(c.actor, c.case_id)
    job = c.packets.generate(c.actor, c.case_id, {"planId": plan["planId"]}, str(uuid4()))
    asyncio.run(c.packets.process(job["jobId"]))
    assert c.intake.get_job(c.actor, job["jobId"])["state"] == "failed"
    assert not c.repository.get(f"cases/{c.case_id}").get("packetIds")


def test_replaced_claim_token_cannot_commit_an_old_workers_packet_batch(setup):
    c = setup
    plan = c.planning.get_plan(c.actor, c.case_id)
    job = c.packets.generate(c.actor, c.case_id, {"planId": plan["planId"]}, str(uuid4()))

    def replace_claim():
        record = c.repository.get(f"jobs/{job['jobId']}")
        record["claimToken"] = "synthetic-new-worker-claim"
        c.repository.set(f"jobs/{job['jobId']}", record)

    c.pipeline.before = replace_claim
    asyncio.run(c.packets.process(job["jobId"]))
    assert not c.repository.get(f"cases/{c.case_id}").get("packetIds")
    assert c.repository.get(f"jobs/{job['jobId']}")["claimToken"] == "synthetic-new-worker-claim"


def test_catalog_change_in_final_writer_call_cannot_commit_old_pack_content(setup):
    c = setup

    def change_last():
        if c.pipeline.calls == 3:
            path = c.registry.root / "india-cyber-rail.yaml"
            pack = yaml.safe_load(path.read_text(encoding="utf-8"))
            pack["disclaimers"].append("Synthetic changed after final context read")
            path.write_text(yaml.safe_dump(pack, allow_unicode=True), encoding="utf-8")

    c.pipeline.before = change_last
    plan = c.planning.get_plan(c.actor, c.case_id)
    job = c.packets.generate(c.actor, c.case_id, {"planId": plan["planId"]}, str(uuid4()))
    asyncio.run(c.packets.process(job["jobId"]))
    assert c.intake.get_job(c.actor, job["jobId"])["state"] == "failed"
    # Earlier valid checkpoints survive, but become stale and cannot be approved.
    retained = c.repository.get(f"cases/{c.case_id}")["packetIds"]
    assert len(retained) == 2
    for packet_id in retained:
        packet = c.packets.get(c.actor, c.case_id, packet_id)
        assert packet["stale"]
        with pytest.raises(IntakeError):
            asyncio.run(c.packets.approve(c.actor, c.case_id, packet_id, approval(packet)))


def test_outbox_recovers_receipt_after_postdelivery_crash_with_stable_projection(setup):
    c = setup
    packet = generate(c)
    c.adapter.fail_after = True
    with pytest.raises(IntakeError):
        asyncio.run(c.packets.approve(c.actor, c.case_id, packet["packetId"], approval(packet)))
    c.adapter.fail_after = False
    outbox = c.repository.get(f"cases/{c.case_id}/packets/{packet['packetId']}")["deliveryPending"]
    assert len([p for p in c.repository.documents if p.startswith("mockDeliveries/")]) == 1
    c.clock[0] += timedelta(minutes=2)
    restarted = PacketService(c.intake, c.pipeline, c.adapter)
    asyncio.run(restarted.process_delivery(outbox))
    current = restarted.get(c.actor, c.case_id, packet["packetId"])
    assert current["status"] == "SENT" and current["delivery"]["simulated"]
    assert len([p for p in c.repository.documents if p.startswith("mockDeliveries/")]) == 1


def test_outbox_backoff_blocks_immediate_repeated_approval(setup):
    c = setup
    packet = generate(c)
    c.adapter.fail_before = True
    for _ in range(2):
        with pytest.raises(IntakeError):
            asyncio.run(c.packets.approve(c.actor, c.case_id, packet["packetId"], approval(packet)))
    assert c.adapter.calls == 1


def test_expired_approval_cannot_send_a_previously_queued_outbox(setup):
    c = setup
    packet = generate(c)
    c.adapter.fail_before = True
    with pytest.raises(IntakeError):
        asyncio.run(c.packets.approve(c.actor, c.case_id, packet["packetId"], approval(packet)))
    pending = c.repository.get(f"cases/{c.case_id}/packets/{packet['packetId']}")["deliveryPending"]
    c.adapter.fail_before = False
    c.clock[0] += timedelta(minutes=11)
    asyncio.run(c.packets.process_delivery(pending))
    assert c.adapter.calls == 1
    assert c.repository.get(f"jobs/{pending}")["state"] == "failed"
    assert not any(path.startswith("mockDeliveries/") for path in c.repository.documents)


def test_delete_between_claim_and_mock_commit_cannot_leave_receiver_record(setup):
    c = setup
    packet = generate(c)
    c.adapter.before = lambda: c.intake.delete_case(c.actor, c.case_id)
    with pytest.raises(IntakeError):
        asyncio.run(c.packets.approve(c.actor, c.case_id, packet["packetId"], approval(packet)))
    assert not any(p.startswith("mockDeliveries/") for p in c.repository.documents)
    assert not any(p.startswith(f"cases/{c.case_id}") for p in c.repository.documents)


def test_checking_one_message_does_not_mark_other_blocked_messages_verified(setup):
    c = setup
    generate(c)
    case = c.repository.get(f"cases/{c.case_id}")
    first_id, second_id = case["packetIds"][:2]
    first_path = f"cases/{c.case_id}/packets/{first_id}"
    blocked = c.repository.get(first_path)
    blocked["status"] = "NEEDS_HUMAN_REVIEW"
    blocked["verification"]["passed"] = False
    c.repository.set(first_path, blocked)
    second = c.packets.get(c.actor, c.case_id, second_id)
    edited = c.packets.edit(
        c.actor,
        c.case_id,
        second_id,
        {"ifVersion": second["version"], "message": "Please review this synthetic incident."},
    )
    assert c.repository.get(f"cases/{c.case_id}")["status"] == "PLAN_READY"
    asyncio.run(c.packets.process(edited["jobId"]))
    assert c.packets.get(c.actor, c.case_id, second_id)["status"] == "VERIFIED"
    assert c.repository.get(f"cases/{c.case_id}")["status"] == "PLAN_READY"


class RecipientFailures(SyntheticPipeline):
    def __init__(self, failing):
        super().__init__()
        self.failing = set(failing)
        self.recipients = []
        self.cancel_on = None

    async def build(self, **context):
        recipient_id = context["recipient"].id
        self.recipients.append(recipient_id)
        if recipient_id == self.cancel_on:
            raise asyncio.CancelledError()
        if recipient_id in self.failing:
            return PacketBuildResult(None, [], 1, "NEEDS_HUMAN_REVIEW", "synthetic-no-provider")
        return await super().build(**context)


def queue_generation(c):
    plan = c.planning.get_plan(c.actor, c.case_id)
    return c.packets.generate(c.actor, c.case_id, {"planId": plan["planId"]}, str(uuid4()))


@pytest.mark.parametrize("failed_recipient", ["bank", "cyber", "payment-app"])
def test_partial_progress_survives_and_retry_only_builds_missing_recipient(setup, failed_recipient):
    c = setup
    pipeline = RecipientFailures([failed_recipient])
    c.packets.pipeline = pipeline
    first = queue_generation(c)
    asyncio.run(c.packets.process(first["jobId"]))
    job = c.repository.get(f"jobs/{first['jobId']}")
    assert pipeline.recipients == ["bank", "cyber", "payment-app"]
    assert job["state"] == "failed" and job["progress"] == {"step": 2, "total": 3}
    assert job["recipientFailures"] == {failed_recipient: "model_unavailable"}
    case = c.repository.get(f"cases/{c.case_id}")
    assert case["status"] == "PLAN_READY" and len(case["packetIds"]) == 2
    originals = {p: c.repository.get(f"cases/{c.case_id}/packets/{p}") for p in case["packetIds"]}
    notification_count = len(case["notificationIds"])
    pipeline.failing.clear()
    second = queue_generation(c)
    asyncio.run(c.packets.process(second["jobId"]))
    assert pipeline.recipients == ["bank", "cyber", "payment-app", failed_recipient]
    assert c.repository.get(f"jobs/{second['jobId']}")["state"] == "succeeded"
    case = c.repository.get(f"cases/{c.case_id}")
    assert len(case["packetIds"]) == 3 and case["status"] == "PACKETS_VERIFIED"
    assert len(case["notificationIds"]) == notification_count + 1
    for packet_id, original in originals.items():
        assert c.repository.get(f"cases/{c.case_id}/packets/{packet_id}") == original
    for packet_id in case["packetIds"]:
        versions = [
            p
            for p in c.repository.documents
            if p.startswith(f"cases/{c.case_id}/packets/{packet_id}/versions/")
        ]
        assert len(versions) == 1
    assert c.adapter.calls == 0


def test_expired_worker_restart_resumes_durable_checkpoint(setup):
    c = setup
    pipeline = RecipientFailures([])
    pipeline.cancel_on = "cyber"
    c.packets.pipeline = pipeline
    first = queue_generation(c)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(c.packets.process(first["jobId"]))
    retained = c.repository.get(f"cases/{c.case_id}")["packetIds"]
    assert len(retained) == 1
    pipeline.cancel_on = None
    c.clock[0] += timedelta(minutes=11)
    asyncio.run(PacketService(c.intake, pipeline, c.adapter).process(first["jobId"]))
    assert pipeline.recipients == ["bank", "cyber", "cyber", "payment-app"]
    assert c.repository.get(f"jobs/{first['jobId']}")["state"] == "succeeded"
    assert len(c.repository.get(f"cases/{c.case_id}")["packetIds"]) == 3


@pytest.mark.parametrize("change", ["version", "content", "catalog", "facts"])
def test_partial_checkpoint_never_reused_after_proof_changes(setup, change):
    c = setup
    pipeline = RecipientFailures(["cyber"])
    c.packets.pipeline = pipeline
    first = queue_generation(c)
    asyncio.run(c.packets.process(first["jobId"]))
    case = c.repository.get(f"cases/{c.case_id}")
    packet_id = case["packetIds"][0]
    if change == "version":
        c.packets.edit(
            c.actor, c.case_id, packet_id, {"ifVersion": 1, "message": "Synthetic user edit."}
        )
    elif change == "content":
        packet = c.repository.get(f"cases/{c.case_id}/packets/{packet_id}")
        packet["content"]["message"] = "Unbound changed content."
        c.repository.atomic(lambda tx: tx.set(f"cases/{c.case_id}/packets/{packet_id}", packet))
    elif change == "catalog":
        path = c.registry.root / "india-cyber-rail.yaml"
        pack = yaml.safe_load(path.read_text(encoding="utf-8"))
        pack["disclaimers"].append("Synthetic source changed")
        path.write_text(yaml.safe_dump(pack), encoding="utf-8")
    else:
        c.intake.update_facts(
            c.actor, c.case_id, {"facts": {"victimBank": "Changed synthetic bank"}}
        )
    before = len(pipeline.recipients)
    if change in {"catalog", "facts"}:
        with pytest.raises(IntakeError):
            queue_generation(c)
    else:
        second = queue_generation(c)
        asyncio.run(c.packets.process(second["jobId"]))
        assert c.repository.get(f"jobs/{second['jobId']}")["state"] == "failed"
    assert len(pipeline.recipients) == before
    assert c.adapter.calls == 0


def test_delete_during_later_recipient_removes_checkpoint_and_never_recreates_case(setup):
    c = setup

    def remove_case():
        if c.pipeline.calls == 2:
            c.intake.delete_case(c.actor, c.case_id)

    c.pipeline.before = remove_case
    first = queue_generation(c)
    asyncio.run(c.packets.process(first["jobId"]))
    assert not any(p.startswith(f"cases/{c.case_id}") for p in c.repository.documents)
    assert not any(
        j.get("caseId") == c.case_id
        for p, j in c.repository.documents.items()
        if p.startswith("jobs/")
    )


def test_pdf_uses_export_storage_and_keeps_version_bound_local_capability(setup, tmp_path):
    c = setup
    packet = generate(c)
    exports = LocalFileBlobStore(tmp_path / "exports", "http://127.0.0.1:8000", b"e" * 32)
    c.intake.export_storage = exports
    result = c.packets.pdf(c.actor, c.case_id, packet["packetId"])
    token = result["downloadUrl"].rsplit("/", 1)[-1]
    key = f"packets/{c.case_id}/{packet['packetId']}/1.pdf"
    assert exports.path(key).is_file()
    assert not c.intake.storage.path(key).exists()
    assert c.packets.pdf_bytes(token).startswith(b"%PDF-")
    c.packets.edit(
        c.actor,
        c.case_id,
        packet["packetId"],
        {"ifVersion": 1, "message": "Synthetic edited draft."},
    )
    with pytest.raises(IntakeError):
        c.packets.pdf_bytes(token)
    c.intake.delete_case(c.actor, c.case_id)
    assert not exports.path(key).exists()


def test_packet_context_anchors_real_confirmed_leaf_origins_without_rewriting_case(setup):
    c = setup
    case = c.repository.get(f"cases/{c.case_id}")
    original = case["facts"]["fieldProvenance"]
    assert original["payment.timestamp"]["reference"] is None
    plan = c.planning.get_plan(c.actor, c.case_id)
    context = c.packets._context(case, plan, "bank")
    origins = context["facts"].field_provenance
    for key in ["payment.timestamp", "payment.method", "payment.amount"]:
        assert origins[key].source == "confirmed"
        assert origins[key].reference == f"case:{c.case_id}:facts:{case['factsRevision']}:{key}"
    assert c.repository.get(f"cases/{c.case_id}")["facts"]["fieldProvenance"] == original


def test_actual_packet_pipeline_verifies_server_manual_facts_through_service(setup):
    from agents.packets import PacketPipeline
    from tests.unit.test_packet_agents import Client

    c = setup
    c.intake.update_facts(
        c.actor,
        c.case_id,
        {
            "facts": {
                "payment": {
                    "transactionRef": "TEST0000000001",
                    "recipientIdentifier": {"type": "upi", "value": "safe.verify@fakebank"},
                },
                "victimBank": "Test Bank",
            }
        },
    )
    planning = c.planning.enqueue(c.actor, c.case_id, {"previewDraft": True})
    asyncio.run(c.planning.process_case(planning["jobId"]))
    original = c.repository.get(f"cases/{c.case_id}")["facts"]["fieldProvenance"]
    assert original["payment.timestamp"]["source"] == "confirmed"
    assert original["payment.timestamp"]["reference"] is None
    client = Client()
    c.packets.pipeline = PacketPipeline(client)
    accepted = queue_generation(c)
    asyncio.run(c.packets.process(accepted["jobId"]))
    job = c.repository.get(f"jobs/{accepted['jobId']}")
    assert job["state"] == "succeeded" and job["progress"] == {"step": 3, "total": 3}
    case = c.repository.get(f"cases/{c.case_id}")
    assert case["status"] == "PACKETS_VERIFIED"
    assert client.calls == ["WriterOutput", "EntailmentOutput"] * 3
    for packet_id in case["packetIds"]:
        packet = c.packets.get(c.actor, c.case_id, packet_id)
        assert packet["status"] == "VERIFIED"
        assert all(check["passed"] for check in packet["verification"]["checks"])
        timestamp = next(f for f in packet["content"]["fields"] if f["key"] == "payment.timestamp")
        assert (
            timestamp["provenance"]["reference"]
            == f"case:{c.case_id}:facts:{case['factsRevision']}:payment.timestamp"
        )
    assert case["facts"]["fieldProvenance"] == original
    assert c.adapter.calls == 0
