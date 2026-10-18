"""M1 text intake and evidence readers: scoped extraction, no state mutation tools."""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError

from packages.safety import SafetyGuard, scrub_credentials
from packages.schemas.models import CaseFacts, Entity, EvidenceExtraction, Model

from .clients import ModelClient, ModelFailure

Language = Literal["en", "hi"]
SHORT = Annotated[str, Field(max_length=4000)]
ENTITY_TYPES = {
    "phone",
    "upi_id",
    "bank_account",
    "ifsc_or_sort_code",
    "iban",
    "url",
    "email",
    "social_handle",
    "wallet_address",
    "transaction_ref",
    "amount",
    "currency",
    "timestamp",
    "bank_name",
    "app_name",
    "claimed_identity",
}
FIRST_ACTION = {
    "en": "Stop contact with the person who asked for money. Do not share any code, PIN, "
    "or password. This applies to everyone, including me. Contact your bank now using the number "
    "on your card or in its official app. I'll help you with the rest.",
    "hi": "जिस व्यक्ति ने पैसे मांगे थे, उससे संपर्क बंद करें। किसी से यह जानकारी साझा न करें: "
    "कोड, पिन, पासवर्ड। मुझसे भी नहीं। कार्ड पर दिए नंबर या बैंक के आधिकारिक ऐप "
    "से अभी अपने बैंक से संपर्क करें। बाकी काम में मैं आपकी मदद करूँगा।",
}
QUESTIONS: dict[str, dict[str, str]] = {
    "en": {
        "country": "Which country are you in?",
        "payment.method": "How did you pay?",
        "payment.amount": "How much did you send, and in which currency?",
        "payment.timestamp": "When did the payment happen?",
        "contact.channel": "How did that person contact you?",
        "ongoingContact": "Are you still in contact with that person?",
    },
    "hi": {
        "country": "आप किस देश में हैं?",
        "payment.method": "आपने पैसे कैसे भेजे?",
        "payment.amount": "आपने कितने पैसे और किस मुद्रा में भेजे?",
        "payment.timestamp": "भुगतान कब हुआ था?",
        "contact.channel": "उस व्यक्ति ने आपसे कैसे संपर्क किया?",
        "ongoingContact": "क्या आप अभी भी उस व्यक्ति के संपर्क में हैं?",
    },
}
DISTRESS = {
    "en": "This is a hard moment. You do not have to face it alone. Please contact local "
    "emergency services or someone you trust right now. We can continue when you are ready.",
    "hi": "यह मुश्किल समय है। आपको इसे अकेले सहने की ज़रूरत नहीं है। अभी स्थानीय "
    "आपातकालीन सेवा या किसी भरोसेमंद व्यक्ति से संपर्क करें। जब आप तैयार हों, "
    "तब हम आगे बात कर सकते हैं।",
}
_distress = re.compile(
    r"kill myself|hurt myself|suicid|end my life|can't go on|cannot go on|hopeless|"
    r"आत्महत्या|खुद को (?:मार|नुकसान)|जीना नहीं|मर जाना|उम्मीद नहीं|"
    r"mar jana|jeena nahi|khud ko maar",
    re.I,
)


class IntakeModelOutput(Model):
    facts_delta: CaseFacts = Field(default_factory=CaseFacts)
    distress: bool = False
    request_upload: Literal["screenshot", "chat_export", "receipt", "other"] | None = None


class UserStatement(Model):
    text: Annotated[str, Field(min_length=1, max_length=4000)]
    at: datetime


class IntakeReply(Model):
    text: str
    lang: Language
    facts_delta: dict[str, Any]
    missing_minimum: list[str]
    distress: bool = False
    processing_ready: bool = False
    request_upload: str | None = None
    safety_flags: list[str] = Field(default_factory=list)
    model: str
    prompt_version: str = "intake_text.v2"
    mode: Literal["live", "fake", "replay"]
    degraded: bool = False


class EvidenceSpan(Model):
    page: Annotated[int, Field(ge=1)] | None = None
    bbox: Annotated[list[float], Field(min_length=4, max_length=4)] | None = None
    offset_start: Annotated[int, Field(ge=0)] | None = None
    offset_end: Annotated[int, Field(ge=0)] | None = None


class ExtractedEntity(Model):
    type: Annotated[str, Field(max_length=32)]
    raw_value: Annotated[str, Field(min_length=1, max_length=2048)]
    normalized_value: Annotated[str, Field(min_length=1, max_length=2048)]
    role: Literal["victim", "scammer", "merchant", "unknown"]
    confidence: Annotated[float, Field(ge=0, le=1)]
    span: EvidenceSpan | None = None


