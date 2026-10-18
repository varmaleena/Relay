"""Synthetic packet safety/repair tests; no model network access."""

import asyncio
import json
from functools import wraps
from pathlib import Path

import pytest

from agents.intake.clients import ModelFailure
from agents.packets import PacketPipeline
from agents.packets.core import EntailmentOutput, _sentences
from packages.packs.registry import PackRegistry
from packages.schemas import CaseFacts, PlanStep


def run_async(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))

    return wrapper


class Client:
    model_id = "synthetic-model"
    mode = "fake"

    def __init__(self, *, fail=False, unsupported=False, writer=None):
        self.calls = []
        self.fail = fail
        self.unsupported = unsupported
        self.writer = writer

    async def generate(self, *, prompt, data, schema, media=None):
        self.calls.append(schema.__name__)
        if self.fail:
            raise ModelFailure("synthetic_unavailable")
        if schema is EntailmentOutput:
            return json.dumps(
                {
                    "sentences": [
                        {
                            "index": s["index"],
                            "verdict": "UNSUPPORTED" if self.unsupported else "SUPPORTED",
                        }
                        for s in data["sentences"]
                    ],
                    "blockers": [],
                    "languageCorrect": True,
                }
            )
        return json.dumps(
            self.writer
            or {
                "subject": "Payment report",
                "summary": "I report a payment of INR 45000.",
                "message": "Please review my reported payment.",
                "requestedActions": ["Please acknowledge this report."],
                "victimCopy": {
                    "summary": "I report a payment of INR 45000.",
                    "message": "Please review my reported payment.",
                },
            }
        )


@pytest.fixture
def context():
    registry = PackRegistry(Path("packs"))
    pack = registry.select("IN", allow_draft_preview=True, environment="local", demo_mode=True).pack
    recipient = pack.recipients[0]
    return dict(
        facts=CaseFacts.model_validate(
            {
                "payment": {
                    "amount": {"value": "45000", "currency": "INR"},
                    "timestamp": "2026-10-14T10:00:00Z",
                    "transactionRef": "TEST0000000001",
                }
            }
        ),
        plan_step=PlanStep(
            step_no=1,
            recipient_id=recipient.id,
            action="Report",
            why_now="Promptly",
            channel=recipient.channels[0],
            rule_refs=[],
            source_refs=[],
        ),
        recipient=recipient,
        pack=pack,
        source_passages=registry.passages(pack),
        evidence=[],
        victim_language="en",
        recipient_language="en",
        attachments=[],
    )


@run_async
async def test_verified_server_metadata(context):
    client = Client()
    result = await PacketPipeline(client).build(**context)
    assert result.status == "VERIFIED"
    assert result.attempts == 1
    assert result.content.fields[0].value == "INR 45000"
    assert "Unverified" in result.content.footer
    assert client.calls == ["WriterOutput", "EntailmentOutput"]


@run_async
async def test_missing_required_stops_before_judge(context):
    context["facts"].payment.amount = None
    client = Client()
    result = await PacketPipeline(client).build(**context)
    assert result.status == "NEEDS_HUMAN_REVIEW"
    assert client.calls == ["WriterOutput"]
    assert "payment.amount" in result.content.completeness["missing"]
    assert any(c.id == "required" and not c.passed for c in result.checks)


@run_async
async def test_unsupported_repair_bounded(context):
    client = Client(unsupported=True)
    result = await PacketPipeline(client).build(**context)
    assert result.status == "NEEDS_HUMAN_REVIEW"
    assert result.attempts == 3
    assert len(client.calls) == 6


@run_async
async def test_transport_never_fake_draft(context):
    result = await PacketPipeline(Client(fail=True)).build(**context)
    assert result.content is None
    assert result.status == "NEEDS_HUMAN_REVIEW"
    assert result.attempts == 1


