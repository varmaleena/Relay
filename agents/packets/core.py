"""Bounded packet drafting; authoritative metadata never originates in model output."""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.intake.clients import ModelClient, ModelFailure
from packages.safety.guard import SafetyGuard, scrub_credentials
from packages.schemas import (
    CaseFacts,
    EvidenceExtraction,
    Pack,
    PacketContent,
    PacketField,
    PlanStep,
    Provenance,
    Recipient,
    VerificationCheck,
)

PROMPTS = Path(__file__).parents[1] / "prompts"


class VictimCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=1800)
    message: str = Field(min_length=1, max_length=5000)


class WriterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=1, max_length=240)
    summary: str = Field(min_length=1, max_length=1800)
    message: str = Field(min_length=1, max_length=5000)
    requestedActions: list[str] = Field(min_length=1, max_length=8)
    victimCopy: VictimCopy


class SentenceVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=0)
    verdict: Literal["SUPPORTED", "UNSUPPORTED", "CONTRADICTED"]


class EntailmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sentences: list[SentenceVerdict] = Field(max_length=100)
    blockers: list[str] = Field(max_length=20)
    languageCorrect: bool


@dataclass
class PacketBuildResult:
    content: PacketContent | None
    checks: list[VerificationCheck]
    attempts: int
    status: Literal["VERIFIED", "NEEDS_HUMAN_REVIEW"]
    model: str
    attempt_history: list[dict[str, Any]] = field(default_factory=list)
    prompt_versions: list[str] = field(default_factory=lambda: ["packet.v1", "verifier.v1"])


def check(
    name: str,
    passed: bool,
    detail: str,
    *,
    kind: Literal["deterministic", "llm"] = "deterministic",
    warning: bool = False,
) -> VerificationCheck:
    return VerificationCheck(
        id=name,
        type=kind,
        passed=passed,
        detail=detail,
        severity="warning" if warning else "blocker",
    )


def footer_for(pack: Pack) -> str:
    text = (
        f"Prepared by Relay from {pack.pack_id} v{pack.version}. "
        "Review before sending. This is not legal advice."
    )
    if pack.status != "published" or any(r.status == "unverified" for r in pack.recipients):
        text += " Unverified draft guidance / सत्यापित नहीं."
    return text


def _value(facts: CaseFacts, key: str) -> str | None:
    obj: Any = facts
    for part in key.split("."):
        if not hasattr(obj, part):
            return None
        obj = getattr(obj, part)
    if obj is None:
        return None
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "currency") and hasattr(obj, "value"):
        return f"{obj.currency} {obj.value}"
    if hasattr(obj, "value"):
        return str(obj.value) if obj.value is not None else None
    if isinstance(obj, (str, bool, int)):
        return str(obj)
    return None


def anchor_confirmed_facts(facts: CaseFacts, *, case_id: str, facts_revision: int) -> CaseFacts:
    """Resolve trusted persisted origins to a case snapshot, never model-supplied proof.

    Only server-confirmed values gain a missing reference. Extracted origins retain
    their evidence reference/confidence requirements. Aliases must not fall through
    to the generic victim-statement fallback.
    """
    if not re.fullmatch(r"case_[A-Za-z0-9_-]{1,100}", case_id) or facts_revision < 0:
        raise ValueError("invalid_case_provenance_anchor")
    anchored = facts.model_copy(deep=True)
    origins: dict[str, Provenance] = {}
    for path, origin in facts.field_provenance.items():
        key = re.sub(r"(?<!^)(?=[A-Z])", "_", path).lower()
        existing = origins.get(key)
        if existing is not None and existing != origin:
            raise ValueError("provenance_alias_conflict")
        origins[key] = origin.model_copy(deep=True)
    for key, origin in origins.items():
        obj: Any = facts
        for part in key.split("."):
            obj = getattr(obj, part, None)
        if origin.source == "confirmed" and not origin.reference and obj is not None:
            origin.reference = f"case:{case_id}:facts:{facts_revision}:{key}"
    groups = {
        "payment.amount": ("value", "currency"),
        "payment.recipient_identifier": ("value", "type"),
    }
    for parent, names in groups.items():
        components = [origins.get(f"{parent}.{name}") for name in names]
        if parent in origins or not any(components):
            continue
        present = [part for part in components if part is not None]
        if len(present) == len(names) and all(part.source == "confirmed" for part in present):
            origins[parent] = Provenance(
                source="confirmed", reference=f"case:{case_id}:facts:{facts_revision}:{parent}"
            )
        elif (
            len(present) == len(names)
            and all(part.source == "extracted" for part in present)
            and present[0].reference
            and all(part.reference == present[0].reference for part in present)
        ):
            origins[parent] = Provenance(
                source="extracted",
                reference=present[0].reference,
                confidence=min((part.confidence or 0) for part in present),
            )
        else:
            # Incomplete/mixed origins must not be promoted to a victim statement.
            origins[parent] = Provenance(source="inferred")
    anchored.field_provenance = origins
    return anchored


