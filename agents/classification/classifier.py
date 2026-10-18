"""Strict classification reader; domain code controls urgency and uncertainty."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from agents.intake.clients import ModelClient, ModelFailure
from packages.safety import SafetyGuard, scrub_credentials
from packages.schemas.models import CaseFacts, Classification, EvidenceExtraction, Urgency


def compute_urgency(
    facts: CaseFacts, now: datetime, urgent_minutes: int = 120, high_hours: int = 72
) -> Urgency:
    if now.tzinfo is None or urgent_minutes <= 0 or high_hours <= 0:
        raise ValueError("invalid_urgency_configuration")
    timestamp = facts.payment.timestamp
    if timestamp is None:
        return Urgency(
            level="normal",
            reason="Payment time is unknown; confirm timing. This is not a legal deadline.",
        )
    seconds = (now.astimezone(UTC) - timestamp.astimezone(UTC)).total_seconds()
    if seconds < 0:
        return Urgency(
            level="normal",
            reason="Payment time is in the future; confirm timing. This is not a legal deadline.",
        )
    if seconds <= urgent_minutes * 60 and facts.payment.method in {
        "upi",
        "bank_transfer",
        "wallet",
    }:
        return Urgency(
            level="critical",
            reason=(
                "Recent transfer: prioritize contact with the bank. Recency does not "
                "establish where funds are. This is not a legal deadline."
            ),
        )
    if seconds <= high_hours * 3600:
        return Urgency(
            level="high",
            reason=(
                "Recent payment: prioritize reporting. This is a workflow threshold, "
                "not a legal deadline."
            ),
        )
    return Urgency(
        level="normal",
        reason=(
            "Payment is outside the configured urgent window. Reporting can still "
            "matter; this is not a legal deadline."
        ),
    )


QUESTIONS = {
    "en": (
        "Did you make or approve this payment yourself, or did someone else make it "
        "without your permission?"
    ),
    "hi": "क्या आपने यह भुगतान खुद किया या मंज़ूरी दी, या किसी और ने आपकी अनुमति के बिना किया?",
}
KNOWN_AUTH_QUESTIONS = {
    True: {
        "en": "What did that person claim, and why did they ask you to transfer money?",
        "hi": "उस व्यक्ति ने क्या दावा किया, और पैसे भेजने को क्यों कहा?",
    },
    False: {
        "en": "What activity did you discover that you had not approved?",
        "hi": "आपको कौन सी गतिविधि पता चली जिसकी आपने मंज़ूरी नहीं दी थी?",
    },
}


class ClassifierAgent:
    prompt_version = "classifier.v1"

    def __init__(
        self,
        client: ModelClient,
        *,
        urgent_minutes: int = 120,
        high_hours: int = 72,
        schema_retries: int = 0,
    ) -> None:
        if schema_retries not in {0, 1} or urgent_minutes <= 0 or high_hours <= 0:
            raise ValueError("invalid_classifier_configuration")
        self.client = client
        self.urgent_minutes = urgent_minutes
        self.high_hours = high_hours
        self.schema_retries = schema_retries
        self.guard = SafetyGuard()

    async def classify(
        self,
        *,
        facts: CaseFacts,
        now: datetime,
        language: Literal["en", "hi"] = "en",
        evidence_extractions: list[EvidenceExtraction] | None = None,
        transcript_summary: str = "",
        evidence: list[EvidenceExtraction] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> Classification:
        if language not in QUESTIONS or len(transcript_summary) > 16000:
            raise ValueError("invalid_classifier_input")
        if evidence is not None and evidence_extractions is not None:
            raise ValueError("duplicate_evidence_input")
        items = evidence if evidence is not None else evidence_extractions or []
        if len(items) > 20:
            raise ValueError("too_many_evidence_items")
        user_history = (history or [])[-6:]
        if (
            any(
                not isinstance(item.get("text"), str) or len(item["text"]) > 4000
                for item in user_history
            )
            or sum(len(item["text"]) for item in user_history) > 16000
        ):
            raise ValueError("invalid_classification_history")
        urgency = compute_urgency(facts, now, self.urgent_minutes, self.high_hours)
        prompt = (Path(__file__).parents[1] / "prompts/classifier.v1.md").read_text(
            encoding="utf-8"
        )
        data = {
            "facts": facts.model_dump(mode="json", by_alias=True),
            "untrustedEvidence": [item.model_dump(mode="json", by_alias=True) for item in items],
            "untrustedTranscript": transcript_summary,
            "untrustedHistory": user_history,
            "thresholds": {"urgentMinutes": self.urgent_minutes, "highHours": self.high_hours},
        }

        # String-only recursive scrubbing preserves numeric amounts/types.
        def sanitize(value: Any) -> Any:
            if isinstance(value, str):
                return scrub_credentials(value)
            if isinstance(value, list):
                return [sanitize(item) for item in value]
            if isinstance(value, dict):
                return {key: sanitize(item) for key, item in value.items()}
            return value

        async def model_output() -> Classification:
            for attempt in range(self.schema_retries + 1):
                raw = await self.client.generate(
                    prompt=prompt, data=sanitize(data), schema=Classification
                )
                if len(raw) > 100000:
                    raise ModelFailure("classification_output_oversized")
                try:
                    return Classification.model_validate_json(raw)
                except ValidationError:
                    if attempt == self.schema_retries:
                        raise ModelFailure("classification_schema_invalid") from None
            raise ModelFailure("classification_schema_invalid")

        try:
            result = await asyncio.wait_for(model_output(), timeout=20)
        except (ModelFailure, TimeoutError) as error:
            failure_code: Literal["schema_invalid", "model_unavailable", "unsafe_output"] = (
                "schema_invalid"
                if isinstance(error, ModelFailure) and "schema_invalid" in str(error)
                else "unsafe_output"
                if isinstance(error, ModelFailure) and "oversized" in str(error)
                else "model_unavailable"
            )
            result = Classification(
                typology="other",
                authorization_type="unclear",
                authorization_rationale="Classification could not reliably read the case.",
                urgency=urgency,
                confidence=0,
                needs_human_review=True,
            )
            result.degraded = True
            result.failure_code = failure_code
            result.clarifying_question = None
            result.funds_likely_in_system = "unknown"
            result.authorization_rationale = (
                "Classification could not reliably read the case. Existing facts remain saved; "
                "retry the model step rather than requesting the same facts again."
            )
            return result
        # Runtime transport state is server-owned, never accepted from model JSON.
        result.degraded = False
        result.failure_code = None
        if not self.guard.inspect_output(result.authorization_rationale).allow:
            result.authorization_type = "unclear"
            result.authorization_rationale = (
                "Classification output failed safety checks; existing facts remain saved."
            )
            result.urgency = urgency
            result.confidence = 0
            result.needs_human_review = True
            result.degraded = True
            result.failure_code = "unsafe_output"
            result.clarifying_question = None
            result.funds_likely_in_system = "unknown"
            result.vulnerability_flags = []
            return result
        conflict = (
            (
                facts.payment.authorized_by_victim is True
                and result.authorization_type in {"unauthorized_access", "card_unauthorized"}
            )
            or (
                facts.payment.authorized_by_victim is False
                and result.authorization_type == "authorized_manipulated"
            )
            or (result.authorization_type == "card_unauthorized" and facts.payment.method != "card")
        )
        if conflict or result.confidence < 0.7 or result.authorization_type == "unclear":
            result.authorization_type = "unclear"
            result.needs_human_review = True
        # Free model rationale is not presented as factual provenance. Only cite supplied paths.
        if conflict:
            rationale = (
                "Classification conflicts with facts.payment.authorizedByVictim "
                "or facts.payment.method; a person must clarify."
            )
        elif result.authorization_type == "authorized_manipulated":
            if facts.payment.authorized_by_victim is not True:
                result.authorization_type = "unclear"
                result.needs_human_review = True
                rationale = "The case does not explicitly confirm who initiated the payment."
            else:
                rationale = (
                    "facts.payment.authorizedByVictim records that the victim made "
                    "or approved the reported payment."
                )
        elif result.authorization_type in {"unauthorized_access", "card_unauthorized"}:
            if facts.payment.authorized_by_victim is not False:
                result.authorization_type = "unclear"
                result.needs_human_review = True
                rationale = (
                    "The case does not explicitly confirm whether payment was "
                    "initiated without permission."
                )
            else:
                rationale = (
                    "facts.payment.authorizedByVictim records no victim authorization; "
                    "facts.payment.method identifies the payment rail."
                )
        else:
            rationale = (
                "The available facts do not consistently establish payment "
                "authorization; a person must clarify."
            )
        result.authorization_rationale = rationale
        if result.authorization_type == "unclear":
            result.confidence = min(result.confidence, 0.69)
        result.urgency = urgency
        result.funds_likely_in_system = "unknown"
        flags = []
        if facts.victim_age_band == "60+":
            flags.append("elderly")
        if facts.ongoing_contact:
            flags.append("ongoing_contact")
        result.vulnerability_flags = flags
        result.clarifying_question = (
            KNOWN_AUTH_QUESTIONS[facts.payment.authorized_by_victim][language]
            if result.needs_human_review and facts.payment.authorized_by_victim is not None
            else QUESTIONS[language]
            if result.needs_human_review
            else None
        )
        if not self.guard.inspect_output(result.authorization_rationale).allow:
            raise ModelFailure("unsafe_classification")
        return result


class FixtureClassifierClient:
    model_id = "fixture-fake"
    mode: Literal["fake"] = "fake"

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result

    async def generate(self, **kwargs: Any) -> str:
        return json.dumps(self.result)
