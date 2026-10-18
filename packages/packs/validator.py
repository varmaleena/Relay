"""Structural/source integrity gates; validation is not legal verification."""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from packages.schemas import Pack

from .deadlines import parse_duration
from .expressions import ExpressionError, compile_expression


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    item_id: str


def validate_pack(
    pack: Pack, passages: set[str], *, for_publish: bool = False
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def issue(code: str, item: str) -> None:
        issues.append(ValidationIssue(code, item))

    if not re.fullmatch(r"\d+\.\d+\.\d+", pack.version):
        issue("invalid_version", pack.pack_id)
    if not pack.languages or not set(pack.languages).issubset({"en", "hi"}):
        issue("unsupported_language", pack.pack_id)
    if not re.fullmatch(r"[A-Z]{3}", pack.currency):
        issue("invalid_currency", pack.pack_id)
    try:
        ZoneInfo(pack.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        issue("invalid_timezone", pack.pack_id)
    all_ids: set[str] = set()
    rules: list[Any] = [*pack.recipients, *pack.sequencing, *pack.deadlines, *pack.liability_rules]
    for item in [*pack.sources, *rules, *pack.forms]:
        if not item.id or item.id in all_ids:
            issue("duplicate_or_empty_id", item.id)
        all_ids.add(item.id)
    source_ids = {x.id for x in pack.sources}
    for source in pack.sources:
        parsed = urlsplit(source.url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or not source.publisher.strip()
            or not source.title.strip()
        ):
            issue("invalid_source_metadata", source.id)
    recipient_ids = {x.id for x in pack.recipients}
    form_ids = {x.id for x in pack.forms}
    for item in [*rules, *pack.crisis_support]:
        item_id = getattr(item, "id", getattr(item, "name", "support"))
        for ref in item.source_refs:
            if ref not in passages or ref.split(":", 1)[0] not in source_ids:
                issue("unresolved_source_ref", item_id)
        if item.status == "verified" and not item.source_refs:
            issue("verified_item_missing_source", item_id)
    for item in pack.recipients:
        if not item.channels or any(not x.value.strip() for x in item.channels):
            issue("empty_channel", item.id)
        if any(x.verified for x in item.channels) and item.status != "verified":
            issue("unverified_recipient_claims_verified_channel", item.id)
        if item.template_id and item.template_id not in form_ids:
            issue("unknown_template", item.id)
        if item.recipient_language not in pack.languages:
            issue("unsupported_recipient_language", item.id)
        if len(item.required_fields) != len(set(item.required_fields)):
            issue("duplicate_required_field", item.id)
    for item in pack.sequencing:
        if item.recipient_id not in recipient_ids:
            issue("unknown_recipient", item.id)
    for item in pack.deadlines:
        if not item.applies_to or not set(item.applies_to).issubset(recipient_ids):
            issue("unknown_recipient", item.id)
        if item.duration is not None:
            try:
                parse_duration(item.duration)
            except ValueError:
                issue("invalid_duration", item.id)
        if item.calendar == "business" and not item.calendar_country:
            issue("missing_calendar_country", item.id)
    for item in pack.forms:
        if item.recipient_id not in recipient_ids:
            issue("unknown_recipient", item.id)
    expressions = (
        [(x.id, x.applies_when) for x in pack.recipients]
        + [(x.id, x.when) for x in pack.sequencing]
        + [(x.id, x.condition) for x in pack.liability_rules]
    )
    for item_id, expression in expressions:
        try:
            compile_expression(expression)
        except ExpressionError:
            issue("unsafe_expression", item_id)
    if for_publish or pack.status == "published":
        if (
            pack.status not in {"reviewed", "published"}
            or not pack.review.reviewer.strip()
            or not pack.review.reviewed_at
        ):
            issue("human_review_required", pack.pack_id)
        try:
            reviewed_at = datetime.fromisoformat(pack.review.reviewed_at.replace("Z", "+00:00"))
            if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
                raise ValueError("review timestamp requires timezone")
        except ValueError:
            issue("invalid_review_timestamp", pack.pack_id)
        accepted = set(pack.review.accepted_unverified_rule_ids)
        unverified = {x.id for x in rules if x.status == "unverified"}
        for item_id in sorted(unverified - accepted):
            issue("unverified_not_accepted", item_id)
        for item_id in sorted(accepted - unverified):
            issue("invalid_unverified_acceptance", item_id)
        if any(x.status == "unverified" for x in pack.crisis_support):
            # Never publish unsupported crisis contacts as usable resources.
            issue("unverified_crisis_support", pack.pack_id)
    return issues


def load_pack(path: Path) -> Pack:
    if path.stat().st_size > 1_000_000:
        raise ValueError("pack exceeds size bound")
    text = path.read_text(encoding="utf-8")
    depth = 0
    for index, event in enumerate(yaml.parse(text)):
        if index > 20000:
            raise ValueError("pack exceeds parse complexity limit")
        if isinstance(event, yaml.events.AliasEvent) or getattr(event, "anchor", None):
            raise ValueError("YAML anchors/aliases are forbidden in packs")
        if isinstance(event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)):
            depth += 1
            if depth > 20:
                raise ValueError("pack exceeds nesting limit")
        elif isinstance(event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)):
            depth -= 1
    body = yaml.safe_load(text)
    return Pack.model_validate(body)
