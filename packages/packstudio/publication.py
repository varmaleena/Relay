"""Human canonical mapping is explicit; AI extraction never becomes a rule by default."""

import re

from pydantic import ValidationError

from packages.intake.service import IntakeError
from packages.packs.validator import validate_pack
from packages.schemas import Pack

from .adapter import PASSES


def prepare_publication(build, body, sources, now):
    checklist = body.get("reviewChecklist")
    if (
        type(checklist) is not dict
        or set(checklist)
        != {"sourcesChecked", "contactsChecked", "scopeConditionsChecked", "languagesChecked"}
        or any(value is not True for value in checklist.values())
        or not body.get("reviewerName", "").strip()
        or type(body.get("notes")) is not str
        or len(body["notes"]) > 4000
    ):
        raise IntakeError(422, "human_review_required")
    raw = body.get("packDraft")
    if type(raw) is not dict or not {
        "packId",
        "version",
        "jurisdiction",
        "languages",
        "timezone",
        "currency",
        "disclaimers",
        "sources",
        "recipients",
    } <= set(raw):
        raise IntakeError(422, "canonical_pack_required")
    for section, condition in (
        ("recipients", "appliesWhen"),
        ("sequencing", "when"),
        ("liabilityRules", "condition"),
    ):
        if any(
            type(item) is not dict
            or condition not in item
            or not isinstance(item[condition], str)
            or not item[condition].strip()
            for item in raw.get(section, [])
        ):
            raise IntakeError(422, "explicit_conditions_required")
    try:
        pack = Pack.model_validate(raw)
    except ValidationError:
        raise IntakeError(422, "pack_validation_failed") from None
    if (
        pack.status != "draft"
        or not re.fullmatch(r"pack_[a-z][a-z0-9_-]{0,79}", pack.pack_id)
        or not re.fullmatch(r"\d+\.\d+\.\d+", pack.version)
        or not pack.recipients
        or not pack.disclaimers
        or pack.jurisdiction.code != build["request"]["jurisdictionCode"]
        or pack.jurisdiction.archetype != build["request"]["archetype"]
        or [s.model_dump(mode="json", by_alias=True) for s in pack.sources]
        != [s.source.model_dump(mode="json", by_alias=True) for s in sources]
    ):
        raise IntakeError(422, "pack_validation_failed")
    result = build["result"]
    candidates = {item["id"]: (name, item) for name in PASSES for item in result[name]["items"]}
    if set(candidates) != set(build["reviews"]):
        raise IntakeError(422, "human_review_required")
    accepted = {key for key, review in build["reviews"].items() if review["state"] != "rejected"}
    verdicts = {item["itemId"]: item["verdict"]["verdict"] for item in result["review"]}
    consumed = set()
    names = {item.name: item.id for item in pack.recipients}
    if len(names) != len(pack.recipients):
        raise IntakeError(422, "pack_validation_failed")

    def bind(item, section):
        candidate = candidates.get(item.id)
        if (
            item.id not in accepted
            or not candidate
            or candidate[0] != section
            or set(item.source_refs) != set(candidate[1]["sourceRefs"])
        ):
            raise IntakeError(422, "canonical_mapping_invalid")
        consumed.add(item.id)
        if item.status == "verified" and (
            verdicts[item.id] != "SUPPORTED"
            or build["reviews"][item.id].get("edited", False)
            or candidate[1].get("conflict")
            or candidate[1].get("ambiguous")
        ):
            raise IntakeError(422, "unverified_status_required")
        return candidate[1]

    for recipient in pack.recipients:
        candidate = bind(recipient, "recipients")
        if (
            recipient.name != candidate["name"]
            or recipient.type != candidate["recipientType"]
            or [(c.type, c.value) for c in recipient.channels]
            != [(c["type"], c["value"]) for c in candidate["channels"]]
        ):
            raise IntakeError(422, "canonical_mapping_invalid")
        from agents.packets.core import PACKET_COMMON_FIELDS

        if any(
            key not in PACKET_COMMON_FIELDS
            or re.search(r"(?i)account|otp|pin|password|cvv|card", key)
            for key in recipient.required_fields
        ):
            raise IntakeError(422, "unsupported_field_mapping")
    for sequence in pack.sequencing:
        candidate = bind(sequence, "sequencing")
        if (
            sequence.recipient_id != names.get(candidate["recipientName"])
            or sequence.rationale != candidate["rationale"]
            or candidate["order"] is None
            or sequence.step != candidate["order"]
        ):
            raise IntakeError(422, "canonical_mapping_invalid")
    for deadline in pack.deadlines:
        candidate = bind(deadline, "deadlines")
        if (
            deadline.from_event != candidate["fromEvent"]
            or deadline.duration != candidate["duration"]
            or deadline.consequence != candidate["consequence"]
            or set(deadline.applies_to)
            != {names.get(value, value) for value in candidate["appliesTo"]}
            or (candidate["obligation"] == "mandatory" and deadline.type != "hard")
            or (candidate["obligation"] == "advisory" and deadline.type != "soft")
        ):
            raise IntakeError(422, "canonical_mapping_invalid")
    for rule in pack.liability_rules:
        candidate = bind(rule, "remedies")
        if rule.summary != candidate["summary"] or rule.limits != candidate["limits"]:
            raise IntakeError(422, "canonical_mapping_invalid")
    if pack.forms:
        raise IntakeError(422, "explicit_form_mapping_required")
    for support in pack.crisis_support:
        matches = [
            key
            for key in accepted
            if candidates[key][0] == "support"
            and candidates[key][1]["name"] == support.name
            and candidates[key][1]["channel"] == support.channel
        ]
        if (
            len(matches) != 1
            or support.status != "verified"
            or verdicts[matches[0]] != "SUPPORTED"
            or build["reviews"][matches[0]].get("edited", False)
            or set(support.source_refs) != set(candidates[matches[0]][1]["sourceRefs"])
        ):
            raise IntakeError(422, "unverified_crisis_support")
        consumed.add(matches[0])
    if consumed != accepted:
        raise IntakeError(422, "unmapped_reviewed_items")
    unverified = {
        item.id
        for group in (pack.recipients, pack.sequencing, pack.deadlines, pack.liability_rules)
        for item in group
        if item.status == "unverified"
    }
    if set(body.get("acceptUnverifiedRuleIds", [])) != unverified:
        raise IntakeError(422, "unverified_acceptance_required")
    pack.status = "reviewed"
    pack.review.reviewer = body["reviewerName"]
    pack.review.reviewed_at = now
    pack.review.notes = body["notes"]
    pack.review.accepted_unverified_rule_ids = sorted(unverified)
    refs = {p.passage_id for source in sources for p in source.passages}
    if validate_pack(pack, refs, for_publish=True):
        raise IntakeError(422, "pack_validation_failed")
    pack.status = "published"
    return pack