@run_async
@pytest.mark.parametrize(
    "change,check_id",
    [
        ({"footer": "Reviewed and approved"}, "footer"),
        ({"language": "hi"}, "language"),
        ({"attachments": [{"sha256": "wrong"}]}, "attachments"),
        ({"citations": [{"reference": "invented"}]}, "citations"),
        ({"summary": "I paid INR 90000."}, "amounts"),
        ({"message": "My payment was at 2026-10-15T10:00:00Z."}, "timestamps"),
        ({"message": "My account number 12345678901."}, "safety"),
        ({"message": "Share your OTP."}, "safety"),
        ({"message": "Your money will be recovered."}, "promise"),
    ],
)
async def test_edits_fail_deterministic_before_judge(context, change, check_id):
    client = Client()
    pipeline = PacketPipeline(client)
    result = await pipeline.build(**context)
    before = len(client.calls)
    edited = result.content.model_copy(update=change)
    checks = await pipeline.verifier.verify(edited, **context)
    assert any(c.id == check_id and not c.passed for c in checks)
    assert len(client.calls) == before


@run_async
async def test_missing_sentence_verdict_rejected(context):
    class Partial(Client):
        async def generate(self, **kwargs):
            if kwargs["schema"] is EntailmentOutput:
                return '{"sentences":[],"blockers":[],"languageCorrect":true}'
            return await super().generate(**kwargs)

    result = await PacketPipeline(Partial(), max_repairs=0).build(**context)
    assert result.status == "NEEDS_HUMAN_REVIEW"
    assert len(_sentences(result.content)) >= 2


@run_async
async def test_secret_in_input_never_reaches_provider(context):
    context["facts"].contact.identifier = "OTP: 123456"
    client = Client()
    result = await PacketPipeline(client).build(**context)
    assert result.content is None and not client.calls


@run_async
async def test_structured_field_tamper(context):
    client = Client()
    pipeline = PacketPipeline(client)
    content = (await pipeline.build(**context)).content
    content.fields[0].value = "INR 99"
    checks = await pipeline.verifier.verify(content, **context)
    assert any(c.id == "fields" and not c.passed for c in checks)


@run_async
@pytest.mark.parametrize(
    "message,check_id",
    [
        ("I paid wrong@inventedbank.", "identifiers"),
        ("The transaction reference is TEST9999999999.", "identifiers"),
    ],
)
async def test_invented_identifiers_blocked(context, message, check_id):
    pipeline = PacketPipeline(Client())
    content = (await pipeline.build(**context)).content
    content.message = message
    checks = await pipeline.verifier.verify(content, **context)
    assert any(c.id == check_id and not c.passed for c in checks)


@run_async
async def test_unavailable_is_explicit_not_fabricated(context):
    context["facts"].unavailable_fields = ["payment.transaction_ref"]
    result = await PacketPipeline(Client(), max_repairs=0).build(**context)
    field = next(f for f in result.content.fields if f.key == "payment.transaction_ref")
    assert field.value is None and field.availability == "not_available"
    assert result.status == "NEEDS_HUMAN_REVIEW"


@run_async
async def test_full_account_not_passed_to_writer(context):
    from packages.schemas import Identifier

    context["facts"].payment.recipient_identifier = Identifier(
        type="bank_account", value="12345678901"
    )
    client = Client()
    result = await PacketPipeline(client).build(**context)
    assert result.content is None and not client.calls


@run_async
async def test_pdf_bilingual_and_missing_font_fail_closed(context):
    from io import BytesIO

    from pypdf import PdfReader

    from packages.packets.pdf import PacketPDFError, render_packet_pdf

    result = await PacketPipeline(Client()).build(**context)
    result.content.victim_copy = {
        "summary": "भुगतान की जानकारी",
        "message": "कृपया रिपोर्ट की जाँच करें।",
    }
    pdf = render_packet_pdf(result.content, recipient_name="Your fictional bank")
    assert pdf.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) >= 1
    assert "INR 45000" in reader.pages[0].extract_text()
    assert "Amount and currency" in reader.pages[0].extract_text()
    assert "payment.amount" not in reader.pages[0].extract_text()
    with pytest.raises(PacketPDFError, match="pdf_unicode_font_required"):
        render_packet_pdf(
            result.content, recipient_name="Your fictional bank", font_path="absent.ttf"
        )


