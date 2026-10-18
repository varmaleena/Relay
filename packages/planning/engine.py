"""Compute recipients and timing without generative or external side effects."""

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal, cast

from packages.packs.deadlines import aware, calculate_deadline, minutes_since_payment
from packages.packs.expressions import compile_expression
from packages.schemas.models import (
    CaseFacts,
    Classification,
    Deadline,
    DeadlineState,
    Pack,
    Plan,
    PlanStep,
    Rule,
)

TYPE_PRIORITY = {
    "bank": 0,
    "payment_app": 1,
    "national_cyber_authority": 2,
    "police": 3,
    "telecom": 4,
    "platform": 5,
    "reimbursement_scheme": 6,
    "ombudsman": 7,
    "support_org": 8,
}
TEXT = {
    "en": {
        "action": "Contact {name} using this pack's listed channel.",
        "why": "This pack rule applies to your recorded details. Check the source before acting.",
        "unverified": "Guidance is unverified. Check an official source before acting.",
        "unknown": "Some details needed for this rule are missing; it was excluded.",
        "sequence_unknown": "The ordering condition is unknown; its order was not applied.",
        "unsupported": "Business-day timing requires human review; no date was calculated.",
        "no_duration": "The source provides no numeric deadline. Check its timing guidance.",
        "missing_event": "The start time is missing; no deadline was calculated.",
        "invalid_time": "Timing needs human review; no deadline was calculated.",
        "overdue": "The recorded deadline has passed. Check the source for the next step.",
        "left": "About {count} {unit} left.",
        "minute": "minutes",
        "hour": "hours",
        "day": "days",
    },
    "hi": {
        "action": "इस पैक में दिए गए माध्यम से {name} से संपर्क करें।",
        "why": "यह पैक नियम आपकी दर्ज जानकारी पर लागू है। कदम उठाने से पहले स्रोत देखें।",
        "unverified": "इस मार्गदर्शन की पुष्टि नहीं हुई है। कदम उठाने से पहले आधिकारिक स्रोत देखें।",
        "unknown": "इस नियम के लिए कुछ जानकारी नहीं है; इसे शामिल नहीं किया गया।",
        "sequence_unknown": "क्रम की शर्त स्पष्ट नहीं है; इसका क्रम लागू नहीं किया गया।",
        "unsupported": "कार्य दिवस की समय सीमा के लिए मानवीय समीक्षा चाहिए; तारीख नहीं निकाली गई।",
        "no_duration": "स्रोत में संख्यात्मक समय सीमा नहीं है। समय का मार्गदर्शन स्रोत में देखें।",
        "missing_event": "शुरुआत का समय नहीं है; समय सीमा नहीं निकाली गई।",
        "invalid_time": "समय के लिए मानवीय समीक्षा चाहिए; समय सीमा नहीं निकाली गई।",
        "overdue": "दर्ज समय सीमा बीत चुकी है। अगला कदम जानने के लिए स्रोत देखें।",
        "left": "लगभग {count} {unit} बाकी हैं।",
        "minute": "मिनट",
        "hour": "घंटे",
        "day": "दिन",
    },
}


