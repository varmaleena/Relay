import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agents.classification import (
    ClassifierAgent,
    FixtureClassifierClient,
    JurisdictionResolver,
    compute_urgency,
)
from packages.schemas.models import CaseFacts, Pack

NOW = datetime(2026, 10, 14, 6, tzinfo=UTC)
CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures/classification/cases.json").read_text(encoding="utf8")
)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_classifier_canonical_fixtures(case):
    result = asyncio.run(
        ClassifierAgent(FixtureClassifierClient(case["modelOutput"])).classify(
            facts=CaseFacts.model_validate(case["facts"]),
            now=NOW,
            language=case["language"],
            transcript_summary=case["narration"],
        )
    )
    assert result.authorization_type == case["expectedAuthorization"]
    assert result.funds_likely_in_system == "unknown"
    assert result.needs_human_review == (result.authorization_type == "unclear")
    assert bool(result.clarifying_question) == result.needs_human_review


@pytest.mark.parametrize(
    "seconds,method,level",
    [
        (7200, "upi", "critical"),
        (7201, "upi", "high"),
        (259200, "bank_transfer", "high"),
        (259201, "bank_transfer", "normal"),
        (60, "card", "high"),
        (-60, "upi", "normal"),
    ],
)
def test_urgency_exact_utc_boundaries(seconds, method, level):
    facts = CaseFacts.model_validate(
        {"payment": {"method": method, "timestamp": (NOW - timedelta(seconds=seconds)).isoformat()}}
    )
    result = compute_urgency(facts, NOW)
    assert result.level == level and "not a legal deadline" in result.reason


def test_conflict_never_labels_self_authorized_as_unauthorized():
    output = dict(CASES[0]["modelOutput"], authorizationType="unauthorized_access")
    result = asyncio.run(
        ClassifierAgent(FixtureClassifierClient(output)).classify(
            facts=CaseFacts.model_validate(CASES[0]["facts"]), now=NOW
        )
    )
    assert result.authorization_type == "unclear" and result.needs_human_review
    assert "conflicts" in result.authorization_rationale


def test_syntax_failure_does_not_request_known_facts():
    result = asyncio.run(
        ClassifierAgent(FixtureClassifierClient({"arbitrary": "invalid"})).classify(
            facts=CaseFacts(), now=NOW, language="hi"
        )
    )
    assert result.confidence == 0 and result.authorization_type == "unclear"
    assert result.clarifying_question is None
    assert result.degraded and result.failure_code == "schema_invalid"


def pack(code="IN", version="1.0.0", status="published", id="india"):
    return Pack(
        pack_id=id,
        version=version,
        status=status,
        jurisdiction={"code": code, "name": "Synthetic", "archetype": "fragmented"},
        languages=["en", "hi"],
        timezone="Asia/Kolkata",
        currency="INR",
    )


def generic():
    return pack(code="ZZ", status="published", id="pack_generic_fragmented")


def test_resolver_published_semver_and_selected_country_wins():
    facts = CaseFacts.model_validate(
        {"country": {"value": "GB", "provenance": {"source": "confirmed"}}}
    )
    result = JurisdictionResolver().resolve(
        packs=[
            generic(),
            pack(version="1.9.0"),
            pack(version="1.10.0"),
            pack(version="2.0.0", status="draft"),
        ],
        facts=facts,
        selected_country="IN",
    )
    assert result.version == "1.10.0" and result.confidence == 1


@pytest.mark.parametrize(
    "source,confidence,confirmation",
    [
        ("victim_statement", None, True),
        ("victim_statement", 0.7, True),
        ("victim_statement", 0.8, False),
        ("inferred", 0.99, True),
        ("confirmed", None, False),
        ("selected", None, False),
    ],
)
def test_country_confidence_not_invented(source, confidence, confirmation):
    facts = CaseFacts.model_validate(
        {"country": {"value": "IN", "provenance": {"source": source, "confidence": confidence}}}
    )
    result = JurisdictionResolver().resolve(packs=[generic(), pack()], facts=facts)
    assert result.needs_country_confirmation == confirmation
    assert (result.pack_id == "pack_generic_fragmented") == confirmation


