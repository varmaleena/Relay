"""Receiver brief metadata is deterministic; unsupported model prose fails closed."""

import asyncio
import json
import math
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError

from agents.intake.clients import ModelClient, ModelFailure
from packages.common.identifiers import canonical_hash
from packages.safety.guard import SafetyGuard, scrub_credentials
from packages.schemas import KeyFact, MissingItem, Model, PacketContent, ReceiverBrief, Suggestion

Action = Literal[
    "acknowledge", "request_info", "place_hold_simulated", "reject_with_reason", "escalate"
]
PROMPTS = Path(__file__).parent


class BriefUnavailable(ModelFailure):
    def __init__(self, code: str):
        self.code = (
            code
            if code
            in {
                "input_invalid",
                "input_unsafe",
                "model_unavailable",
                "schema_invalid",
                "unsafe_output",
                "unsupported_claim",
                "timeout",
            }
            else "model_unavailable"
        )
        super().__init__("receiver_brief_unavailable:" + self.code)


class Recommendation(Model):
    action: Action
    why: str = Field(min_length=1, max_length=700)
    fact_refs: list[str] = Field(min_length=1, max_length=8)


class Reply(Model):
    lang: Literal["en", "hi"]
    text: str = Field(min_length=1, max_length=1000)
    requested_items: list[str] = Field(max_length=20)


class ReceiverBriefModelOutput(Model):
    suggestions: list[Recommendation] = Field(min_length=1, max_length=5)
    draft_reply: Reply | None = None


class Verdict(Model):
    index: int = Field(ge=0, le=30)
    verdict: Literal["SUPPORTED", "UNSUPPORTED", "CONTRADICTED"]


class ReceiverBriefEntailmentOutput(Model):
    verdicts: list[Verdict] = Field(max_length=30)
    language_correct: bool
    no_decision_claims: bool


def _safe(text: str) -> bool:
    return (
        scrub_credentials(text) == text
        and SafetyGuard().inspect_output(text).allow
        and not re.search(r"(?i)(?:account|खाता)\s*(?:number|नंबर)?\s*[:=#-]?\s*\d{5,}", text)
    )


