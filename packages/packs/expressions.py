"""Bounded AST interpreter over plain dictionaries; never Python eval/attributes."""

import ast
import math
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo


class ExpressionError(ValueError):
    pass


class _Unknown:
    pass


UNKNOWN = _Unknown()
ROOTS = {"facts", "classification", "minutes_since_payment", "now"}
FUNCTIONS = {"len", "lower", "contains", "exists"}
OPERATORS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn)
# Explicit canonical snake_case schema paths, not arbitrary document attributes.
SCHEMA_PATHS = {
    "facts",
    "facts.country",
    "facts.country.value",
    "facts.country.availability",
    "facts.country.provenance",
    "facts.country.provenance.source",
    "facts.country.provenance.reference",
    "facts.country.provenance.confidence",
    "facts.payment",
    "facts.payment.method",
    "facts.payment.amount",
    "facts.payment.amount.value",
    "facts.payment.amount.currency",
    "facts.payment.timestamp",
    "facts.payment.authorized_by_victim",
    "facts.payment.recipient_identifier",
    "facts.payment.recipient_identifier.type",
    "facts.payment.recipient_identifier.value",
    "facts.payment.transaction_ref",
    "facts.contact",
    "facts.contact.channel",
    "facts.contact.identifier",
    "facts.contact.claimed_identity",
    "facts.victim_bank",
    "facts.ongoing_contact",
    "facts.credentials_shared",
    "facts.victim_age_band",
    "facts.languages",
    "facts.discovery_timestamp",
    "facts.report_timestamp",
    "facts.unavailable_fields",
    "classification",
    "classification.typology",
    "classification.authorization_type",
    "classification.authorization_rationale",
    "classification.urgency",
    "classification.urgency.level",
    "classification.urgency.reason",
    "classification.funds_likely_in_system",
    "classification.vulnerability_flags",
    "classification.confidence",
    "classification.needs_human_review",
    "classification.clarifying_question",
    "minutes_since_payment",
    "now",
}