def test_language_currency_cannot_select_country():
    facts = CaseFacts.model_validate(
        {"languages": ["hi"], "payment": {"amount": {"value": "1", "currency": "INR"}}}
    )
    result = JurisdictionResolver().resolve(packs=[generic(), pack()], facts=facts)
    assert result.pack_id == "pack_generic_fragmented" and result.needs_country_confirmation


def test_draft_country_pack_requires_explicit_id_optin():
    resolver = JurisdictionResolver()
    packs = [generic(), pack(status="draft")]
    with pytest.raises(ValueError, match="opt_in"):
        resolver.resolve(
            packs=packs, facts=CaseFacts(), selected_country="IN", demo_pack_id="india"
        )
    result = resolver.resolve(
        packs=packs,
        facts=CaseFacts(),
        selected_country="IN",
        demo_pack_id="india",
        allow_draft_demo=True,
    )
    assert result.unverified and "draft" in result.notice.lower()


def test_retired_pack_never_selected():
    result = JurisdictionResolver().resolve(
        packs=[generic(), pack(status="retired")], facts=CaseFacts(), selected_country="IN"
    )
    assert result.pack_id == "pack_generic_fragmented" and result.unverified


@pytest.mark.parametrize("environment,demo", [("dev", True), ("local", False)])
def test_draft_preview_local_demo_boundary(environment, demo):
    with pytest.raises(ValueError, match="local_only"):
        JurisdictionResolver().resolve(
            packs=[pack(status="draft", id="pack_generic_fragmented")],
            facts=CaseFacts(),
            allow_draft_demo=True,
            environment=environment,
            demo_mode=demo,
        )


def test_generic_draft_not_silently_promoted():
    packs = [pack(code="ZZ", status="draft", id="pack_generic_fragmented")]
    with pytest.raises(ValueError, match="generic_pack_missing"):
        JurisdictionResolver().resolve(packs=packs, facts=CaseFacts())
    result = JurisdictionResolver().resolve(packs=packs, facts=CaseFacts(), allow_draft_demo=True)
    assert result.unverified and result.pack.status == "draft"


def test_known_fact_conflicts_from_multiple_turns_require_review():
    output = dict(CASES[0]["modelOutput"], authorizationType="unauthorized_access")
    history = [
        {"text": "I sent the transfer myself.", "at": NOW.isoformat()},
        {"text": "Someone else accessed my account too.", "at": NOW.isoformat()},
    ]
    result = asyncio.run(
        ClassifierAgent(FixtureClassifierClient(output)).classify(
            facts=CaseFacts.model_validate(CASES[0]["facts"]), now=NOW, history=history
        )
    )
    assert result.needs_human_review and result.confidence < 0.7


def test_unknown_authorization_cannot_be_invented_from_model_confidence():
    facts = CaseFacts.model_validate({"payment": {"method": "upi"}})
    result = asyncio.run(
        ClassifierAgent(FixtureClassifierClient(CASES[0]["modelOutput"])).classify(
            facts=facts, now=NOW
        )
    )
    assert result.authorization_type == "unclear" and result.clarifying_question


@pytest.mark.parametrize("country,confidence", [(None, None), ("IN", 0.6), ("XX", None)])
def test_country_draft_never_bypasses_confirmation(country, confidence):
    facts = (
        CaseFacts()
        if not country
        else CaseFacts.model_validate(
            {
                "country": {
                    "value": country,
                    "provenance": {"source": "victim_statement", "confidence": confidence},
                }
            }
        )
    )
    result = JurisdictionResolver().resolve(
        packs=[generic(), pack(status="draft")],
        facts=facts,
        demo_pack_id="india",
        allow_draft_demo=True,
    )
    assert result.pack_id == "pack_generic_fragmented" and result.needs_country_confirmation


