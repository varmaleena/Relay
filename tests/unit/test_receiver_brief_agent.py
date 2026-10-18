"""Synthetic addressed receiver briefs; no model/network calls."""

import asyncio
import json

import pytest

from agents.intake.clients import ModelFailure
from agents.receiver import BriefUnavailable, ReceiverBriefAgent
from agents.receiver.brief import ReceiverBriefEntailmentOutput
from packages.common.identifiers import canonical_hash
from packages.schemas import PacketContent, PacketField, Provenance, ReceiverBrief


class Client:
    model_id = "fixture-receiver"
    mode = "fake"

    def __init__(self, output=None, unsupported=False, fail=False):
        self.output, self.unsupported, self.fail = output, unsupported, fail
        self.calls = []

    async def generate(self, *, prompt, data, schema, media=None):
        self.calls.append((schema.__name__, data))
        if self.fail:
            raise ModelFailure("synthetic-provider-failure")
        if schema is ReceiverBriefEntailmentOutput:
            return json.dumps(
                {
                    "verdicts": [
                        {
                            "index": s["index"],
                            "verdict": "UNSUPPORTED" if self.unsupported else "SUPPORTED",
                        }
                        for s in data["sentences"]
                    ],
                    "languageCorrect": True,
                    "noDecisionClaims": True,
                }
            )
        return json.dumps(
            self.output
            or {
                "suggestions": [
                    {
                        "action": "acknowledge",
                        "why": "The addressed report is ready for staff review.",
                        "factRefs": ["packet"],
                    }
                ]
            }
        )


@pytest.fixture
def projection():
    content = PacketContent(
        language="en",
        recipient_language="en",
        subject="Synthetic report",
        summary="The victim reports a payment.",
        message="Please review this report.",
        fields=[
            PacketField(
                key="payment.amount",
                label="Amount",
                value="INR 45000",
                required=True,
                provenance=Provenance(
                    source="confirmed", reference="case:case_synthetic:facts:1:payment.amount"
                ),
            ),
            PacketField(
                key="payment.transaction_ref",
                label="Transaction reference",
                value="TEST0000000001",
                required=True,
                provenance=Provenance(
                    source="confirmed",
                    reference="case:case_synthetic:facts:1:payment.transaction_ref",
                ),
            ),
        ],
        requested_actions=["Review"],
        citations=[{"reference": "mha-1930:reporting", "status": "unverified"}],
        attachments=[],
        victim_copy={"summary": "Report", "message": "Please review."},
        footer="Unverified simulated draft.",
        completeness={"score": 1.0},
    )
    return {
        "caseRef": "RLY-2026-000123",
        "jurisdiction": "IN",
        "urgency": "critical",
        "typology": "bank_impersonation",
        "authorizationType": "authorized_manipulated",
        "minutesSincePayment": 20,
        "packet": {
            "packetId": "packet_synthetic",
            "recipientId": "bank",
            "recipientName": "Test Bank",
            "version": 1,
            "status": "SENT",
            "content": content.model_dump(mode="json", by_alias=True),
            "contentHash": canonical_hash(content.model_dump(mode="json", by_alias=True)),
            "verification": {"passed": True},
            "stale": False,
        },
        "keyFacts": [],
        "evidence": [],
        "timeline": [],
        "links": [],
    }


def replace_content(projection, update):
    content = projection["packet"]["content"]
    update(content)
    projection["packet"]["contentHash"] = canonical_hash(content)


def test_canonical_deterministic_metadata_and_minimized_model_input(projection):
    projection["evidence"] = [{"previewUrl": "https://example.com?X-Goog-Signature=secret"}]
    projection["timeline"] = [{"text": "receiver-only hidden event"}]
    client = Client()
    brief = asyncio.run(ReceiverBriefAgent(client).make_brief(projection))
    assert isinstance(brief, ReceiverBrief) and brief.completeness_score == 1
    assert len(brief.key_facts) == 2 and brief.missing_items == []
    assert brief.key_facts[0].value == "INR 45000"
    assert brief.suggested_actions[0].action == "acknowledge"
    assert any(r["signal"] == "unverified_sources" for r in brief.risk_signals)
    assert len(client.calls) == 2
    outbound = json.dumps(client.calls)
    assert "X-Goog" not in outbound and "receiver-only hidden event" not in outbound
    assert "ownerUid" not in outbound and "caseRef" not in outbound


