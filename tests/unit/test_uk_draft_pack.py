"""Isolated UK draft evidence integrity and deterministic cross-jurisdiction contrast."""

import hashlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from packages.packs.expressions import compile_expression
from packages.packs.registry import PackRegistry, PackRegistryError
from packages.packs.validator import load_pack, validate_pack
from packages.planning.engine import compute
from packages.schemas import CaseFacts, Classification

ROOT = Path(__file__).resolve().parents[2]
PACKS = ROOT / "packs/uk"
SOURCES = ROOT / "docs/pack-sources/uk"


def registry():
    return PackRegistry(PACKS, source_root=SOURCES)


def draft():
    return registry().available(allow_draft_preview=True, environment="local", demo_mode=True)[0]


def facts(country="GB", method="bank_transfer"):
    now = datetime(2026, 10, 17, 12, tzinfo=UTC)
    return CaseFacts.model_validate(
        {
            "country": {"value": country, "provenance": {"source": "selected"}},
            "payment": {
                "method": method,
                "amount": {"value": "3000", "currency": "GBP"},
                "timestamp": (now - timedelta(days=3)).isoformat(),
                "authorizedByVictim": True,
            },
            "discoveryTimestamp": now.isoformat(),
            "ongoingContact": False,
        }
    )


def classification(authorization="authorized_manipulated"):
    return Classification(
        typology="investment",
        authorization_type=authorization,
        authorization_rationale="Synthetic scenario only.",
        confidence=0.95,
        urgency={"level": "high", "reason": "Synthetic operational priority."},
    )


def test_draft_schema_exact_sources_hashes_passages_and_offsets():
    reg, pack = registry(), draft()
    assert reg.root == PACKS.resolve() and reg.source_root == SOURCES.resolve()
    passages = reg.passages(pack)
    assert len(passages) == 16
    assert validate_pack(pack, set(passages)) == []
    for item in json.loads((SOURCES / "passages.json").read_text(encoding="utf-8")):
        extraction = (SOURCES / (item["source_id"] + ".txt")).read_text(encoding="utf-8")
        assert extraction[item["offsetStart"] : item["offsetEnd"]] == item["text"]
        assert hashlib.sha256(item["text"].encode()).hexdigest() == item["sha256"]
        assert item["page"] is None  # HTML has extracted-text offsets, not invented page numbers.
    assert pack.pack_id == "pack_uk_reimbursement" and pack.jurisdiction.code == "GB"


def test_no_human_review_publication_verified_channels_or_numeric_dates():
    pack = draft()
    assert pack.status == "draft" and not pack.review.reviewer and not pack.review.reviewed_at
    assert not pack.review.accepted_unverified_rule_ids
    assert all(
        rule.status == "unverified"
        for rule in [*pack.recipients, *pack.sequencing, *pack.deadlines, *pack.liability_rules]
    )
    assert all(
        not channel.verified for recipient in pack.recipients for channel in recipient.channels
    )
    assert all(rule.duration is None for rule in pack.deadlines)
    assert "human_review_required" in {
        issue.code
        for issue in validate_pack(pack, set(registry().passages(pack)), for_publish=True)
    }
    assert registry().available() == []


def test_same_story_explicit_india_uk_changes_recipients_forms_and_timing_metadata():
    now = datetime(2026, 10, 17, 12, tzinfo=UTC)
    uk = draft()
    india_registry = PackRegistry(ROOT / "packs")
    india = next(
        pack
        for pack in india_registry.available(
            allow_draft_preview=True, environment="local", demo_mode=True
        )
        if pack.pack_id == "pack_in_cyber_rail"
    )
    uk_plan = compute(
        pack=uk,
        facts=facts(),
        classification=classification(),
        now=now,
        source_passages=registry().passages(uk),
    )
    india_plan = compute(
        pack=india,
        facts=facts("IN"),
        classification=classification(),
        now=now,
        source_passages=india_registry.passages(india),
    )
    assert [step.recipient_id for step in uk_plan.steps] == ["bank"]
    assert [step.recipient_id for step in india_plan.steps] == ["bank", "cyber"]
    assert uk.forms[0].fields != india.forms[0].fields
    assert uk.currency == "GBP" and india.currency == "INR"
    assert uk.timezone == "Europe/London" and india.timezone == "Asia/Kolkata"
    assert uk.languages == ["en"] and india.languages == ["en", "hi"]
    assert all(step.deadline is None or step.deadline.due_at is None for step in uk_plan.steps)
    assert uk_plan.steps[0].source_refs and uk_plan.steps[0].rule_refs
    wrong_country = compute(
        pack=uk,
        facts=facts("IN"),
        classification=classification(),
        now=now,
        source_passages=registry().passages(uk),
    )
    assert wrong_country.steps == []


@pytest.mark.parametrize(
    "method,authorization,expected",
    [
        ("bank_transfer", "authorized_manipulated", True),
        ("bank_transfer", "unauthorized_access", False),
        ("bank_transfer", "unclear", False),
        ("card", "card_unauthorized", False),
        ("crypto", "authorized_manipulated", False),
    ],
)
def test_app_context_does_not_mix_unauthorized_card_or_crypto_rules(
    method, authorization, expected
):
    rule = draft().liability_rules[0]
    outcome = compile_expression(rule.condition).evaluate(
        {
            "facts": facts(method=method).model_dump(mode="python"),
            "classification": classification(authorization).model_dump(mode="python"),
        }
    )
    assert outcome is expected  # Context relevance only; never an eligibility decision.


def test_missing_nation_and_complaint_state_keep_routes_blocked():
    pack = draft()
    for recipient in pack.recipients[1:]:
        assert recipient.applies_when == "False"
    mapping = json.loads((SOURCES / "review-mapping.json").read_text(encoding="utf-8"))
    assert mapping["human_review"] is None and mapping["policy_applicability_decision"] is None
    assert {entry["recipientId"] for entry in mapping["blocked_routes"]} == {
        "report-fraud",
        "ombudsman",
    }
    for item in mapping["policy_windows_and_limits"]:
        assert item.get("computedDueAt") is None and item.get("computedAmount") is None
        assert item["blockReason"]


def test_source_tamper_fails_closed_in_isolated_registry(tmp_path):
    copied = tmp_path / "sources"
    shutil.copytree(SOURCES, copied)
    record = json.loads((copied / "retrievals.json").read_text())[0]
    snapshot = copied / record["snapshot"]
    snapshot.write_bytes(snapshot.read_bytes() + b"tamper")
    with pytest.raises(PackRegistryError, match="snapshot_hash_mismatch"):
        PackRegistry(PACKS, source_root=copied).available(
            allow_draft_preview=True, environment="local", demo_mode=True
        )


def test_pack_can_load_without_touching_global_registry():
    assert load_pack(PACKS / "pack_uk_reimbursement.yaml").status == "draft"
