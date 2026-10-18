"""Attack-oriented tests for rule interpreter trust and resource boundaries."""

from datetime import UTC, datetime, timedelta, tzinfo
from decimal import Decimal

import pytest

from packages.packs.expressions import ExpressionError, compile_expression
from packages.schemas import CaseFacts, Money, Payment


@pytest.mark.parametrize(
    "expression",
    [
        "facts.misspelled == 1",
        "classification.unknown",
        "exists('now.year')",
        "exists('facts.misspelled')",
        "facts.payment.amount.valeu > 0",
    ],
)
def test_unknown_schema_paths_rejected_at_compile(expression):
    with pytest.raises(ExpressionError):
        compile_expression(expression)


def test_known_but_unprovided_field_remains_unknown():
    assert compile_expression("facts.victim_bank == 'Test'").evaluate({"facts": {}}) is None
    assert (
        compile_expression("exists('facts.payment.amount.value')").evaluate(
            {"facts": {"payment": {"amount": None}}}
        )
        is False
    )


def test_python_subclasses_never_execute_side_effects():
    calls = []

    class EvilString(str):
        def __eq__(self, other):
            calls.append("comparison")
            return True

    class EvilDict(dict):
        def __contains__(self, key):
            calls.append("contains")
            return True

    class EvilList(list):
        def __len__(self):
            calls.append("length")
            return 0

    cases = [
        ("facts.victim_bank == 1", {"facts": {"victim_bank": EvilString("hostile")}}),
        ("facts.victim_bank", {"facts": EvilDict(victim_bank="fake")}),
        ("len(facts.languages) == 0", {"facts": {"languages": EvilList(["hi"])}}),
        ("contains(facts.languages, 'hi')", {"facts": {"languages": [EvilString("hi")]}}),
    ]
    for expression, context in cases:
        with pytest.raises(ExpressionError):
            compile_expression(expression).evaluate(context)
    assert calls == []


def test_real_casefacts_money_and_timestamp_compatible_without_float_conversion():
    facts = CaseFacts(
        payment=Payment(
            method="upi",
            amount=Money(value="999999999999.12345678", currency="INR"),
            timestamp=datetime(2026, 10, 13, tzinfo=UTC),
        )
    )
    context = {"facts": facts.model_dump(), "now": datetime(2026, 10, 14, tzinfo=UTC)}
    assert compile_expression("facts.payment.amount.value > 999999999999").evaluate(context) is True
    assert (
        compile_expression("facts.payment.amount.value < 1000000000000").evaluate(context) is True
    )
    assert compile_expression("facts.payment.timestamp < now").evaluate(context) is True


@pytest.mark.parametrize(
    "value",
    [
        Decimal("NaN"),
        Decimal("1e1000000"),
        Decimal("1e-1000000"),
        Decimal("123456789012345678901"),
        1 << 1000,
        float("nan"),
        ["x" * 4001],
        ["hi"] * 101,
    ],
)
def test_scalar_and_container_resource_bounds(value):
    with pytest.raises(ExpressionError):
        compile_expression("facts.languages").evaluate({"facts": {"languages": value}})


def test_recursive_cycle_rejected_without_overflow():
    cycle = {}
    cycle["cycle"] = cycle
    with pytest.raises(ExpressionError):
        compile_expression("facts.payment").evaluate({"facts": {"payment": cycle}})


def test_custom_timezone_not_invoked():
    calls = []

    class EvilTimezone(tzinfo):
        def utcoffset(self, dt):
            calls.append("offset")
            return timedelta()

    with pytest.raises(ExpressionError):
        compile_expression("now").evaluate({"now": datetime(2026, 10, 13, tzinfo=EvilTimezone())})
    assert calls == []


def test_operation_completion_checks_same_time_budget(monkeypatch):
    # Clock expires after the last AST walk check, so a post-operation check is
    # necessary even though operands and operations are restricted builtins.
    times = iter([0.0, 0.0, 0.051])
    monkeypatch.setattr("packages.packs.expressions.time.monotonic", lambda: next(times))
    with pytest.raises(ExpressionError, match="time budget"):
        compile_expression("True").evaluate({})
