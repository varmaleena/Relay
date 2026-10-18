"""Contract tests assert source requirements and trust-boundary decisions."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from packages.schemas import Classification, DeadlineState, Money, Pack, PacketStatus, Payment
from services.api.contracts import AnswerRequest, ApproveRequest, DecisionRequest


def test_money_preserves_large_decimal_exactly():
    money = Money(value=Decimal("999999999999.12345678"), currency="INR")
    assert Money.model_validate_json(money.model_dump_json()).value == money.value
    assert '"999999999999.12345678"' in money.model_dump_json()


@pytest.mark.parametrize(
    "value,currency", [("0", "INR"), ("-1", "INR"), ("1", "inr"), ("NaN", "INR")]
)
def test_invalid_money_rejected(value, currency):
    with pytest.raises(ValidationError):
        Money(value=value, currency=currency)


def test_packet_review_failure_has_explicit_state():
    assert PacketStatus("NEEDS_HUMAN_REVIEW") is PacketStatus.NEEDS_HUMAN_REVIEW


def test_ambiguous_authorization_has_question_and_camelcase_roundtrip():
    classification = Classification.model_validate(
        {
            "typology": "bank_impersonation",
            "authorizationType": "unclear",
            "authorizationRationale": "Statements conflict",
            "urgency": {"level": "normal", "reason": "Unknown time"},
            "confidence": 0.4,
            "needsHumanReview": True,
            "clarifyingQuestion": "Did you make the payment?",
        }
    )
    wire = classification.model_dump(by_alias=True)
    assert wire["clarifyingQuestion"] == "Did you make the payment?"
    assert Classification.model_validate(wire) == classification


def test_pack_disk_and_wire_aliases():
    data = {
        "pack_id": "pack_test",
        "version": "1.0.0",
        "jurisdiction": {"code": "ZZ", "name": "Synthetic regime", "archetype": "fragmented"},
        "languages": ["en", "hi"],
        "timezone": "UTC",
        "currency": "USD",
    }
    pack = Pack.model_validate(data)
    assert pack.model_dump()["pack_id"] == "pack_test"
    assert pack.model_dump(by_alias=True)["packId"] == "pack_test"
    assert Pack.model_validate(pack.model_dump(by_alias=True)) == pack


def test_business_calendar_unsupported_is_visible_state():
    deadline = DeadlineState(
        ruleId="test",
        label="Business-day rule",
        type="hard",
        state="unsupported_in_v1",
        statusText="Cannot calculate this rule",
    )
    assert deadline.due_at is None


def test_naive_payment_timestamp_rejected():
    with pytest.raises(ValidationError):
        Payment(timestamp="2026-10-13T10:00:00")


def test_approval_requires_current_version_and_explicit_confirmation():
    with pytest.raises(ValidationError):
        ApproveRequest(confirm=False, confirmedRecipientId="synthetic_bank", packetVersion=1)
    with pytest.raises(ValidationError):
        ApproveRequest(confirm=True, confirmedRecipientId="synthetic_bank", packetVersion=0)


def test_answer_cannot_silently_resend():
    with pytest.raises(ValidationError):
        AnswerRequest(requestId="r", answers=[], ifVersion=1, resend=True)


def test_human_decision_bound_to_packet_version():
    with pytest.raises(ValidationError):
        DecisionRequest(action="acknowledge")