def test_model_unavailable_with_known_authorization_is_not_fact_ambiguity():
    from agents.intake.clients import ModelFailure

    class FailingClient(FixtureClassifierClient):
        async def generate(self, **kwargs):
            raise ModelFailure("model_unavailable:504")

    facts = CaseFacts.model_validate(CASES[0]["facts"])
    result = asyncio.run(ClassifierAgent(FailingClient({})).classify(facts=facts, now=NOW))
    assert result.degraded and result.failure_code == "model_unavailable"
    assert result.clarifying_question is None
    assert facts.payment.authorized_by_victim is True
    assert "Existing facts remain saved" in result.authorization_rationale


def test_real_unknown_authorization_is_not_model_degradation():
    output = dict(CASES[0]["modelOutput"], authorizationType="unclear")
    result = asyncio.run(
        ClassifierAgent(FixtureClassifierClient(output)).classify(facts=CaseFacts(), now=NOW)
    )
    assert not result.degraded and result.failure_code is None
    assert result.needs_human_review and result.clarifying_question


def test_model_cannot_forge_transport_failure_or_success():
    output = dict(CASES[0]["modelOutput"], degraded=True, failureCode="model_unavailable")
    result = asyncio.run(
        ClassifierAgent(FixtureClassifierClient(output)).classify(
            facts=CaseFacts.model_validate(CASES[0]["facts"]), now=NOW
        )
    )
    assert not result.degraded and result.failure_code is None
    from agents.intake.clients import provider_schema
    from packages.schemas.models import Classification

    projected = provider_schema(Classification)
    assert (
        "degraded" not in projected["properties"] and "failureCode" not in projected["properties"]
    )


def test_unsafe_model_output_is_degraded_without_question():
    output = dict(CASES[0]["modelOutput"], authorizationRationale="Guaranteed refund")
    result = asyncio.run(
        ClassifierAgent(FixtureClassifierClient(output)).classify(
            facts=CaseFacts.model_validate(CASES[0]["facts"]), now=NOW
        )
    )
    assert result.degraded and result.failure_code == "unsafe_output"
    assert result.clarifying_question is None


@pytest.mark.parametrize("language", ["en", "hi"])
@pytest.mark.parametrize("authorized", [True, False, None])
def test_low_confidence_clarifier_respects_known_authorization(language, authorized):
    facts = CaseFacts.model_validate(
        {"payment": {"method": "upi", "authorizedByVictim": authorized}}
    )
    output = dict(
        CASES[0]["modelOutput"],
        confidence=0.5,
        authorizationType="authorized_manipulated"
        if authorized
        else "unauthorized_access"
        if authorized is False
        else "unclear",
    )
    result = asyncio.run(
        ClassifierAgent(FixtureClassifierClient(output)).classify(
            facts=facts, now=NOW, language=language
        )
    )
    assert result.needs_human_review and not result.degraded
    from agents.classification.classifier import KNOWN_AUTH_QUESTIONS, QUESTIONS

    assert result.clarifying_question == (
        QUESTIONS[language] if authorized is None else KNOWN_AUTH_QUESTIONS[authorized][language]
    )
    from packages.safety import SafetyGuard

    assert SafetyGuard().inspect_output(result.clarifying_question).allow


def test_gambia_is_known_country_without_india_inference():
    facts = CaseFacts.model_validate(
        {"country": {"value": "GM", "provenance": {"source": "confirmed"}}}
    )
    result = JurisdictionResolver().resolve(packs=[generic(), pack()], facts=facts)
    assert result.pack_id == "pack_generic_fragmented"
    assert result.confidence == 1 and not result.needs_country_confirmation


def test_malformed_model_country_requests_confirmation_not_worker_failure():
    facts = CaseFacts.model_validate(
        {
            "country": {
                "value": "India",
                "provenance": {"source": "victim_statement", "confidence": 0.99},
            }
        }
    )
    result = JurisdictionResolver().resolve(packs=[generic(), pack()], facts=facts)
    assert result.pack_id == "pack_generic_fragmented"
    assert result.needs_country_confirmation and result.confidence == 0


def test_invalid_explicit_country_still_rejected():
    with pytest.raises(ValueError, match="invalid_selected_country"):
        JurisdictionResolver().resolve(
            packs=[generic()], facts=CaseFacts(), selected_country="India"
        )