def compute(
    *,
    pack: Pack,
    facts: CaseFacts,
    classification: Classification,
    now: datetime,
    language: str = "en",
    source_passages: Mapping[str, str] | None = None,
) -> Plan:
    """UNKNOWN excludes conditional recipients; source gaps suppress numeric deadlines.

    Explicit sequencing precedes urgency and type priority. Multiple matching sequences use their
    lowest step then ID; deadline ties use earliest date, hard before soft, then rule ID.
    Authored templates never copy free-text sequencing rationale into instructions.
    """
    current = aware(now)
    if language not in TEXT:
        raise ValueError("unsupported planner language")
    if pack.status == "retired":
        raise ValueError("retired pack cannot produce a plan")
    rules: list[Rule] = [*pack.recipients, *pack.sequencing, *pack.deadlines]
    ids = [item.id for item in rules]
    if any(not item_id for item_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("planner rule IDs must be nonempty and unique")
    recipients = {item.id for item in pack.recipients}
    if any(item.recipient_id not in recipients for item in pack.sequencing) or any(
        not item.applies_to or not set(item.applies_to) <= recipients for item in pack.deadlines
    ):
        raise ValueError("planner rules reference unknown recipients")
    if len(rules) > 300:
        raise ValueError("planner exceeds rule count bound")
    text = TEXT[language]
    passages = source_passages or {}
    sources = {item.id for item in pack.sources}
    notices: dict[tuple[str, str], dict[str, str]] = {}

    def notice(rule_id: str, code: str) -> None:
        notices[(rule_id, code)] = {"ruleId": rule_id, "code": code, "text": text[code]}

    def verified(rule: Rule) -> bool:
        return (
            pack.status in {"reviewed", "published"}
            and rule.status == "verified"
            and bool(rule.source_refs)
            and all(
                ref.split(":", 1)[0] in sources and bool(passages.get(ref, "").strip())
                for ref in rule.source_refs
            )
        )

    context: dict[str, Any] = {
        "facts": facts.model_dump(mode="python", exclude={"field_provenance"}),
        "classification": classification.model_dump(mode="python"),
        "now": current,
    }
    if facts.payment.timestamp is not None:
        try:
            context["minutes_since_payment"] = minutes_since_payment(
                facts.payment.timestamp, current
            )
        except ValueError:
            notice(pack.pack_id, "invalid_time")
    compiled = {item.id: compile_expression(item.applies_when) for item in pack.recipients} | {
        item.id: compile_expression(item.when) for item in pack.sequencing
    }
    sequence: dict[str, list[tuple[int, str]]] = {}
    for item in sorted(pack.sequencing, key=lambda rule: rule.id):
        applies = compiled[item.id].evaluate(context)
        if applies is None:
            notice(item.id, "sequence_unknown")
        elif applies:
            sequence.setdefault(item.recipient_id, []).append((item.step, item.id))
            if not verified(item):
                notice(item.id, "unverified")

    def deadline_state(rule: Deadline) -> DeadlineState:
        state: Literal["upcoming", "due_soon", "overdue", "not_applicable", "unsupported_in_v1"] = (
            "not_applicable"
        )
        due = None
        if rule.calendar == "business":
            state = "unsupported_in_v1"
            notice(rule.id, "unsupported")
            if not verified(rule):
                notice(rule.id, "unverified")
            status = text["unsupported"]
        elif not verified(rule) or classification.needs_human_review:
            notice(rule.id, "unverified")
            status = text["unverified"]
        elif rule.duration is None:
            status = text["no_duration"]
        else:
            start = (
                facts.payment.timestamp
                if rule.from_event == "payment_timestamp"
                else getattr(facts, rule.from_event)
            )
            try:
                result = calculate_deadline(
                    start=start,
                    duration=rule.duration,
                    now=current,
                    timezone=pack.timezone,
                    calendar_type=rule.calendar,
                )
                due = result.due_at
                state = cast(
                    Literal[
                        "upcoming", "due_soon", "overdue", "not_applicable", "unsupported_in_v1"
                    ],
                    result.state,
                )
                if due is None:
                    notice(rule.id, "missing_event")
                    status = text["missing_event"]
                elif state == "overdue":
                    status = text["overdue"]
                else:
                    seconds = max(0, (due - current).total_seconds())
                    unit, size = (
                        ("day", 86400)
                        if seconds >= 86400
                        else ("hour", 3600)
                        if seconds >= 3600
                        else ("minute", 60)
                    )
                    status = text["left"].format(
                        count=max(1, round(seconds / size)), unit=text[unit]
                    )
            except (ValueError, OverflowError):
                notice(rule.id, "invalid_time")
                status = text["invalid_time"]
        return DeadlineState(
            rule_id=rule.id,
            label=rule.id,
            type=rule.type,
            due_at=due,
            state=state,
            status_text=status,
        )

    ordered = []
    for recipient in pack.recipients:
        applies = compiled[recipient.id].evaluate(context)
        if applies is None:
            notice(recipient.id, "unknown")
            continue
        if not applies:
            continue
        if not recipient.channels or any(
            not channel.value.strip() for channel in recipient.channels
        ):
            raise ValueError("recipient requires a nonempty pack channel")
        trusted = verified(recipient)
        if not trusted:
            notice(recipient.id, "unverified")
        matches = sorted(sequence.get(recipient.id, []))
        order = matches[0][0] if matches else 2**31
        deadlines = [
            (deadline_state(rule), rule)
            for rule in pack.deadlines
            if recipient.id in rule.applies_to
        ]
        deadlines.sort(
            key=lambda pair: (
                pair[0].due_at is None,
                pair[0].due_at or current,
                pair[1].type != "hard",
                pair[1].id,
            )
        )
        selected = deadlines[0][0] if deadlines else None
        refs = [recipient.id, *(item[1] for item in matches), *(rule.id for _, rule in deadlines)]
        source_refs = sorted(
            {
                ref
                for rule in rules
                if rule.id in refs
                for ref in rule.source_refs
                if ref.split(":", 1)[0] in sources and passages.get(ref, "").strip()
            }
        )
        channel = next(
            (channel for channel in recipient.channels if channel.verified), recipient.channels[0]
        ).model_copy(deep=True)
        channel.verified = channel.verified and trusted
        step = PlanStep(
            step_no=0,
            recipient_id=recipient.id,
            action=text["action"].format(name=recipient.name),
            why_now=text["why"] if trusted else text["unverified"],
            channel=channel,
            deadline=selected,
            rule_refs=refs,
            source_refs=source_refs,
        )
        # Case-level model urgency is operational context, never a legal time window.
        # Only source-bound deadlines can distinguish recipients within a sequence tie.
        urgent = classification.urgency.level in {"critical", "high"}
        timing = selected.due_at if selected is not None and urgent else None
        ordered.append(
            (
                (
                    order,
                    timing is None,
                    timing or current,
                    TYPE_PRIORITY[recipient.type],
                    recipient.id,
                ),
                step,
            )
        )
    steps = [step for _, step in sorted(ordered, key=lambda item: item[0])]
    for index, step in enumerate(steps, 1):
        step.step_no = index
    payload = {
        "pack": pack.model_dump(mode="json"),
        "facts": facts.model_dump(mode="json"),
        "classification": classification.model_dump(mode="json"),
        "now": current.isoformat(),
        "language": language,
        "passages": sorted(
            (ref, hashlib.sha256(value.encode()).hexdigest()) for ref, value in passages.items()
        ),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
    return Plan(
        plan_id=f"plan_{digest}",
        pack_id=pack.pack_id,
        pack_version=pack.version,
        pack_status=pack.status,
        generated_at=current,
        steps=steps,
        unverified_notices=[notices[key] for key in sorted(notices)],
    )