def test_writer_provider_shape_is_constrained():
    from agents.intake.clients import provider_schema
    from agents.packets.core import WriterOutput

    schema = provider_schema(WriterOutput)
    assert set(schema["properties"]["victimCopy"]["properties"]) == {"summary", "message"}


@run_async
async def test_missing_reference_confirmation_can_be_verified(context):
    from agents.packets import prepare_content

    context["facts"].payment.transaction_ref = None
    pipeline = PacketPipeline(Client(), max_repairs=0)
    content = (await pipeline.build(**context)).content
    field = next(f for f in content.fields if f.key == "payment.transaction_ref")
    field.value = "TEST0000000002"
    confirms = {"payment.transaction_ref": "TEST0000000002"}
    prepared = prepare_content(content, **context, confirmed_fields=confirms)
    checks = await pipeline.verifier.verify(prepared, **context, confirmed_fields=confirms)
    assert all(c.passed for c in checks)
    assert "payment.transaction_ref" not in prepared.completeness["missing"]
    assert (
        next(f for f in prepared.fields if f.key == "payment.transaction_ref").provenance.source
        == "confirmed"
    )


@run_async
async def test_confirmation_cannot_override_existing_money(context):
    from agents.packets import prepare_content

    pipeline = PacketPipeline(Client())
    content = (await pipeline.build(**context)).content
    content.fields[0].value = "INR 90000"
    confirms = {"payment.amount": "INR 90000"}
    with pytest.raises(ValueError, match="invalid_field_confirmation"):
        prepare_content(content, **context, confirmed_fields=confirms)
    checks = await pipeline.verifier.verify(content, **context, confirmed_fields=confirms)
    assert any(not c.passed and c.id == "field_confirmation" for c in checks)


@run_async
async def test_normalization_does_not_erase_tampering(context):
    from agents.packets import prepare_content

    pipeline = PacketPipeline(Client())
    content = (await pipeline.build(**context)).content
    content.fields[0].value = "INR 90000"
    content.footer = "Approved"
    prepared = prepare_content(content, **context)
    assert prepared.fields[0].value == "INR 90000" and prepared.footer == "Approved"
    checks = await pipeline.verifier.verify(prepared, **context)
    assert any(not c.passed and c.id == "fields" for c in checks)
    assert any(not c.passed and c.id == "footer" for c in checks)


@run_async
async def test_unsafe_generated_credentials_never_returned(context):
    client = Client(
        writer={
            "subject": "Report",
            "summary": "My payment report.",
            "message": "My OTP: 123456.",
            "requestedActions": ["Please review."],
            "victimCopy": {"summary": "Report", "message": "My OTP: 123456."},
        }
    )
    result = await PacketPipeline(client).build(**context)
    assert result.content is None
    assert result.status == "NEEDS_HUMAN_REVIEW"
    assert client.calls == ["WriterOutput"] * 3


@run_async
async def test_plan_cannot_reference_unknown_rule(context):
    context["plan_step"].rule_refs = ["invented-regulation"]
    client = Client()
    result = await PacketPipeline(client, max_repairs=0).build(**context)
    assert any(c.id == "rule_references" and not c.passed for c in result.checks)
    assert "EntailmentOutput" not in client.calls