class EvidenceModelOutput(Model):
    document_type: Literal["payment_screenshot", "chat", "sms", "call_log", "receipt", "other"]
    entities: Annotated[list[ExtractedEntity], Field(max_length=100)]
    summary: SHORT
    confidence: Annotated[float, Field(ge=0, le=1)]
    injection_suspected: bool = False
    notes: SHORT = ""
    sensitive_content_detected: bool = False
    safety_scan_complete: bool = False


def minimum_facts(facts: CaseFacts) -> list[str]:
    """Recipient identifiers are optional; unknown booleans remain missing."""
    values = {
        "country": facts.country.value
        if facts.country and facts.country.availability == "available"
        else None,
        "payment.method": facts.payment.method,
        "payment.amount": facts.payment.amount,
        "payment.timestamp": facts.payment.timestamp,
        "contact.channel": facts.contact.channel,
        "ongoingContact": facts.ongoing_contact,
    }
    return [key for key, value in values.items() if value is None or value == ""]


def _prompt(name: str, version: str = "v1") -> str:
    return (Path(__file__).parents[1] / "prompts" / f"{name}.{version}.md").read_text(
        encoding="utf-8"
    )


async def _validated[T: Model](
    client: ModelClient,
    schema: type[T],
    *,
    prompt: str,
    data: dict[str, Any],
    media: tuple[str, bytes] | None = None,
    timeout: float,
    retries: int = 1,
) -> T:
    """One schema repair retry, bounded by a total deadline, sanitized failures."""

    async def attempt() -> T:
        current_prompt = prompt
        for index in range(retries + 1):
            try:
                raw = await client.generate(
                    prompt=current_prompt, data=data, schema=schema, media=media
                )
                if len(raw) > 100000:
                    raise ModelFailure("model_response_oversized")
                return schema.model_validate_json(raw)
            except ValidationError:
                if index == retries:
                    raise ModelFailure("model_schema_invalid") from None
                # Never echo the malformed result into prompts/logs (could contain secrets).
                prompt_retry = (
                    "\nThe previous result failed schema validation. Return exact schema."
                )
                current_prompt += prompt_retry
        raise ModelFailure("model_schema_invalid")

    try:
        return await asyncio.wait_for(attempt(), timeout=timeout)
    except TimeoutError:
        raise ModelFailure("model_timeout") from None


def _merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        elif value is not None:
            merged[key] = value
    return merged


class IntakeTextAgent:
    def __init__(self, client: ModelClient) -> None:
        self.client = client
        self.guard = SafetyGuard()

    async def respond(
        self,
        *,
        text: str,
        facts: CaseFacts,
        language: Language,
        now: datetime,
        first_turn: bool = False,
        history: list[dict[str, str]] | None = None,
    ) -> IntakeReply:
        if language not in {"en", "hi"} or not 1 <= len(text) <= 4000:
            raise ValueError("invalid_intake_input")
        if now.tzinfo is None:
            raise ValueError("server_time_requires_timezone")
        safe_text = scrub_credentials(text)
        safe_history: list[dict[str, str]] = []
        history_size = 0
        for item in reversed((history or [])[-6:]):
            statement = UserStatement.model_validate(item)
            sanitized = scrub_credentials(statement.text)
            if history_size + len(sanitized) > 16000:
                break
            history_size += len(sanitized)
            safe_history.insert(0, {"text": sanitized, "at": statement.at.isoformat()})
        input_flags = list(self.guard.inspect_input(safe_text).flags)
        if safe_text != text:
            input_flags.append("credential_redacted")
        distress = bool(_distress.search(safe_text))
        delta: dict[str, Any] = {}
        degraded = False
        upload = None
        if not distress:
            try:
                output = await _validated(
                    self.client,
                    IntakeModelOutput,
                    prompt=_prompt("intake_text", version="v2"),
                    data={
                        "untrustedText": safe_text,
                        "untrustedHistory": safe_history,
                        "knownFacts": facts.model_dump(mode="json", by_alias=True),
                        "caseLanguage": language,
                        "serverNow": now.isoformat(),
                    },
                    timeout=19,
                )
                distress = output.distress
                if not distress:
                    delta = output.facts_delta.model_dump(
                        mode="json", by_alias=True, exclude_unset=True, exclude_none=True
                    )
                    serialized = json.dumps(delta, ensure_ascii=False)
                    if scrub_credentials(serialized) != serialized:
                        raise ModelFailure("model_secret_output")
                    # A model may not create confirmed provenance or trigger mutations.
                    delta.pop("fieldProvenance", None)
                    if "country" in delta and delta["country"]:
                        country = delta["country"].get("value")
                        if not isinstance(country, str) or not re.fullmatch(r"[A-Z]{2}", country):
                            raise ModelFailure("model_country_invalid")
                        delta["country"]["provenance"] = {"source": "victim_statement"}
                    upload = output.request_upload
            except ModelFailure:
                delta = {}
                degraded = True
        combined = CaseFacts.model_validate(
            _merge(facts.model_dump(mode="json", by_alias=True), delta)
        )
        missing = minimum_facts(combined)
        ready = not missing and not distress and not degraded
        if distress:
            reply = DISTRESS[language]
        elif degraded:
            reply = {
                "en": "I couldn't read all of that reliably. Please try again, or use Change "
                "to enter the missing details.",
                "hi": "मैं आपकी पूरी बात ठीक से नहीं समझ सका। कृपया फिर से लिखें, या जानकारी "
                "खुद भरने के लिए बदलें का उपयोग करें।",
            }[language]
            if missing:
                reply += " " + QUESTIONS[language][missing[0]]
        elif missing:
            reply = QUESTIONS[language][missing[0]]
        else:
            reply = {
                "en": "Your details are ready. Check them before continuing.",
                "hi": "आपकी जानकारी तैयार है। आगे बढ़ने से पहले इसे जाँच लें।",
            }[language]
        if first_turn and not distress:
            reply = FIRST_ACTION[language] + " " + reply
        # All user-visible replies are deterministic, but still pass the same output boundary.
        if not self.guard.inspect_output(reply).allow:
            reply = QUESTIONS[language]["country"]
            degraded = True
            ready = False
        return IntakeReply(
            text=reply,
            lang=language,
            facts_delta=delta,
            missing_minimum=missing,
            distress=distress,
            processing_ready=ready,
            request_upload=upload,
            safety_flags=input_flags,
            model=self.client.model_id,
            mode=self.client.mode,
            degraded=degraded,
        )