def test_supplied_score_authoritative_and_missing_from_actual_fields(projection):
    replace_content(projection, lambda c: c["completeness"].update(score=0.42))
    brief = asyncio.run(ReceiverBriefAgent(Client()).make_brief(projection))
    assert brief.completeness_score == 0.42 and brief.missing_items == []


@pytest.mark.parametrize("where", ["top", "packet"])
def test_full_case_fields_rejected_before_model(projection, where):
    target = projection if where == "top" else projection["packet"]
    target["facts"] = {"victimBank": "unaddressed full case"}
    client = Client()
    with pytest.raises(BriefUnavailable, match="input_invalid"):
        asyncio.run(ReceiverBriefAgent(client).make_brief(projection))
    assert client.calls == []


@pytest.mark.parametrize(
    "mutation",
    [
        {"status": "DRAFT"},
        {"stale": True},
        {"contentHash": "f" * 64},
        {"verification": {"passed": False}},
        {"version": {"fullCase": "secret"}},
    ],
)
def test_unapproved_stale_tampered_projection_fails(projection, mutation):
    projection["packet"].update(mutation)
    client = Client()
    with pytest.raises(BriefUnavailable):
        asyncio.run(ReceiverBriefAgent(client).make_brief(projection))
    assert client.calls == []


def test_missing_fields_weighted_and_hindi_reply(projection):
    def update(c):
        c["language"] = "hi"
        c["fields"][1]["value"] = None
        c["fields"][1]["availability"] = "unknown"
        c["completeness"] = {}

    replace_content(projection, update)
    output = {
        "suggestions": [
            {
                "action": "request_info",
                "why": "The required reference is missing.",
                "factRefs": ["missing:payment.transaction_ref"],
            }
        ],
        "draftReply": {
            "lang": "hi",
            "text": "कृपया लेन-देन की संदर्भ संख्या बताएँ।",
            "requestedItems": ["payment.transaction_ref"],
        },
    }
    brief = asyncio.run(ReceiverBriefAgent(Client(output)).make_brief(projection))
    assert brief.completeness_score == 0.5
    assert brief.missing_items[0].key == "payment.transaction_ref"
    assert brief.draft_reply_to_victim["lang"] == "hi"


def test_unavailable_item_never_requested(projection):
    replace_content(
        projection, lambda c: c["fields"][1].update(value=None, availability="not_available")
    )
    client = Client(
        {
            "suggestions": [
                {
                    "action": "request_info",
                    "why": "Need the reference.",
                    "factRefs": ["missing:payment.transaction_ref"],
                }
            ]
        }
    )
    with pytest.raises(BriefUnavailable, match="unsupported_claim"):
        asyncio.run(ReceiverBriefAgent(client).make_brief(projection))
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "output",
    [
        {"suggestions": [{"action": "place_hold_real", "why": "Done", "factRefs": ["packet"]}]},
        {
            "suggestions": [
                {"action": "acknowledge", "why": "Review", "factRefs": ["invented-other-case"]}
            ]
        },
        {
            "suggestions": [
                {"action": "acknowledge", "why": "Share your OTP.", "factRefs": ["packet"]}
            ]
        },
        {
            "suggestions": [
                {"action": "acknowledge", "why": "We guarantee recovery.", "factRefs": ["packet"]}
            ]
        },
    ],
)
def test_invalid_action_fact_reference_or_unsafe_output(projection, output):
    with pytest.raises(BriefUnavailable):
        asyncio.run(ReceiverBriefAgent(Client(output)).make_brief(projection))


def test_unsupported_sentence_never_returns_fake_brief(projection):
    with pytest.raises(BriefUnavailable, match="unsupported_claim"):
        asyncio.run(ReceiverBriefAgent(Client(unsupported=True)).make_brief(projection))