def test_packet_profile_shares_global_concurrency_and_keeps_base_defaults():
    from types import SimpleNamespace

    from agents.intake.clients import GoogleGenAIClient
    from agents.intake.core import IntakeModelOutput
    from agents.packets.core import EntailmentOutput, WriterOutput
    from packages.common.settings import Settings

    async def scenario():
        active, peak = 0, 0
        configs = []

        async def generate_content(**kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            configs.append(kwargs["config"])
            await asyncio.sleep(0.005)
            active -= 1
            return SimpleNamespace(text="{}", usage_metadata=None)

        sdk = SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        )
        base = GoogleGenAIClient(
            Settings(
                genai_mode="live",
                intake_enabled=True,
                gcp_project_id="demo-relay-local",
                genai_location="global",
                model_reasoning="gemini-3.8-flash",
                max_model_concurrency=1,
                packet_thinking_level="LOW",
            ),
            sdk_client=sdk,
        )
        packet = base.for_packets()
        await asyncio.gather(
            base.generate(prompt="synthetic", data={}, schema=IntakeModelOutput),
            packet.generate(prompt="synthetic", data={}, schema=WriterOutput),
            packet.generate(prompt="synthetic", data={}, schema=EntailmentOutput),
        )
        assert peak == 1 and packet.parent is base
        assert configs[0].thinking_config is None and configs[0].max_output_tokens == 2000
        assert configs[1].thinking_config.thinking_level == "LOW"
        assert configs[1].max_output_tokens == 2500 and configs[1].temperature == 0.3
        assert configs[2].max_output_tokens == 2000 and configs[2].temperature == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status,reason", [(400, "http_400"), (429, "http_429"), (503, "http_503"), (504, "http_504")]
)
def test_typed_failure_and_persistent_safe_ledger(tmp_path, status, reason):
    from types import SimpleNamespace

    from agents.intake.clients import GoogleGenAIClient
    from agents.packets.core import WriterOutput
    from agents.packets.smoke import CappedClient
    from packages.common.settings import Settings

    class ProviderError(Exception):
        code = status
        message = "SENSITIVE raw provider prose OTP123456"

    async def generate_content(**kwargs):
        raise ProviderError()

    async def scenario():
        sdk = SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        )
        base = GoogleGenAIClient(
            Settings(
                genai_mode="live",
                intake_enabled=True,
                gcp_project_id="demo-relay-local",
                genai_location="global",
                model_reasoning="gemini-3.8-flash",
            ),
            sdk_client=sdk,
        )
        path = tmp_path / "attempts.jsonl"
        cap = CappedClient(base.for_packets(), usage_source=base, ledger_path=path)
        with pytest.raises(ModelFailure) as exc:
            await cap.generate(
                prompt="synthetic", data={"repairChecks": ["required"]}, schema=WriterOutput
            )
        assert exc.value.reason == reason and exc.value.status_code == status
        row = json.loads(path.read_text())
        assert row["reason"] == reason and row["stage"] == "writer"
        assert row["repairCheckIds"] == ["required"] and row["usage"] == []
        assert "SENSITIVE" not in path.read_text() and "123456" not in path.read_text()
        assert base.failure_records[0]["reason"] == reason

    asyncio.run(scenario())


def test_failure_type_not_guessed_from_error_prose():
    import httpx

    from agents.intake.clients import _failure_reason

    class MisleadingError(Exception):
        message = "429 ReadTimeout 503 - claims only"

    assert _failure_reason(MisleadingError()) == (None, "unknown")
    assert _failure_reason(httpx.ReadTimeout("never persist this message")) == (
        None,
        "read_timeout",
    )
    assert _failure_reason(httpx.ConnectTimeout("never persist this message")) == (
        None,
        "connect_timeout",
    )


def test_attempt_history_retains_failed_verdicts(context):
    result = asyncio.run(PacketPipeline(Client(unsupported=True)).build(**context))
    assert len(result.attempt_history) == 3
    assert all(
        any(not c["passed"] and c["id"] == "entailment" for c in row["checks"])
        for row in result.attempt_history
    )


