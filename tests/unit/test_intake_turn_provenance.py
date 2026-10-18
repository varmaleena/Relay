"""Offline reproduction of unanchored statement blocker; no provider calls."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from agents.packets.core import PacketVerifier, _metadata, anchor_confirmed_facts
from packages.intake.service import IntakeError, merge_facts
from packages.packs.registry import PackRegistry
from packages.schemas import CaseFacts, PacketContent, PlanStep
from tests.unit.test_intake_service import setup  # noqa: F401

NOW = datetime(2026, 10, 14, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def reproducible_statement_identifiers(monkeypatch):
    """Avoid random card-shaped digit runs in synthetic opaque provenance IDs."""
    from itertools import count
    from uuid import UUID

    sequence = count(1)
    monkeypatch.setattr(
        "packages.common.identifiers.uuid4",
        lambda: UUID(hex=f"bbbbbbbbbbbbbbbbbbbbbbbb{next(sequence):08x}"),
    )


def confirmed():
    return {
        "country": {"value": "IN"},
        "payment": {
            "method": "upi",
            "amount": {"value": "45000", "currency": "INR"},
            "timestamp": (NOW - timedelta(minutes=20)).isoformat(),
            "authorizedByVictim": True,
            "transactionRef": "TEST0000000001",
            "recipientIdentifier": {"type": "upi_id", "value": "safe.verify@fakebank"},
        },
        "contact": {"channel": "phone", "identifier": "synthetic-caller"},
        "ongoingContact": False,
        "victimBank": "Fictional Test Bank",
    }


class SyntheticEntailment:
    calls = 0

    async def generate(self, *, data, **kwargs):
        self.calls += 1
        return json.dumps(
            {
                "sentences": [
                    {"index": item["index"], "verdict": "SUPPORTED"} for item in data["sentences"]
                ],
                "blockers": [],
                "languageCorrect": True,
            }
        )


def verify_all(facts):
    registry = PackRegistry(ROOT / "packs")
    pack = next(
        p
        for p in registry.available(allow_draft_preview=True, environment="local", demo_mode=True)
        if p.pack_id == "pack_in_cyber_rail"
    )
    facts = anchor_confirmed_facts(
        CaseFacts.model_validate(facts), case_id="case_synthetic", facts_revision=2
    )
    model = SyntheticEntailment()
    results = []
    for index, recipient in enumerate(pack.recipients):
        step = PlanStep(
            step_no=index + 1,
            recipient_id=recipient.id,
            action="Review report",
            why_now="Synthetic test",
            channel=recipient.channels[0],
            rule_refs=[recipient.id],
            source_refs=recipient.source_refs,
        )
        source_passages = registry.passages(pack)
        metadata = _metadata(facts, recipient, pack, step, source_passages, [])
        content = PacketContent(
            language="en",
            recipient_language="en",
            subject="Synthetic report",
            summary="Please review this report.",
            message="Please review this report.",
            requested_actions=["Review the report."],
            victim_copy={
                "summary": "Please review this report.",
                "message": "Please review this report.",
            },
            **metadata,
        )
        checks = asyncio.run(
            PacketVerifier(model).verify(
                content,
                facts=facts,
                plan_step=step,
                recipient=recipient,
                pack=pack,
                source_passages=source_passages,
                evidence=[],
                victim_language="en",
                recipient_language="en",
                attachments=[],
            )
        )
        results.append(checks)
    return results, model.calls


def test_reproduces_exact_sixteen_checks_one_provenance_blocker_without_inference():
    base = merge_facts(
        CaseFacts().model_dump(mode="json", by_alias=True), confirmed(), confirmed=True, now=NOW
    )
    changed = merge_facts(base, {"contact": {"claimedIdentity": "bank"}}, confirmed=False, now=NOW)
    results, calls = verify_all(changed)
    assert calls == 0
    assert len(results) == 3
    assert all(len(checks) == 16 for checks in results)
    assert all(
        [check.id for check in checks if not check.passed] == ["provenance"] for checks in results
    )


def test_message_records_real_turn_origin_same_transaction_and_static_checks_pass(setup):  # noqa: F811
    service, repo, _, agent, _, actor, case_id, clock = setup
    clock[0] = NOW
    service.update_facts(actor, case_id, {"facts": confirmed()})
    before = repo.get("cases/" + case_id)["facts"]["fieldProvenance"]
    agent.delta = {"contact": {"claimedIdentity": "bank"}}
    response = asyncio.run(
        service.message(
            actor,
            case_id,
            {"text": "A person claiming to be my bank contacted me.", "lang": "en"},
            str(uuid4()),
        )
    )
    case = repo.get("cases/" + case_id)
    provenance = case["facts"]["fieldProvenance"]
    origin = provenance["contact.claimedIdentity"]
    assert origin["source"] == "victim_statement"
    assert (
        origin["reference"]
        == f"case:{case_id}:turn:{response['turnId']}:facts:{case['factsRevision']}"
    )
    turn = repo.get(f"cases/{case_id}/transcript/{response['turnId']}")
    assert turn["role"] == "user" and "my bank" in turn["text"]
    assert provenance["payment.transactionRef"] == before["payment.transactionRef"]
    results, calls = verify_all(case["facts"])
    assert calls == 3  # Synthetic entailment only, after every static check passed.
    assert all(all(check.passed for check in checks) for checks in results)


def test_unrelated_current_turn_does_not_repair_legacy_or_override_confirmed():
    base = merge_facts(
        CaseFacts().model_dump(mode="json", by_alias=True), confirmed(), confirmed=True, now=NOW
    )
    legacy = merge_facts(base, {"contact": {"claimedIdentity": "bank"}}, confirmed=False, now=NOW)
    changed = merge_facts(
        legacy,
        {"contact": {"claimedIdentity": "bank"}, "payment": {"transactionRef": "MUTATED0000"}},
        confirmed=False,
        now=NOW,
        statement_reference="case:case_synthetic:turn:turn_new:facts:3",
    )
    assert changed["fieldProvenance"]["contact.claimedIdentity"]["source"] == "victim_statement"
    assert changed["fieldProvenance"]["contact.claimedIdentity"]["reference"] is None
    assert changed["payment"]["transactionRef"] == "TEST0000000001"
    results, calls = verify_all(changed)
    assert calls == 0 and all(
        any(c.id == "provenance" and not c.passed for c in checks) for checks in results
    )


def test_model_metadata_cannot_supply_turn_or_evidence_origin():
    changed = merge_facts(
        CaseFacts().model_dump(mode="json", by_alias=True),
        {
            "contact": {"claimedIdentity": "bank", "provenance": {"source": "confirmed"}},
            "fieldProvenance": {
                "contact.claimedIdentity": {"source": "extracted", "reference": "fake"}
            },
        },
        confirmed=False,
        now=NOW,
    )
    assert changed["fieldProvenance"]["contact.claimedIdentity"]["source"] == "victim_statement"
    assert changed["fieldProvenance"]["contact.claimedIdentity"]["reference"] is None
    with pytest.raises(IntakeError):
        merge_facts(changed, {}, confirmed=False, now=NOW, statement_reference="fake-tool-call")


def test_composite_statement_origin_requires_same_actual_turn_for_all_components():
    ref = "case:case_synthetic:turn:turn_original:facts:1"
    base = merge_facts(
        CaseFacts().model_dump(mode="json", by_alias=True),
        {"payment": {"amount": {"value": "45000", "currency": "INR"}}},
        confirmed=False,
        now=NOW,
        statement_reference=ref,
    )
    origin = base["fieldProvenance"]["payment.amount"]
    assert origin["source"] == "victim_statement" and origin["reference"] == ref
    changed = merge_facts(
        base,
        {"payment": {"amount": {"value": "50000"}}},
        confirmed=False,
        now=NOW,
        statement_reference="case:case_synthetic:turn:turn_new:facts:2",
    )
    anchored = anchor_confirmed_facts(
        CaseFacts.model_validate(changed), case_id="case_synthetic", facts_revision=2
    )
    assert anchored.field_provenance["payment.amount"].source == "inferred"
    assert anchored.field_provenance["payment.amount"].reference is None