def test_provider_failure_honest_unavailable(projection):
    client = Client(fail=True)
    with pytest.raises(BriefUnavailable, match="model_unavailable"):
        asyncio.run(ReceiverBriefAgent(client).make_brief(projection))
    assert len(client.calls) == 1


def test_total_timeout_has_no_retry(projection):
    class Slow(Client):
        async def generate(self, **kwargs):
            self.calls.append(("slow", {}))
            await asyncio.sleep(0.1)

    client = Slow()
    with pytest.raises(BriefUnavailable, match="timeout"):
        asyncio.run(ReceiverBriefAgent(client, timeout=0.01).make_brief(projection))
    assert len(client.calls) == 1


def test_deterministic_metadata_cannot_be_model_overridden(projection):
    output = {
        "completenessScore": 1,
        "suggestions": [{"action": "acknowledge", "why": "Review", "factRefs": ["packet"]}],
    }
    with pytest.raises(BriefUnavailable, match="schema_invalid"):
        asyncio.run(ReceiverBriefAgent(Client(output)).make_brief(projection))


def test_missing_entailment_indices_fail_closed(projection):
    class Partial(Client):
        async def generate(self, **kwargs):
            if kwargs["schema"] is ReceiverBriefEntailmentOutput:
                return '{"verdicts":[],"languageCorrect":true,"noDecisionClaims":true}'
            return await super().generate(**kwargs)

    with pytest.raises(BriefUnavailable, match="unsupported_claim"):
        asyncio.run(ReceiverBriefAgent(Partial()).make_brief(projection))


def test_completed_institution_decision_claim_fails(projection):
    class DecisionClaim(Client):
        async def generate(self, **kwargs):
            if kwargs["schema"] is ReceiverBriefEntailmentOutput:
                return json.dumps(
                    {
                        "verdicts": [
                            {"index": s["index"], "verdict": "SUPPORTED"}
                            for s in kwargs["data"]["sentences"]
                        ],
                        "languageCorrect": True,
                        "noDecisionClaims": False,
                    }
                )
            return await super().generate(**kwargs)

    with pytest.raises(BriefUnavailable, match="unsupported_claim"):
        asyncio.run(ReceiverBriefAgent(DecisionClaim()).make_brief(projection))


def test_low_confidence_extracted_required_field_not_present(projection):
    def update(c):
        c["fields"][1]["provenance"] = {
            "source": "extracted",
            "reference": "ev_synthetic",
            "confidence": 0.4,
        }
        c["completeness"] = {}

    replace_content(projection, update)
    output = {
        "suggestions": [
            {
                "action": "request_info",
                "why": "The reference needs confirmation.",
                "factRefs": ["missing:payment.transaction_ref"],
            }
        ],
        "draftReply": {
            "lang": "en",
            "text": "Please confirm the reference.",
            "requestedItems": ["payment.transaction_ref"],
        },
    }
    brief = asyncio.run(ReceiverBriefAgent(Client(output)).make_brief(projection))
    assert brief.completeness_score == 0.5 and len(brief.key_facts) == 1


def test_full_account_never_forwarded_even_in_approved_template(projection):
    def update(c):
        c["fields"][1]["key"] = "bank.account_number"
        c["fields"][1]["label"] = "Account number"
        c["fields"][1]["value"] = "12345678901"

    replace_content(projection, update)
    client = Client()
    with pytest.raises(BriefUnavailable, match="input_unsafe"):
        asyncio.run(ReceiverBriefAgent(client).make_brief(projection))
    assert client.calls == []


def test_invalid_supplied_score_not_replaced_by_model(projection):
    replace_content(projection, lambda c: c["completeness"].update(score=2.0))
    client = Client()
    with pytest.raises(BriefUnavailable, match="input_invalid"):
        asyncio.run(ReceiverBriefAgent(client).make_brief(projection))
    assert client.calls == []


def test_missing_secret_field_is_never_requested(projection):
    def update(c):
        c["fields"][1].update(
            key="victim.password", label="Password", value=None, availability="unknown"
        )

    replace_content(projection, update)
    client = Client()
    with pytest.raises(BriefUnavailable, match="input_unsafe"):
        asyncio.run(ReceiverBriefAgent(client).make_brief(projection))
    assert client.calls == []
