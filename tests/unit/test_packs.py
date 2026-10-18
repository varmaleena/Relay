from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from packages.packs import (
    calculate_deadline,
    compile_expression,
    load_pack,
    minutes_since_payment,
    parse_duration,
    validate_pack,
)
from packages.packs.deadlines import add_duration
from packages.packs.expressions import ExpressionError
from packages.schemas import Pack


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("True", True),
        ("False", False),
        ("facts.payment.method in ['upi', 'card']", True),
        ("classification.authorization_type == 'authorized_manipulated'", True),
        ("minutes_since_payment <= 120 and facts.payment.amount.value > 0", True),
        ("not facts.ongoing_contact", True),
        ("lower(facts.victim_bank) == 'test'", True),
        ("contains(facts.victim_bank, 'EST')", True),
        ("len(facts.victim_bank) >= 4", True),
        ("exists('facts.payment.method')", True),
        ("exists('facts.victim_age_band')", False),
        ("facts.victim_age_band == 'anything'", None),
        ("facts.victim_age_band != 'anything'", None),
        ("False and facts.victim_age_band", False),
        ("True or facts.victim_age_band", True),
        ("True and facts.victim_age_band", None),
        ("False or facts.victim_age_band", None),
        ("not facts.victim_age_band", None),
        ("0 < minutes_since_payment < 120", True),
        ("minutes_since_payment not in [1, 2]", True),
    ],
)
def test_rules(expression, expected):
    context = {
        "facts": {
            "payment": {"method": "upi", "amount": {"value": 45000}},
            "victim_bank": "TEST",
            "ongoing_contact": False,
        },
        "classification": {"authorization_type": "authorized_manipulated"},
        "minutes_since_payment": 20,
    }
    assert compile_expression(expression).evaluate(context) is expected


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('whoami')",
        "facts.__class__",
        "facts.payment.__dict__",
        "facts['payment']",
        "[x for x in facts]",
        "facts.method + 'x'",
        "2 ** 100000",
        "(lambda: True)()",
        "open('/file')",
        "payment.method == 'upi'",
        "now.year == 2026",
        "lower(x='abc')",
        "contains('a')",
        "exists('facts.__class__')",
        "exists(facts.path)",
        "facts..method",
        "",
        "x" * 301,
    ],
)
def test_malicious_expressions_are_rejected(expression):
    with pytest.raises(ExpressionError):
        compile_expression(expression)


def test_bounded_plain_input_and_type_errors():
    class Hostile:
        def __bool__(self):
            raise AssertionError("must never execute user object")

    with pytest.raises(ExpressionError):
        compile_expression("facts.victim_bank").evaluate({"facts": {"victim_bank": Hostile()}})
    with pytest.raises(ExpressionError):
        compile_expression("facts.victim_bank").evaluate({"facts": {"victim_bank": "x" * 4001}})
    with pytest.raises(ExpressionError):
        compile_expression("facts.victim_bank < 10").evaluate({"facts": {"victim_bank": "text"}})
    with pytest.raises(ExpressionError):
        compile_expression("lower(facts.victim_bank)").evaluate({"facts": {"victim_bank": 10}})
    with pytest.raises(ExpressionError):
        compile_expression("True").evaluate({}, timeout_ms=0)


@pytest.mark.parametrize(
    "value", ["P", "PT", "P0D", "P-1D", "PT1HT", "P1W1D", "P101Y", "P1.5D", "1 hour"]
)
def test_invalid_durations(value):
    with pytest.raises(ValueError):
        parse_duration(value)


def test_calendar_month_leap_clamp_and_elapsed_time():
    assert add_duration(
        datetime(2024, 1, 31, tzinfo=UTC), parse_duration("P1M"), "UTC"
    ) == datetime(2024, 2, 29, tzinfo=UTC)
    assert add_duration(
        datetime(2024, 2, 29, tzinfo=UTC), parse_duration("P1Y"), "UTC"
    ) == datetime(2025, 2, 28, tzinfo=UTC)
    assert add_duration(
        datetime(2026, 10, 13, tzinfo=UTC), parse_duration("PT1.5S"), "UTC"
    ) == datetime(2026, 10, 13, 0, 0, 1, 500000, tzinfo=UTC)


def test_dst_calendar_day_differs_from_elapsed_24_hours():
    start = datetime.fromisoformat("2026-03-28T12:00:00+00:00")
    assert add_duration(start, parse_duration("P1D"), "Europe/London") == datetime(
        2026, 3, 29, 11, tzinfo=UTC
    )
    assert add_duration(start, parse_duration("PT24H"), "Europe/London") == datetime(
        2026, 3, 29, 12, tzinfo=UTC
    )
    with pytest.raises(ValueError, match="DST gap"):
        add_duration(
            datetime(2026, 3, 28, 1, 30, tzinfo=UTC), parse_duration("P1D"), "Europe/London"
        )