def _path(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return _path(node.value) + [node.attr]
    raise ExpressionError("only dictionary field paths are allowed")


def _valid_path(parts: list[str]) -> bool:
    return ".".join(parts) in SCHEMA_PATHS


def _validate(node: ast.AST) -> None:
    if isinstance(node, ast.Expression):
        _validate(node.body)
    elif isinstance(node, (ast.Name, ast.Attribute)):
        parts = _path(node)
        if not _valid_path(parts) or (
            len(parts) > 1 and parts[0] not in {"facts", "classification"}
        ):
            raise ExpressionError("unknown or forbidden field path")
    elif isinstance(node, ast.Constant):
        if (
            not isinstance(node.value, (str, int, float, bool, type(None)))
            or len(str(node.value)) > 128
        ):
            raise ExpressionError("unsupported or oversized literal")
    elif isinstance(node, (ast.List, ast.Tuple)):
        if len(node.elts) > 32 or any(not isinstance(x, ast.Constant) for x in node.elts):
            raise ExpressionError("lists may contain at most 32 literal values")
        for child in node.elts:
            _validate(child)
    elif isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        for child in node.values:
            _validate(child)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        _validate(node.operand)
    elif isinstance(node, ast.Compare) and all(isinstance(op, OPERATORS) for op in node.ops):
        _validate(node.left)
        for child in node.comparators:
            _validate(child)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
            raise ExpressionError("function is not permitted")
        expected = 2 if node.func.id == "contains" else 1
        if len(node.args) != expected:
            raise ExpressionError("wrong function arity")
        if node.func.id == "exists":
            arg = node.args[0]
            if (
                not isinstance(arg, ast.Constant)
                or not isinstance(arg.value, str)
                or not _valid_path(arg.value.split("."))
            ):
                raise ExpressionError("exists requires a quoted safe field path")
        for child in node.args:
            _validate(child)
    else:
        raise ExpressionError(f"syntax {type(node).__name__} is not permitted")


def _bounded(value: Any, depth: int = 0, nodes: list[int] | None = None) -> Any:
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if depth > 8 or nodes[0] > 1000:
        raise ExpressionError("rule input nesting or node bound exceeded")
    kind = type(value)
    if kind is str and len(value) <= 4000:
        return value
    if kind in {list, tuple} and len(value) <= 100:
        return [_bounded(item, depth + 1, nodes) for item in value]
    if kind is dict and len(value) <= 100:
        if any(type(key) is not str or len(key) > 128 for key in value):
            raise ExpressionError("rule dictionary keys must be bounded plain strings")
        return {key: _bounded(item, depth + 1, nodes) for key, item in value.items()}
    if kind is Decimal:
        if not value.is_finite():
            raise ExpressionError("non-finite decimal")
        digits = value.as_tuple().digits
        exponent = value.as_tuple().exponent
        if (
            not isinstance(exponent, int)
            or len(digits) > 20
            or exponent < -8
            or value.adjusted() > 19
        ):
            raise ExpressionError("decimal exceeds canonical money bounds")
        return value
    if kind is datetime:
        if type(value.tzinfo) not in {timezone, ZoneInfo} or value.utcoffset() is None:
            raise ExpressionError("datetime requires a trusted aware timezone")
        return value.astimezone(UTC)
    if value is None or kind is bool:
        return value
    if kind is int and value.bit_length() <= 256:
        return value
    if kind is float:
        if math.isfinite(value):
            return value
    raise ExpressionError("rule inputs must be bounded plain scalar values")


@dataclass(frozen=True)
class Expression:
    tree: ast.Expression

    def evaluate(self, context: Mapping[str, Any], *, timeout_ms: float = 50) -> bool | None:
        if (
            type(timeout_ms) not in {int, float}
            or not math.isfinite(timeout_ms)
            or timeout_ms <= 0
            or timeout_ms > 50
        ):
            raise ExpressionError("evaluation budget must be between 0 and 50 ms")
        stop = time.monotonic() + timeout_ms / 1000

        def lookup(parts: list[str]) -> Any:
            value: Any = context
            for part in parts:
                if type(value) is not dict:
                    if value is None:
                        return UNKNOWN
                    raise ExpressionError("rule paths require exact builtin dictionaries")
                if part not in value:
                    return UNKNOWN
                value = value[part]
            return _bounded(value)

        def truth(value: Any) -> bool | _Unknown:
            if value is UNKNOWN or value is None:
                return UNKNOWN
            return bool(value)

        def walk(node: ast.AST) -> Any:
            if time.monotonic() >= stop:
                raise ExpressionError("evaluation time budget exceeded")
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, (ast.Name, ast.Attribute)):
                return lookup(_path(node))
            if isinstance(node, (ast.List, ast.Tuple)):
                return [walk(child) for child in node.elts]
            if isinstance(node, ast.UnaryOp):
                value = truth(walk(node.operand))
                return UNKNOWN if value is UNKNOWN else not value
            if isinstance(node, ast.BoolOp):
                unknown = False
                for child in node.values:
                    value = truth(walk(child))
                    if value is UNKNOWN:
                        unknown = True
                    elif isinstance(node.op, ast.And) and not value:
                        return False
                    elif isinstance(node.op, ast.Or) and value:
                        return True
                return UNKNOWN if unknown else isinstance(node.op, ast.And)
            if isinstance(node, ast.Compare):
                left = walk(node.left)
                unknown = False
                for op, child in zip(node.ops, node.comparators, strict=True):
                    right = walk(child)
                    if left is UNKNOWN or right is UNKNOWN or left is None or right is None:
                        unknown = True
                    else:
                        try:
                            if isinstance(op, ast.Eq):
                                result = left == right
                            elif isinstance(op, ast.NotEq):
                                result = left != right
                            elif isinstance(op, ast.Lt):
                                result = left < right
                            elif isinstance(op, ast.LtE):
                                result = left <= right
                            elif isinstance(op, ast.Gt):
                                result = left > right
                            elif isinstance(op, ast.GtE):
                                result = left >= right
                            elif isinstance(op, ast.In):
                                result = left in right
                            else:
                                result = left not in right
                        except (TypeError, ValueError) as exc:
                            raise ExpressionError("incompatible rule operands") from exc
                        if not result:
                            return False
                    left = right
                return UNKNOWN if unknown else True
            if isinstance(node, ast.Call):
                assert isinstance(node.func, ast.Name)
                name = node.func.id
                args = [walk(arg) for arg in node.args]
                if name == "exists":
                    value = lookup(args[0].split("."))
                    return value is not UNKNOWN and value is not None
                if any(x is UNKNOWN or x is None for x in args):
                    return UNKNOWN
                try:
                    if name == "len":
                        return len(args[0])
                    if name == "lower":
                        if type(args[0]) is not str:
                            raise TypeError
                        return args[0].lower()
                    return args[1] in args[0]
                except TypeError as exc:
                    raise ExpressionError("invalid function input") from exc
            raise ExpressionError("invalid compiled expression")

        result = truth(walk(self.tree.body))
        if time.monotonic() >= stop:
            raise ExpressionError("evaluation time budget exceeded")
        return None if result is UNKNOWN else bool(result)


def compile_expression(text: str) -> Expression:
    if type(text) is not str or not text or len(text) > 300:
        raise ExpressionError("expression length must be 1–300 characters")
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, RecursionError) as exc:
        raise ExpressionError("invalid expression") from exc
    if len(list(ast.walk(tree))) > 120:
        raise ExpressionError("expression is too complex")
    _validate(tree)
    return Expression(tree)