def _canonical(key: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()


def _present(field: Any) -> bool:
    origin = field.provenance
    return bool(
        field.value
        and field.value.strip()
        and field.availability == "available"
        and (
            origin.source in {"confirmed", "statement", "victim_statement"}
            or origin.source == "extracted"
            and origin.confidence is not None
            and origin.confidence >= 0.8
        )
    )


class ReceiverBriefAgent:
    def __init__(self, client: ModelClient, *, timeout: float = 20):
        if not 0 < timeout <= 20:
            raise ValueError("receiver brief deadline at most20seconds")
        self.client, self.timeout = client, timeout

    async def make_brief(self, projection: dict[str, Any]) -> ReceiverBrief:
        """Caller authorizes org ownership; full case documents are never accepted."""
        allowed = {
            "caseRef",
            "jurisdiction",
            "urgency",
            "typology",
            "authorizationType",
            "minutesSincePayment",
            "packet",
            "keyFacts",
            "evidence",
            "timeline",
            "links",
        }
        try:
            if not isinstance(projection, dict) or set(projection) - allowed:
                raise ValueError("projection_shape")
            packet = projection["packet"]
            packet_allowed = {
                "packetId",
                "recipientId",
                "recipientName",
                "version",
                "status",
                "content",
                "verification",
                "delivery",
                "deadlines",
                "planId",
                "stale",
                "factsRevision",
                "contentHash",
            }
            if not isinstance(packet, dict) or set(packet) - packet_allowed:
                raise ValueError("packet_shape")
            if (
                type(packet.get("version")) is not int
                or not 1 <= packet["version"] <= 10000
                or not isinstance(packet.get("verification"), dict)
            ):
                raise ValueError("packet_version")
            if (
                not isinstance(packet, dict)
                or packet.get("stale") is True
                or packet.get("status")
                not in {
                    "APPROVED",
                    "SENT",
                    "ACKNOWLEDGED",
                    "NEEDS_INFO",
                    "ACTIONED",
                    "REJECTED",
                    "CLOSED",
                }
                or packet.get("verification", {}).get("passed") is not True
            ):
                raise ValueError("unapproved_projection")
            content = PacketContent.model_validate(packet["content"])
            if packet.get("contentHash") != canonical_hash(
                content.model_dump(mode="json", by_alias=True)
            ):
                raise ValueError("content_integrity")
            if not isinstance(packet.get("recipientId"), str) or not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_-]{0,79}", packet["recipientId"]
            ):
                raise ValueError("recipient_identity")
            if content.language not in {"en", "hi"} or len(content.fields) > 80:
                raise ValueError("input_bounds")
            keys = [f.key for f in content.fields]
            if len(set(keys)) != len(keys):
                raise ValueError("duplicate_fields")
            for field in content.fields:
                if len(field.key) > 120 or len(field.label) > 160 or len(field.value or "") > 2000:
                    raise ValueError("field_bounds")
                raw_value = field.value or ""
                if re.search(r"(?i)(?:^|[_.-])(?:password|pin|otp|cvv)(?:$|[_.-])", field.key):
                    raise BriefUnavailable("input_unsafe")
                if re.search(r"(?i)account_number|iban", field.key) and not raw_value:
                    raise BriefUnavailable("input_unsafe")
                if (
                    re.search(r"(?i)account|iban|card_number", field.key)
                    and len(re.sub(r"[^A-Za-z0-9]", "", raw_value)) > 4
                    and not re.fullmatch(r"[xX*•]+[- ]?[A-Za-z0-9]{0,4}", raw_value)
                ):
                    raise BriefUnavailable("input_unsafe")
                if re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}", raw_value):
                    raise BriefUnavailable("input_unsafe")
                if field.provenance.reference and not re.fullmatch(
                    r"[A-Za-z0-9_:.|/-]{1,400}", field.provenance.reference
                ):
                    raise BriefUnavailable("input_unsafe")
                if field.provenance.reference and "://" in field.provenance.reference:
                    raise BriefUnavailable("input_unsafe")
            for text in [
                content.subject,
                content.summary,
                content.message,
                content.footer,
                *content.requested_actions,
                *content.victim_copy.values(),
                *[f"{f.label}: {f.value or ''}" for f in content.fields],
            ]:
                if not _safe(text):
                    raise BriefUnavailable("input_unsafe")
            visible_size = sum(len(f.value or "") + len(f.label) for f in content.fields)
            if visible_size > 16000:
                raise ValueError("input_bounds")
        except BriefUnavailable:
            raise
        except (KeyError, TypeError, ValueError, ValidationError):
            raise BriefUnavailable("input_invalid") from None
        critical = {
            "payment.transaction_ref",
            "payment.amount",
            "payment.timestamp",
            "payment.recipient_identifier",
            "contact.identifier",
        }
        required = [f for f in content.fields if f.required]
        total = sum(2 if _canonical(f.key) in critical else 1 for f in required)
        score = sum((2 if _canonical(f.key) in critical else 1) for f in required if _present(f))
        completeness = score / total if total else 1.0
        if "score" in content.completeness:
            supplied = content.completeness["score"]
            if (
                type(supplied) not in {int, float}
                or not math.isfinite(supplied)
                or not 0 <= supplied <= 1
            ):
                raise BriefUnavailable("input_invalid")
            completeness = float(supplied)
        missing = [MissingItem(key=f.key, label=f.label) for f in required if not _present(f)]
        askable = {f.key for f in required if not _present(f) and f.availability != "not_available"}
        facts = [
            KeyFact(
                key=f.key,
                label=f.label,
                value=f.value or "",
                provenance=f.provenance.reference or f.provenance.source,
            )
            for f in sorted(
                content.fields, key=lambda f: (not f.required, _canonical(f.key) not in critical)
            )
            if _present(f)
        ][:5]
        risk = []
        if projection.get("urgency") in {"critical", "high"}:
            risk.append(
                {
                    "signal": "urgent_report",
                    "detail": "Supplied workflow urgency; not proof of fund location.",
                }
            )
        if any(f.availability == "not_available" for f in required):
            risk.append(
                {
                    "signal": "unavailable_item",
                    "detail": "The victim explicitly cannot provide one or more required items.",
                }
            )
        if (
            any(c.get("status") != "verified" for c in content.citations)
            or "unverified" in content.footer.lower()
        ):
            risk.append(
                {
                    "signal": "unverified_sources",
                    "detail": "Draft sources are unverified; no legal conclusion is established.",
                }
            )
        allowed_actions = {"acknowledge", "escalate", "reject_with_reason"}
        if askable:
            allowed_actions.add("request_info")
        minutes = projection.get("minutesSincePayment")
        if packet["recipientId"] == "bank" and type(minutes) is int and 0 <= minutes <= 90:
            allowed_actions.add("place_hold_simulated")
        manifest = {f.key: f.model_dump(mode="json", by_alias=True) for f in facts}
        references = (
            set(manifest) | {"packet", "completeness"} | {f"missing:{f.key}" for f in missing}
        )
        context = {
            "recipientId": packet["recipientId"],
            "packetVersion": packet.get("version"),
            "facts": manifest,
            "completeness": completeness,
            "missingItems": [m.model_dump(mode="json", by_alias=True) for m in missing],
            "askableMissing": sorted(askable),
            "unavailableItems": [f.key for f in required if f.availability == "not_available"],
            "allowedActions": sorted(allowed_actions),
            "victimLanguage": content.language,
            "riskSignals": risk,
            "simulated": True,
            "minutesSincePayment": minutes if type(minutes) is int and minutes >= 0 else None,
        }
        context["inputFlags"] = list(
            SafetyGuard().inspect_input(json.dumps(context, ensure_ascii=False)).flags
        )
        try:
            async with asyncio.timeout(self.timeout):
                raw = await self.client.generate(
                    prompt=(PROMPTS / "receiver_brief.v1.md").read_text(encoding="utf-8"),
                    data=context,
                    schema=ReceiverBriefModelOutput,
                )
                if len(raw) > 12000:
                    raise BriefUnavailable("schema_invalid")
                output = ReceiverBriefModelOutput.model_validate_json(raw)
                seen = set()
                for item in output.suggestions:
                    if (
                        item.action not in allowed_actions
                        or item.action in seen
                        or not set(item.fact_refs) <= references
                    ):
                        raise BriefUnavailable("unsupported_claim")
                    seen.add(item.action)
                if askable and output.draft_reply is None:
                    raise BriefUnavailable("schema_invalid")
                if output.draft_reply is not None and (
                    output.draft_reply.lang != content.language
                    or not set(output.draft_reply.requested_items) <= askable
                    or len(output.draft_reply.requested_items)
                    != len(set(output.draft_reply.requested_items))
                ):
                    raise BriefUnavailable("unsupported_claim")
                texts = [item.why for item in output.suggestions]
                if output.draft_reply is not None:
                    texts.append(output.draft_reply.text)
                if not all(_safe(text) for text in texts):
                    raise BriefUnavailable("unsafe_output")
                sentences = [
                    s.strip()
                    for t in texts
                    for s in re.split(r"(?<=[.!?।])\s+|\n+", t)
                    if s.strip()
                ]
                if not sentences or len(sentences) > 30:
                    raise BriefUnavailable("schema_invalid")
                checked = await self.client.generate(
                    prompt=(PROMPTS / "receiver_brief_verify.v1.md").read_text(encoding="utf-8"),
                    data={
                        **context,
                        "sentences": [{"index": i, "text": s} for i, s in enumerate(sentences)],
                    },
                    schema=ReceiverBriefEntailmentOutput,
                )
                if len(checked) > 12000:
                    raise BriefUnavailable("schema_invalid")
                verdict = ReceiverBriefEntailmentOutput.model_validate_json(checked)
                if (
                    sorted(v.index for v in verdict.verdicts) != list(range(len(sentences)))
                    or any(v.verdict != "SUPPORTED" for v in verdict.verdicts)
                    or not verdict.language_correct
                    or not verdict.no_decision_claims
                ):
                    raise BriefUnavailable("unsupported_claim")
        except BriefUnavailable:
            raise
        except TimeoutError:
            raise BriefUnavailable("timeout") from None
        except ValidationError:
            raise BriefUnavailable("schema_invalid") from None
        except ModelFailure:
            raise BriefUnavailable("model_unavailable") from None
        return ReceiverBrief(
            completeness_score=completeness,
            missing_items=missing,
            key_facts=facts,
            risk_signals=risk,
            suggested_actions=[Suggestion(action=i.action, why=i.why) for i in output.suggestions],
            draft_reply_to_victim={"lang": output.draft_reply.lang, "text": output.draft_reply.text}
            if output.draft_reply
            else {},
        )