@run_async
@pytest.mark.parametrize(
    "message",
    [
        "Please provide a reference number.",
        "Please acknowledge with a transaction reference.",
        "I paid safe.verify@fakebank.",
        "The transaction reference number is TEST0000000001.",
    ],
)
async def test_ordinary_reference_requests_and_terminal_punctuation(context, message):
    from packages.schemas import Identifier

    context["facts"].payment.recipient_identifier = Identifier(
        type="upi", value="safe.verify@fakebank"
    )
    pipeline = PacketPipeline(Client())
    content = (await pipeline.build(**context)).content
    content.message = message
    checks = await pipeline.verifier.verify(content, **context)
    assert all(c.passed for c in checks)


@run_async
async def test_repair_provider_failure_preserves_prior_safe_draft_and_checks(context):
    class RepairFails(Client):
        async def generate(self, **kwargs):
            if kwargs["schema"] is not EntailmentOutput and self.calls:
                raise ModelFailure("model_unavailable:429", status_code=429, reason="http_429")
            return await super().generate(**kwargs)

    result = await PacketPipeline(RepairFails(unsupported=True)).build(**context)
    assert result.content is not None and result.status == "NEEDS_HUMAN_REVIEW"
    assert any(c.id == "entailment" and not c.passed for c in result.checks)
    assert any(c.id == "writer_unavailable" and not c.passed for c in result.checks)


def test_synthetic_smoke_snapshots_safe_writer_not_secrets(tmp_path):
    from types import SimpleNamespace

    from agents.packets.core import WriterOutput
    from agents.packets.smoke import CappedClient

    async def scenario():
        source = SimpleNamespace(usage_records=[])
        client = Client()
        cap = CappedClient(
            client,
            usage_source=source,
            ledger_path=tmp_path / "safe.jsonl",
            synthetic_input_hash="a" * 64,
        )
        await cap.generate(
            prompt="synthetic", data={"recipient": {"id": "bank"}}, schema=WriterOutput
        )
        row = json.loads(cap.snapshot_path.read_text())
        assert row["synthetic"] is True and row["verified"] is False
        assert row["recipientId"] == "bank" and row["inputSha256"] == "a" * 64
        assert row["writerOutput"]["subject"] == "Payment report"
        unsafe = Client(
            writer={
                "subject": "Report",
                "summary": "Report",
                "message": "OTP: 123456",
                "requestedActions": ["Review"],
                "victimCopy": {"summary": "Report", "message": "Report"},
            }
        )
        cap2 = CappedClient(
            unsafe,
            usage_source=source,
            ledger_path=tmp_path / "unsafe.jsonl",
            synthetic_input_hash="b" * 64,
        )
        await cap2.generate(prompt="synthetic", data={}, schema=WriterOutput)
        assert cap2.snapshot_path.read_text() == ""
        assert cap2.ledger[0]["snapshotRejected"] == "unsafe_or_oversized"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "reason", ["http_429", "http_503", "http_504", "connect_timeout", "read_timeout", "timeout"]
)
def test_packet_transient_retry_counts_every_attempt_and_backoff(tmp_path, reason):
    from types import SimpleNamespace

    from agents.packets import RetryPacketClient
    from agents.packets.core import WriterOutput
    from agents.packets.smoke import CappedClient

    class OneTransient(Client):
        async def generate(self, **kwargs):
            if not self.calls:
                self.calls.append("failed")
                raise ModelFailure("synthetic_transient", reason=reason)
            return await super().generate(**kwargs)

    async def scenario():
        sleeps = []

        async def sleep(seconds):
            sleeps.append(seconds)

        cap = CappedClient(
            OneTransient(),
            usage_source=SimpleNamespace(usage_records=[]),
            ledger_path=tmp_path / "attempts.jsonl",
        )
        retry = RetryPacketClient(cap, on_retry=cap.record_retry, sleep=sleep, jitter=lambda: 0)
        await retry.generate(prompt="synthetic", data={}, schema=WriterOutput)
        expected_backoff = 8 if reason == "http_429" else 2
        assert cap.attempts == 2 and sleeps == [expected_backoff]
        rows = [json.loads(line) for line in cap.ledger_path.read_text().splitlines()]
        assert [r["event"] for r in rows] == [
            "provider_attempt",
            "retry_backoff",
            "provider_attempt",
        ]
        assert rows[0]["reason"] == reason and rows[1]["backoffSeconds"] == expected_backoff

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "reason",
    ["http_400", "http_401", "http_403", "http_404", "unknown", "cancelled", "empty_response"],
)
def test_packet_never_retries_nontransient(reason):
    from agents.packets import RetryPacketClient
    from agents.packets.core import WriterOutput

    class Fails(Client):
        async def generate(self, **kwargs):
            self.calls.append("call")
            raise ModelFailure("synthetic_failure", reason=reason)

    async def scenario():
        client = Fails()
        with pytest.raises(ModelFailure):
            await RetryPacketClient(client).generate(
                prompt="synthetic", data={}, schema=WriterOutput
            )
        assert len(client.calls) == 1

    asyncio.run(scenario())