PACKET_COMMON_FIELDS = (
    "payment.amount",
    "payment.timestamp",
    "payment.transaction_ref",
    "payment.recipient_identifier",
    "payment.method",
    "victim_bank",
    "contact.identifier",
    "contact.claimed_identity",
)


def confirmable_packet_fields(facts: CaseFacts, recipient: Recipient, pack: Pack) -> set[str]:
    """Server-defined fields with no canonical value; never model-defined keys."""
    allowed = set(recipient.required_fields) | set(PACKET_COMMON_FIELDS)
    for form in pack.forms:
        if form.recipient_id == recipient.id:
            allowed.update(f if isinstance(f, str) else str(f.get("key", "")) for f in form.fields)
    return {
        key
        for key in allowed
        if _value(facts, key) is None
        and not re.search(r"(?i)account|card|otp|pin|password|cvv", key)
    }


def _confirmations(
    facts: CaseFacts, recipient: Recipient, pack: Pack, values: dict[str, str] | None
) -> dict[str, str]:
    allowed = confirmable_packet_fields(facts, recipient, pack)
    result = {}
    for key, value in (values or {}).items():
        if (
            key not in allowed
            or _value(facts, key) is not None
            or not value.strip()
            or len(value) > 250
            or scrub_credentials(value) != value
            or not SafetyGuard().inspect_output(value).allow
            or re.search(r"(?i)account|card|otp|pin|password|cvv", key)
        ):
            raise ValueError("invalid_field_confirmation")
        if key == "payment.amount":
            from packages.schemas import Money

            match = re.fullmatch(r"([A-Z]{3}) ([0-9]+(?:\.[0-9]+)?)", value)
            if not match:
                raise ValueError("invalid_amount_confirmation")
            money = Money(value=Decimal(match[2]), currency=match[1])
            value = f"{money.currency} {money.value}"
        elif key == "payment.timestamp":
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("invalid_timestamp_confirmation")
            value = timestamp.isoformat()
        elif key == "payment.transaction_ref" and not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", value):
            raise ValueError("invalid_reference_confirmation")
        result[key] = value
    return result