class EvidenceAgent:
    def __init__(
        self, client: ModelClient, *, schema_retries: int = 1, timeout: float = 119
    ) -> None:
        self.client = client
        self.guard = SafetyGuard()
        if schema_retries not in {0, 1} or not 0 < timeout <= 119:
            raise ValueError("invalid_model_bounds")
        self.schema_retries = schema_retries
        self.timeout = timeout

    async def extract(
        self,
        *,
        evidence_id: str,
        mime: str,
        content: bytes | str,
        case_language: str,
    ) -> EvidenceExtraction:
        if not evidence_id or case_language not in {"en", "hi", "hi-en"}:
            raise ValueError("invalid_evidence_input")
        if mime not in self.guard.ALLOWED_MIMES:
            raise ValueError("unsupported_media_type")
        raw = content.encode("utf-8") if isinstance(content, str) else content
        if not 0 < len(raw) <= self.guard.MAX_BYTES:
            raise ValueError("invalid_evidence_size")
        text = raw.decode("utf-8", errors="strict") if mime == "text/plain" else ""
        if text and scrub_credentials(text) != text:
            raise ModelFailure("evidence_secret_rejected")
        input_flags = self.guard.inspect_input(text).flags
        result = await _validated(
            self.client,
            EvidenceModelOutput,
            prompt=_prompt("evidence"),
            data={"untrustedText": text, "caseLanguage": case_language},
            media=(mime, raw) if mime != "text/plain" else None,
            timeout=self.timeout,
            retries=self.schema_retries,
        )
        if result.sensitive_content_detected or (
            mime != "text/plain" and not result.safety_scan_complete
        ):
            raise ModelFailure("evidence_secret_rejected")
        if not self.guard.inspect_output(result.summary + "\n" + result.notes).allow:
            raise ModelFailure("unsafe_extraction_text")
        entities = []
        for index, entity in enumerate(result.entities):
            if entity.type not in ENTITY_TYPES:
                raise ModelFailure("unsupported_entity_type")
            if any(
                scrub_credentials(value) != value
                for value in (entity.raw_value, entity.normalized_value)
            ):
                raise ModelFailure("evidence_secret_rejected")
            if mime == "text/plain" and entity.raw_value not in text:
                raise ModelFailure("entity_not_in_evidence")
            entities.append(
                Entity(
                    entity_id=f"{evidence_id}:entity:{index + 1}",
                    **entity.model_dump(),
                    status="extracted",
                )
            )
        return EvidenceExtraction(
            evidence_id=evidence_id,
            document_type=result.document_type,
            entities=entities,
            summary=result.summary,
            confidence=result.confidence,
            injection_suspected=result.injection_suspected or bool(input_flags),
            notes=result.notes,
            model=self.client.model_id,
            prompt_version="evidence.v1",
        )