def test_deadline_states_and_unsupported_or_unknown_dates():
    start = datetime(2026, 10, 13, tzinfo=UTC)

    def result(hours, **extra):
        return calculate_deadline(
            start=start,
            duration="PT4H",
            now=start + timedelta(hours=hours),
            timezone="UTC",
            **extra,
        )

    assert result(0).state == "upcoming"
    assert result(3).state == "due_soon"
    assert result(4).state == "due_soon"
    assert result(4.1).state == "overdue"
    assert result(0, calendar_type="business").state == "unsupported_in_v1"
    assert (
        calculate_deadline(start=None, duration="P1D", now=start, timezone="UTC").notice
        == "start_event_missing"
    )
    assert calculate_deadline(start=start, duration=None, now=start, timezone="UTC").due_at is None
    with pytest.raises(ValueError):
        result(-1)
    with pytest.raises(ValueError):
        result(0, calendar_type="guess")
    assert minutes_since_payment(start, start + timedelta(minutes=20, seconds=59)) == 20
    with pytest.raises(ValueError):
        minutes_since_payment(start, start - timedelta(seconds=1))
    with pytest.raises(ValueError):
        minutes_since_payment(datetime(2026, 10, 13), start)


@pytest.fixture
def pack_data():
    # Test-only invented regime, never a real jurisdiction/legal assertion.
    return {
        "pack_id": "pack_test",
        "version": "1.0.0",
        "status": "draft",
        "jurisdiction": {"code": "ZZ", "name": "Synthetic test regime", "archetype": "fragmented"},
        "languages": ["en", "hi"],
        "timezone": "UTC",
        "currency": "INR",
        "sources": [
            {
                "id": "src",
                "title": "Synthetic fixture",
                "publisher": "Test",
                "url": "https://example.com",
                "retrieved_at": "2026-10-13",
                "sha256": "a" * 64,
            }
        ],
        "recipients": [
            {
                "id": "bank",
                "type": "bank",
                "name": "Test Bank",
                "channels": [{"type": "app", "value": "Synthetic test app", "verified": False}],
                "status": "verified",
                "source_refs": ["src:p1"],
                "template_id": "form",
            }
        ],
        "forms": [{"id": "form", "recipient_id": "bank", "fields": ["amount"]}],
        "sequencing": [
            {
                "id": "sequence",
                "step": 1,
                "recipient_id": "bank",
                "rationale": "Synthetic test only",
                "status": "verified",
                "source_refs": ["src:p1"],
            }
        ],
        "deadlines": [
            {
                "id": "deadline",
                "applies_to": ["bank"],
                "from_event": "payment_timestamp",
                "duration": "P1D",
                "type": "soft",
                "consequence": "Synthetic deadline only",
                "status": "unverified",
            }
        ],
    }


def codes(data, **kwargs):
    return {x.code for x in validate_pack(Pack.model_validate(data), {"src:p1"}, **kwargs)}


def test_pack_draft_and_publication_review_gate(pack_data):
    assert not codes(pack_data)
    assert {"human_review_required", "unverified_not_accepted"}.issubset(
        codes(pack_data, for_publish=True)
    )
    pack_data["status"] = "reviewed"
    pack_data["review"] = {
        "reviewer": "Synthetic test reviewer",
        "reviewed_at": "2026-10-13T00:00:00Z",
        "accepted_unverified_rule_ids": ["deadline"],
    }
    assert not codes(pack_data, for_publish=True)
    assert Pack.model_validate(pack_data).deadlines[0].status == "unverified"
    pack_data["review"]["accepted_unverified_rule_ids"].append("invented")
    assert "invalid_unverified_acceptance" in codes(pack_data, for_publish=True)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (lambda p: p.update(version="latest"), "invalid_version"),
        (lambda p: p.update(timezone="Not/AZone"), "invalid_timezone"),
        (lambda p: p.update(currency="bad"), "invalid_currency"),
        (lambda p: p.update(languages=["unknown"]), "unsupported_language"),
        (lambda p: p["recipients"][0].update(source_refs=[]), "verified_item_missing_source"),
        (lambda p: p["recipients"][0].update(source_refs=["src:missing"]), "unresolved_source_ref"),
        (lambda p: p["recipients"][0].update(channels=[]), "empty_channel"),
        (lambda p: p["recipients"][0].update(applies_when="__import__('os')"), "unsafe_expression"),
        (lambda p: p["recipients"][0].update(template_id="missing"), "unknown_template"),
        (lambda p: p["sequencing"][0].update(recipient_id="missing"), "unknown_recipient"),
        (lambda p: p["deadlines"][0].update(duration="not a duration"), "invalid_duration"),
        (lambda p: p["deadlines"][0].update(calendar="business"), "missing_calendar_country"),
        (lambda p: p["forms"][0].update(id="bank"), "duplicate_or_empty_id"),
    ],
)
def test_pack_invalid_integrity(pack_data, mutation, expected):
    mutation(pack_data)
    assert expected in codes(pack_data)


def test_pack_loader_rejects_executable_yaml(tmp_path):
    path = tmp_path / "malicious.yaml"
    path.write_text("!!python/object/apply:os.system ['whoami']", encoding="utf-8")
    import yaml

    with pytest.raises(yaml.YAMLError):
        load_pack(path)


def test_pack_loader_valid_yaml(pack_data, tmp_path):
    import yaml

    path: Path = tmp_path / "fixture.yaml"
    path.write_text(yaml.safe_dump(pack_data), encoding="utf-8")
    assert load_pack(path).pack_id == "pack_test"