def _metadata(
    facts: CaseFacts,
    recipient: Recipient,
    pack: Pack,
    plan_step: PlanStep,
    source_passages: dict[str, str],
    attachments: list[dict[str, str]],
    available_provenance: dict[str, Provenance] | None = None,
    confirmed_fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    keys = list(dict.fromkeys(recipient.required_fields + list(PACKET_COMMON_FIELDS)))
    confirmations = _confirmations(facts, recipient, pack, confirmed_fields)
    provenance = dict(facts.field_provenance)
    for key in confirmations:
        provenance[key] = Provenance(source="confirmed", reference=f"packet_confirmation:{key}")
    # Supplied provenance may corroborate existing facts, never override authoritative origins.
    if available_provenance and any(
        key in provenance and provenance[key] != value
        for key, value in available_provenance.items()
    ):
        raise ValueError("provenance_conflict")
    fields = []
    for key in keys:
        value = confirmations.get(key, _value(facts, key))
        missing = key in facts.unavailable_fields and key not in confirmations
        fields.append(
            PacketField(
                key=key,
                label=key,
                value=None if missing else value,
                required=key in recipient.required_fields,
                availability="not_available" if missing else "available" if value else "unknown",
                provenance=provenance.get(
                    key, Provenance(source="victim_statement", reference=key)
                ),
            )
        )
    refs = list(dict.fromkeys(plan_step.source_refs + recipient.source_refs))
    citations = [
        {"reference": ref, "status": "unverified" if pack.status != "published" else "verified"}
        for ref in refs
        if ref in source_passages
    ]
    missing_fields = [f.key for f in fields if f.required and not f.value]
    critical = {
        "payment.amount",
        "payment.timestamp",
        "payment.transaction_ref",
        "payment.recipient_identifier",
        "contact.identifier",
    }
    total = sum(2 if f.key in critical else 1 for f in fields)
    score = sum(
        (2 if f.key in critical else 1)
        for f in fields
        if f.value
        and (
            f.provenance.source in {"confirmed", "statement", "victim_statement"}
            or (f.provenance.source == "extracted" and (f.provenance.confidence or 0) >= 0.8)
        )
    )
    return {
        "fields": fields,
        "citations": citations,
        "attachments": attachments,
        "footer": footer_for(pack),
        "completeness": {
            "score": score / total if total else 0,
            "missing": missing_fields,
            "recipientId": recipient.id,
            "notAvailable": [f.key for f in fields if f.availability == "not_available"],
        },
    }


def _sentences(content: PacketContent) -> list[str]:
    return [
        s.strip()
        for text in (content.summary, content.message)
        for s in re.split(r"(?<=[.!?।])\s+|\n+", text)
        if s.strip()
    ]


def _context(
    *,
    facts: CaseFacts,
    plan_step: PlanStep,
    recipient: Recipient,
    pack: Pack,
    source_passages: dict[str, str],
    evidence: list[EvidenceExtraction],
    victim_language: str,
    recipient_language: str,
    attachments: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "facts": facts.model_dump(mode="json", by_alias=True),
        "planStep": plan_step.model_dump(mode="json", by_alias=True),
        "recipient": recipient.model_dump(mode="json", by_alias=True),
        "packId": pack.pack_id,
        "packStatus": pack.status,
        "sourcePassages": source_passages,
        "evidence": [e.model_dump(mode="json", by_alias=True) for e in evidence],
        "victimLanguage": victim_language,
        "recipientLanguage": recipient_language,
        "attachments": attachments,
    }


def prepare_content(
    content: PacketContent,
    *,
    facts: CaseFacts,
    plan_step: PlanStep,
    recipient: Recipient,
    pack: Pack,
    source_passages: dict[str, str],
    attachments: list[dict[str, str]],
    confirmed_fields: dict[str, str] | None = None,
    evidence: list[EvidenceExtraction] | None = None,
    victim_language: str = "en",
    recipient_language: str = "en",
) -> PacketContent:
    """Normalize only legitimate missing-field confirmations and completeness.

    Never repair existing fact edits, citations, footer or prose behind the user's back.
    Must be invoked server-side with persisted confirmations, never raw client proof.
    """
    confirmations = _confirmations(facts, recipient, pack, confirmed_fields)
    expected = _metadata(
        facts,
        recipient,
        pack,
        plan_step,
        source_passages,
        attachments,
        confirmed_fields=confirmations,
    )
    expected_fields = {f.key: f for f in expected["fields"]}
    fields = []
    seen = set()
    for item in content.fields:
        if item.key in confirmations:
            if item.value != confirmations[item.key]:
                raise ValueError("confirmation_value_mismatch")
            fields.append(expected_fields[item.key])
        else:
            fields.append(item)
        seen.add(item.key)
    if set(confirmations) - seen:
        raise ValueError("confirmation_field_missing")
    return content.model_copy(update={"fields": fields, "completeness": expected["completeness"]})


class PacketVerifier:
    def __init__(self, client: ModelClient, *, timeout: float = 20) -> None:
        self.client = client
        self.timeout = timeout
        self.guard = SafetyGuard()

    async def verify(
        self,
        content: PacketContent,
        *,
        facts: CaseFacts,
        plan_step: PlanStep,
        recipient: Recipient,
        pack: Pack,
        source_passages: dict[str, str],
        evidence: list[EvidenceExtraction],
        victim_language: str,
        recipient_language: str,
        attachments: list[dict[str, str]],
        confirmed_fields: dict[str, str] | None = None,
    ) -> list[VerificationCheck]:
        try:
            confirmations = _confirmations(facts, recipient, pack, confirmed_fields)
            expected = _metadata(
                facts,
                recipient,
                pack,
                plan_step,
                source_passages,
                attachments,
                confirmed_fields=confirmations,
            )
        except (ValueError, ValidationError):
            return [
                check("field_confirmation", False, "Invalid or conflicting field confirmation.")
            ]
        checks = [
            check(
                "recipient",
                plan_step.recipient_id == recipient.id
                and content.completeness.get("recipientId") == recipient.id
                and any(r == recipient for r in pack.recipients),
                "Recipient must match selected pack and plan.",
            ),
            check(
                "language",
                content.language == victim_language
                and content.recipient_language
                == recipient_language
                == recipient.recipient_language,
                "Language metadata must match requested languages.",
            ),
            check(
                "footer",
                content.footer == expected["footer"],
                "Required versioned footer and draft labels.",
            ),
            check(
                "attachments",
                content.attachments == attachments
                and all(re.fullmatch(r"[0-9a-f]{64}", a.get("sha256", "")) for a in attachments),
                "Attachment manifest must match verified hashes.",
            ),
            check(
                "citations",
                content.citations == expected["citations"]
                and all(
                    ref in source_passages for ref in plan_step.source_refs + recipient.source_refs
                ),
                "Every source reference must resolve; draft status must survive.",
            ),
            check(
                "fields",
                content.fields == expected["fields"],
                "Structured values and provenance must equal case facts.",
            ),
            check(
                "completeness",
                content.completeness == expected["completeness"],
                "Completeness is computed from trusted field metadata.",
            ),
            check(
                "required",
                not expected["completeness"]["missing"],
                "Required fields must be provided.",
            ),
            check(
                "victim_copy",
                set(content.victim_copy) == {"summary", "message"}
                and all(content.victim_copy.values()),
                "A complete plain-language victim copy is required.",
            ),
        ]
        rules = {
            r.id
            for group in (pack.recipients, pack.sequencing, pack.deadlines, pack.liability_rules)
            for r in group
        }
        checks.append(
            check(
                "rule_references",
                all(ref in rules for ref in plan_step.rule_refs),
                "Plan rule references must belong to the selected pack.",
            )
        )
        text = json.dumps(content.model_dump(mode="json"), ensure_ascii=False)
        # Scan user-visible text, not computed scores or cryptographic hash digits.
        safety_text = "\n".join(
            [
                content.subject,
                content.summary,
                content.message,
                content.footer,
                *content.requested_actions,
                *content.victim_copy.values(),
                *[f"{f.label}: {f.value or ''}" for f in content.fields],
            ]
        )
        checks.append(
            check(
                "safety",
                self.guard.inspect_output(safety_text).allow
                and scrub_credentials(safety_text) == safety_text
                and not re.search(
                    r"(?i)(?:account|खाता)\s*(?:number|नंबर|:|=)\s*\d{5,}", safety_text
                ),
                "No credentials, full accounts, promises or unsupported legal conclusions.",
            )
        )
        prose = " ".join(
            [
                content.subject,
                content.summary,
                content.message,
                *content.requested_actions,
                *content.victim_copy.values(),
            ]
        )
        amount = facts.payment.amount
        if amount is None and "payment.amount" in confirmations:
            from packages.schemas import Money

            currency, value = confirmations["payment.amount"].split(" ")
            amount = Money(value=Decimal(value), currency=currency)
        monetary = re.findall(r"\b(INR|USD|GBP|EUR)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", prose)

        checks.append(
            check(
                "amounts",
                all(
                    amount is not None
                    and c == amount.currency
                    and Decimal(v.replace(",", "")) == amount.value
                    for c, v in monetary
                ),
                "Explicit currency amounts must equal the case amount.",
            )
        )
        iso_times = re.findall(r"\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?(?:Z|[+-]\d\d:\d\d)", prose)
        payment_time = facts.payment.timestamp
        if payment_time is None and "payment.timestamp" in confirmations:
            payment_time = datetime.fromisoformat(confirmations["payment.timestamp"])
        checks.append(
            check(
                "timestamps",
                all(
                    facts.payment.timestamp is not None
                    and datetime.fromisoformat(t.replace("Z", "+00:00")) == facts.payment.timestamp
                    for t in iso_times
                ),
                "Explicit timestamps must equal case facts.",
            )
        )
        allowed_identifiers = {
            value
            for value in (
                facts.payment.transaction_ref,
                facts.payment.recipient_identifier.value
                if facts.payment.recipient_identifier
                else None,
                facts.contact.identifier,
            )
            if value
        }
        allowed_identifiers.update(confirmations.values())
        found_identifiers = [v.rstrip(".") for v in re.findall(r"[\w.+-]+@[\w.-]+", prose)]
        found_refs = re.findall(
            r"(?i)(?:transaction (?:reference|ref)(?: number)?|reference(?: number)?|UTR)"
            r"\s*(?:is|:|=)?\s*((?=[A-Z0-9_-]*[0-9])[A-Z0-9_-]{6,})",
            prose,
        )
        checks.append(
            check(
                "identifiers",
                all(value in allowed_identifiers for value in found_identifiers + found_refs),
                "Explicit identifiers must match victim facts, not new model values.",
            )
        )
        checks.append(
            check(
                "provenance",
                all(
                    f.value is None
                    or (
                        f.provenance.source
                        in {"statement", "victim_statement", "selected", "confirmed"}
                        and bool(f.provenance.reference)
                    )
                    or (
                        f.provenance.source == "extracted"
                        and f.provenance.reference in {e.evidence_id for e in evidence}
                    )
                    for f in content.fields
                ),
                "Every populated field requires a traceable statement or evidence origin.",
            )
        )
        checks.append(
            check(
                "promise",
                not re.search(
                    r"(?i)(?:money|funds|payment).{0,25}(?:will be|is guaranteed to be)"
                    r"\s*(?:recovered|returned|refunded)|"
                    r"(?:पैसे|धन).{0,20}(?:ज़रूर|जरूर|गारंटी).{0,20}(?:वापस|मिल)",
                    prose,
                ),
                "Recovery cannot be promised.",
            )
        )
        if any(not c.passed and c.severity == "blocker" for c in checks):
            return checks
        sentences = _sentences(content)
        if not sentences or len(sentences) > 60 or len(text) > 24000:
            return checks + [check("bounds", False, "Packet exceeds verification bounds.")]
        context = _context(
            facts=facts,
            plan_step=plan_step,
            recipient=recipient,
            pack=pack,
            source_passages=source_passages,
            evidence=evidence,
            victim_language=victim_language,
            recipient_language=recipient_language,
            attachments=attachments,
        )
        input_text = json.dumps(context, ensure_ascii=False)
        if len(input_text) > 48000 or scrub_credentials(input_text) != input_text:
            return checks + [
                check(
                    "verification_input_safety", False, "Unsafe or oversized verification context."
                )
            ]
        try:
            raw = await asyncio.wait_for(
                self.client.generate(
                    prompt=(PROMPTS / "verifier.v1.md").read_text(encoding="utf-8"),
                    data={
                        **context,
                        "packet": content.model_dump(mode="json", by_alias=True),
                        "confirmedFields": confirmations,
                        "sentences": [{"index": i, "text": s} for i, s in enumerate(sentences)],
                    },
                    schema=EntailmentOutput,
                ),
                self.timeout,
            )
            if len(raw) > 24000:
                raise ValueError("response_bounds")
            verdict = EntailmentOutput.model_validate_json(raw)
            indices = [s.index for s in verdict.sentences]
            for sentence in verdict.sentences:
                checks.append(
                    check(
                        f"entailment_sentence_{sentence.index}",
                        sentence.verdict == "SUPPORTED",
                        f"Sentence {sentence.index} requires explicit fact/evidence support.",
                        kind="llm",
                    )
                )

            checks.append(
                check(
                    "entailment",
                    sorted(indices) == list(range(len(sentences)))
                    and all(s.verdict == "SUPPORTED" for s in verdict.sentences)
                    and not verdict.blockers
                    and verdict.languageCorrect,
                    "Every sentence must be supported and both copies accurate.",
                    kind="llm",
                )
            )
        except (ModelFailure, ValidationError, ValueError, TimeoutError):
            checks.append(
                check(
                    "entailment_unavailable",
                    False,
                    "Verification unavailable or invalid; review required.",
                    kind="llm",
                )
            )
        return checks


class PacketPipeline:
    def __init__(self, client: ModelClient, *, timeout: float = 20, max_repairs: int = 2) -> None:
        if not 0 <= max_repairs <= 2:
            raise ValueError("max_repairs must be between zero and two")
        self.client, self.timeout, self.max_repairs = client, timeout, max_repairs
        self.verifier = PacketVerifier(client, timeout=timeout)

    async def build(
        self,
        *,
        facts: CaseFacts,
        plan_step: PlanStep,
        recipient: Recipient,
        pack: Pack,
        source_passages: dict[str, str],
        evidence: list[EvidenceExtraction] | None = None,
        victim_language: str = "en",
        recipient_language: str = "en",
        attachments: list[dict[str, str]] | None = None,
        available_provenance: dict[str, Provenance] | None = None,
        confirmed_fields: dict[str, str] | None = None,
    ) -> PacketBuildResult:
        evidence, attachments = evidence or [], attachments or []
        context = _context(
            facts=facts,
            plan_step=plan_step,
            recipient=recipient,
            pack=pack,
            source_passages=source_passages,
            evidence=evidence,
            victim_language=victim_language,
            recipient_language=recipient_language,
            attachments=attachments,
        )
        context["confirmedFields"] = confirmed_fields or {}
        serialized = json.dumps(context, ensure_ascii=False)
        context["inputFlags"] = list(self.verifier.guard.inspect_input(serialized).flags)
        try:
            _confirmations(facts, recipient, pack, confirmed_fields)
        except (ValueError, ValidationError):
            return PacketBuildResult(
                None,
                [check("field_confirmation", False, "Invalid or conflicting field confirmation.")],
                0,
                "NEEDS_HUMAN_REVIEW",
                self.client.model_id,
            )

        identifier = facts.payment.recipient_identifier
        account_secret = bool(
            identifier
            and re.search(r"(?i)account|card|खाता|कार्ड", identifier.type)
            and len(re.sub(r"\D", "", identifier.value)) > 4
        )
        if len(serialized) > 48000 or scrub_credentials(serialized) != serialized or account_secret:
            return PacketBuildResult(
                None,
                [check("input_bounds_safety", False, "Unsafe or oversized packet input.")],
                0,
                "NEEDS_HUMAN_REVIEW",
                self.client.model_id,
            )
        checks: list[VerificationCheck] = []
        history: list[dict[str, Any]] = []
        content = None
        for attempt in range(1, self.max_repairs + 2):
            try:
                raw = await asyncio.wait_for(
                    self.client.generate(
                        prompt=(PROMPTS / "packet.v1.md").read_text(encoding="utf-8"),
                        data={
                            **context,
                            "repairChecks": [c.id for c in checks if not c.passed],
                            "previousDraft": (
                                content.model_dump(mode="json", by_alias=True)
                                if content is not None
                                and not any(c.id == "safety" and not c.passed for c in checks)
                                else None
                            ),
                        },
                        schema=WriterOutput,
                    ),
                    self.timeout,
                )
                if len(raw) > 16000:
                    raise ValueError("response_bounds")
                output = WriterOutput.model_validate_json(raw)
                content = PacketContent(
                    language=victim_language,
                    recipient_language=recipient_language,
                    subject=output.subject,
                    summary=output.summary,
                    message=output.message,
                    requested_actions=output.requestedActions,
                    victim_copy=output.victimCopy.model_dump(),
                    **_metadata(
                        facts,
                        recipient,
                        pack,
                        plan_step,
                        source_passages,
                        attachments,
                        available_provenance,
                        confirmed_fields,
                    ),
                )
                checks = await self.verifier.verify(
                    content,
                    facts=facts,
                    plan_step=plan_step,
                    recipient=recipient,
                    pack=pack,
                    source_passages=source_passages,
                    evidence=evidence,
                    victim_language=victim_language,
                    recipient_language=recipient_language,
                    attachments=attachments,
                    confirmed_fields=confirmed_fields,
                )
                history.append(
                    {
                        "attempt": attempt,
                        "checks": [c.model_dump(mode="json", by_alias=True) for c in checks],
                    }
                )
                static_blockers = {
                    "recipient",
                    "fields",
                    "completeness",
                    "required",
                    "provenance",
                    "attachments",
                    "citations",
                    "rule_references",
                    "footer",
                    "language",
                }
                if any(not c.passed and c.id in static_blockers for c in checks):
                    # The writer cannot repair server-owned fields/origins/pack configuration.
                    break

                if all(c.passed or c.severity == "warning" for c in checks):
                    return PacketBuildResult(
                        content,
                        checks,
                        attempt,
                        "VERIFIED",
                        self.client.model_id,
                        attempt_history=history,
                    )
            except (ModelFailure, ValidationError, ValueError, TimeoutError) as error:
                # Preserve a prior safe draft and its blockers, never fabricate first-failure prose.
                safe_prior = (
                    content if not any(c.id == "safety" and not c.passed for c in checks) else None
                )
                prior_checks = list(checks)
                history.append(
                    {"attempt": attempt, "stage": "writer", "errorType": type(error).__name__}
                )
                checks = prior_checks + [
                    check(
                        "writer_unavailable",
                        False,
                        "Draft unavailable or invalid; review required.",
                    )
                ]
                return PacketBuildResult(
                    safe_prior,
                    checks,
                    attempt,
                    "NEEDS_HUMAN_REVIEW",
                    self.client.model_id,
                    attempt_history=history,
                )
        # Never hand unsafe generated credentials to persistence or the UI, even as a failed draft.
        if any(not c.passed and c.id == "safety" for c in checks):
            content = None
        return PacketBuildResult(
            content,
            checks,
            attempt,
            "NEEDS_HUMAN_REVIEW",
            self.client.model_id,
            attempt_history=history,
        )