def test_packet_retry_at_most_once_and_requires_remaining_deadline():
    from agents.packets import RetryPacketClient
    from agents.packets.core import WriterOutput

    class Fails(Client):
        async def generate(self, **kwargs):
            self.calls.append("call")
            raise ModelFailure("synthetic_failure", reason="http_503")

    async def scenario():
        async def sleep(seconds):
            pass

        client = Fails()
        with pytest.raises(ModelFailure):
            await RetryPacketClient(client, sleep=sleep).generate(
                prompt="synthetic", data={}, schema=WriterOutput
            )
        assert len(client.calls) == 2
        short = Fails()
        with pytest.raises(ModelFailure):
            await RetryPacketClient(short, timeout=16, sleep=sleep).generate(
                prompt="synthetic", data={}, schema=WriterOutput
            )
        assert len(short.calls) == 1

    asyncio.run(scenario())


def test_packet_cancellation_during_backoff_never_calls_again():
    from agents.packets import RetryPacketClient
    from agents.packets.core import WriterOutput

    class Fails(Client):
        async def generate(self, **kwargs):
            self.calls.append("call")
            raise ModelFailure("synthetic_failure", reason="http_429")

    async def scenario():
        client = Fails()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                RetryPacketClient(client).generate(
                    prompt="synthetic", data={}, schema=WriterOutput
                ),
                0.01,
            )
        assert len(client.calls) == 1

    asyncio.run(scenario())


def test_retry_cap_never_exceeds_eighteen_actual_attempts(tmp_path):
    from types import SimpleNamespace

    from agents.packets import RetryPacketClient
    from agents.packets.core import WriterOutput
    from agents.packets.smoke import CappedClient

    async def scenario():
        cap = CappedClient(
            Client(),
            usage_source=SimpleNamespace(usage_records=[]),
            ledger_path=tmp_path / "cap.jsonl",
        )
        retry = RetryPacketClient(cap)
        for _ in range(18):
            await retry.generate(prompt="synthetic", data={}, schema=WriterOutput)
        with pytest.raises(ModelFailure, match="smoke_request_limit"):
            await retry.generate(prompt="synthetic", data={}, schema=WriterOutput)
        assert cap.attempts == 18 and len(cap.ledger) == 18

    asyncio.run(scenario())


@run_async
async def test_server_confirmed_origins_anchored_to_case_revision_without_mutation(context):
    from agents.packets import anchor_confirmed_facts
    from packages.schemas import Provenance

    facts = context["facts"]
    facts.field_provenance = {
        "payment.timestamp": Provenance(source="confirmed"),
        "payment.method": Provenance(source="confirmed"),
        "payment.transactionRef": Provenance(source="confirmed"),
        "payment.amount.value": Provenance(source="confirmed"),
        "payment.amount.currency": Provenance(source="confirmed"),
    }
    facts.payment.method = "upi"
    context["facts"] = anchor_confirmed_facts(facts, case_id="case_synthetic", facts_revision=7)
    result = await PacketPipeline(Client()).build(**context)
    assert result.status == "VERIFIED"
    for key in ["payment.timestamp", "payment.method", "payment.transaction_ref", "payment.amount"]:
        origin = next(f.provenance for f in result.content.fields if f.key == key)
        assert (
            origin.source == "confirmed"
            and origin.reference == f"case:case_synthetic:facts:7:{key}"
        )
    assert facts.field_provenance["payment.timestamp"].reference is None
    next_revision = anchor_confirmed_facts(facts, case_id="case_synthetic", facts_revision=8)
    assert (
        next_revision.field_provenance["payment.timestamp"].reference
        != context["facts"].field_provenance["payment.timestamp"].reference
    )


@run_async
@pytest.mark.parametrize("reference", [None, "invented-evidence"])
async def test_alias_normalization_never_replaces_extracted_evidence_origin(context, reference):
    from agents.packets import anchor_confirmed_facts
    from packages.schemas import Provenance

    context["facts"].field_provenance = {
        "payment.transactionRef": Provenance(
            source="extracted", reference=reference, confidence=0.99
        )
    }
    context["facts"] = anchor_confirmed_facts(
        context["facts"], case_id="case_synthetic", facts_revision=1
    )
    client = Client()
    result = await PacketPipeline(client).build(**context)
    assert result.status == "NEEDS_HUMAN_REVIEW"
    assert client.calls == ["WriterOutput"]
    origin = next(f.provenance for f in result.content.fields if f.key == "payment.transaction_ref")
    assert origin.source == "extracted" and origin.reference == reference
    assert any(not c.passed and c.id == "provenance" for c in result.checks)


def test_composite_confirmation_requires_all_components(context):
    from agents.packets import anchor_confirmed_facts
    from packages.schemas import Provenance

    facts = context["facts"]
    facts.field_provenance = {
        "payment.amount.value": Provenance(source="confirmed"),
        "payment.amount.currency": Provenance(
            source="extracted", reference="ev_synthetic", confidence=0.5
        ),
    }
    anchored = anchor_confirmed_facts(facts, case_id="case_synthetic", facts_revision=1)
    assert anchored.field_provenance["payment.amount"].source == "inferred"
    assert anchored.field_provenance["payment.amount"].reference is None


def test_existing_confirmed_reference_is_preserved(context):
    from agents.packets import anchor_confirmed_facts
    from packages.schemas import Provenance

    context["facts"].field_provenance = {
        "payment.timestamp": Provenance(source="confirmed", reference="ev_synthetic")
    }
    anchored = anchor_confirmed_facts(context["facts"], case_id="case_synthetic", facts_revision=1)
    assert anchored.field_provenance["payment.timestamp"].reference == "ev_synthetic"


@run_async
async def test_common_missing_contact_confirmation_and_unavailable_metadata_are_verifiable(context):
    from agents.packets import prepare_content
    from packages.schemas import Provenance

    pipeline = PacketPipeline(Client())
    built = await pipeline.build(**context)
    field = next(item for item in built.content.fields if item.key == "contact.identifier")
    field.value = "synthetic-caller"
    field.availability = "available"
    prepared = prepare_content(
        built.content, **context, confirmed_fields={"contact.identifier": "synthetic-caller"}
    )
    checks = await pipeline.verifier.verify(
        prepared, **context, confirmed_fields={"contact.identifier": "synthetic-caller"}
    )
    assert all(c.passed or c.severity != "blocker" for c in checks)
    # A separate explicit unavailable answer carries no invented identifier.
    context["facts"].unavailable_fields.append("contact.identifier")
    context["facts"].field_provenance["contact.identifier"] = Provenance(
        source="confirmed", reference="packet_confirmation:contact.identifier"
    )
    unavailable = await pipeline.build(**context)
    assert unavailable.status == "VERIFIED"
    field = next(item for item in unavailable.content.fields if item.key == "contact.identifier")
    assert field.value is None and field.availability == "not_available"
