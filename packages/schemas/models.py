"""Versioned schemas; pack files use snake_case, transport uses camelCase aliases."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def utc_timestamps(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("timestamp requires a timezone")
            return value.astimezone(UTC)
        return value


class KeyFact(Model):
    key: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=160)
    value: str = Field(max_length=2000)
    provenance: str = Field(max_length=500)


class MissingItem(Model):
    key: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=160)


class Suggestion(Model):
    action: Literal[
        "acknowledge", "request_info", "place_hold_simulated", "reject_with_reason", "escalate"
    ]
    why: str = Field(min_length=1, max_length=2000)


class ReceiverBrief(Model):
    completeness_score: float = Field(ge=0, le=1)
    missing_items: list[MissingItem] = Field(max_length=40)
    key_facts: list[KeyFact] = Field(max_length=60)
    risk_signals: list[dict[str, str]] = Field(max_length=20)
    suggested_actions: list[Suggestion] = Field(max_length=10)
    draft_reply_to_victim: dict[str, str] = Field(max_length=4)


class CaseStatus(StrEnum):
    INTAKE = "INTAKE"
    CLASSIFIED = "CLASSIFIED"
    PLAN_READY = "PLAN_READY"
    PACKETS_VERIFIED = "PACKETS_VERIFIED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class PacketStatus(StrEnum):
    DRAFT = "DRAFT"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    VERIFIED = "VERIFIED"
    APPROVED = "APPROVED"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    NEEDS_INFO = "NEEDS_INFO"
    ACTIONED = "ACTIONED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


class Money(Model):
    # JSON decimal string deliberately avoids binary floating-point corruption.
    value: Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=8)]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class Provenance(Model):
    source: Literal[
        "victim_statement",
        "statement",
        "inferred",
        "selected",
        "confirmed",
        "extracted",
        "computed",
    ]
    reference: str | None = None
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None


class FactValue(Model):
    value: str | int | bool | None = None
    availability: Literal["available", "not_available", "unknown"] = "available"
    provenance: Provenance


class Identifier(Model):
    type: str
    value: str


class Payment(Model):
    method: Literal["upi", "bank_transfer", "card", "wallet", "crypto", "cash", "other"] | None = (
        None
    )
    amount: Money | None = None
    timestamp: datetime | None = None
    authorized_by_victim: bool | None = None
    recipient_identifier: Identifier | None = None
    transaction_ref: str | None = None

    @field_validator("timestamp")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamp requires a timezone")
        return value


class Contact(Model):
    channel: (
        Literal["phone", "sms", "whatsapp", "email", "social", "marketplace", "website", "other"]
        | None
    ) = None
    identifier: str | None = None
    claimed_identity: str | None = None


class CaseFacts(Model):
    country: FactValue | None = None
    payment: Payment = Field(default_factory=Payment)
    contact: Contact = Field(default_factory=Contact)
    victim_bank: str | None = None
    ongoing_contact: bool | None = None
    credentials_shared: list[
        Literal["none", "otp", "pin", "password", "card_details", "remote_access"]
    ] = Field(default_factory=list)
    victim_age_band: str | None = None
    languages: list[str] = Field(default_factory=list)
    discovery_timestamp: datetime | None = None
    report_timestamp: datetime | None = None
    field_provenance: dict[str, Provenance] = Field(default_factory=dict)
    unavailable_fields: list[str] = Field(default_factory=list)


class Urgency(Model):
    level: Literal["critical", "high", "normal"]
    reason: str


class Classification(Model):
    typology: Literal[
        "bank_impersonation",
        "official_impersonation",
        "investment",
        "romance",
        "job_task",
        "marketplace",
        "rental",
        "tech_support",
        "crypto",
        "phishing_credential",
        "recovery_scam",
        "other",
    ]
    authorization_type: Literal[
        "authorized_manipulated", "unauthorized_access", "card_unauthorized", "unclear"
    ]
    authorization_rationale: str
    urgency: Urgency
    funds_likely_in_system: Literal["yes", "no", "unknown"] = "unknown"
    vulnerability_flags: list[str] = Field(default_factory=list)
    confidence: Annotated[float, Field(ge=0, le=1)]
    needs_human_review: bool = False
    clarifying_question: str | None = None
    degraded: bool = False
    failure_code: Literal["model_unavailable", "schema_invalid", "unsafe_output"] | None = None


class Source(Model):
    id: str
    title: str
    publisher: str
    url: str
    retrieved_at: str
    sha256: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")]


class Rule(Model):
    id: str
    source_refs: list[str] = Field(default_factory=list)
    status: Literal["verified", "unverified"] = "unverified"


class Channel(Model):
    type: Literal["phone", "portal", "app", "email", "in_person", "website"]
    value: str
    verified: bool = False


class Recipient(Rule):
    type: Literal[
        "bank",
        "national_cyber_authority",
        "police",
        "payment_app",
        "telecom",
        "platform",
        "ombudsman",
        "reimbursement_scheme",
        "support_org",
    ]
    name: str
    channels: list[Channel]
    applies_when: str = "True"
    required_fields: list[str] = Field(default_factory=list)
    template_id: str | None = None
    recipient_language: str = "en"
    typology_categories: dict[str, str] = Field(default_factory=dict)


class Sequencing(Rule):
    step: Annotated[int, Field(ge=1)]
    recipient_id: str
    when: str = "True"
    rationale: str


class Deadline(Rule):
    applies_to: list[str]
    from_event: Literal["payment_timestamp", "discovery_timestamp", "report_timestamp"]
    duration: str | None = None
    type: Literal["soft", "hard"]
    consequence: str
    calendar: Literal["calendar", "business"] = "calendar"
    calendar_country: str | None = None


class LiabilityRule(Rule):
    condition: str
    summary: str
    limits: str = ""


class Form(Model):
    id: str
    recipient_id: str
    fields: list[str | dict[str, Any]] = Field(default_factory=list)
    format: Literal["text", "pdf", "portal_steps"] = "text"


class CrisisSupport(Model):
    name: str
    channel: str
    source_refs: list[str] = Field(default_factory=list)
    status: Literal["verified", "unverified"] = "unverified"


class PackReview(Model):
    reviewer: str = ""
    reviewed_at: str = ""
    notes: str = ""
    accepted_unverified_rule_ids: list[str] = Field(default_factory=list)


class Jurisdiction(Model):
    code: str
    name: str
    archetype: Literal["centralized_rail", "mandatory_reimbursement", "fragmented"]


class Pack(Model):
    pack_id: str
    version: str
    status: Literal["draft", "reviewed", "published", "retired"] = "draft"
    jurisdiction: Jurisdiction
    languages: list[str]
    timezone: str
    currency: str
    sources: list[Source] = Field(default_factory=list)
    recipients: list[Recipient] = Field(default_factory=list)
    sequencing: list[Sequencing] = Field(default_factory=list)
    deadlines: list[Deadline] = Field(default_factory=list)
    liability_rules: list[LiabilityRule] = Field(default_factory=list)
    forms: list[Form] = Field(default_factory=list)
    crisis_support: list[CrisisSupport] = Field(default_factory=list)
    disclaimers: list[str] = Field(default_factory=list)
    review: PackReview = Field(default_factory=PackReview)


class Entity(Model):
    entity_id: str
    type: str
    raw_value: str
    normalized_value: str
    role: Literal["victim", "scammer", "merchant", "unknown"]
    confidence: Annotated[float, Field(ge=0, le=1)]
    span: dict[str, Any] | None = None
    status: Literal["extracted", "confirmed", "edited", "unrelated"] = "extracted"


class EvidenceExtraction(Model):
    evidence_id: str
    document_type: str
    entities: list[Entity]
    summary: str
    confidence: Annotated[float, Field(ge=0, le=1)]
    injection_suspected: bool = False
    notes: str = ""
    model: str
    prompt_version: str


class DeadlineState(Model):
    rule_id: str
    label: str
    type: Literal["soft", "hard"]
    due_at: datetime | None = None
    state: Literal["upcoming", "due_soon", "overdue", "not_applicable", "unsupported_in_v1"]
    status_text: str


class PlanStep(Model):
    step_no: int
    recipient_id: str
    action: str
    why_now: str
    channel: Channel
    deadline: DeadlineState | None = None
    packet_id: str | None = None
    rule_refs: list[str]
    source_refs: list[str]
    recipient_name: str = ""
    recipient_type: str = ""
    additional_channels: list[Channel] = Field(default_factory=list)


class PlanSourceCitation(Model):
    reference: str
    title: str
    publisher: str
    url: str
    passage: Annotated[str, Field(max_length=4000)]
    retrieved_at: str
    snapshot_hash: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")]
    status: Literal["verified", "unverified"] = "unverified"


class Plan(Model):
    plan_id: str
    pack_id: str
    pack_version: str
    pack_status: Literal["draft", "reviewed", "published"]
    generated_at: datetime
    steps: list[PlanStep]
    unverified_notices: list[dict[str, str]] = Field(default_factory=list)
    facts_revision: Annotated[int, Field(ge=0)] = 0
    facts_hash: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")] | None = None
    pack_hash: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")] | None = None
    input_hash: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")] | None = None
    catalog_hash: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")] | None = None
    classification: Classification | None = None
    country_code: str | None = None
    resolution_reason: str = ""
    resolution_confidence: Annotated[float, Field(ge=0, le=1)] = 0
    generic_guidance: bool = False
    draft_preview: bool = False
    source_citations: list[PlanSourceCitation] = Field(default_factory=list)
    stale: bool = False
    processing_ms: Annotated[int, Field(ge=0)] = 0


class VerificationCheck(Model):
    id: str
    type: Literal["deterministic", "llm"]
    passed: bool
    detail: str
    severity: Literal["blocker", "warning"]


class PacketField(Model):
    key: str
    label: str
    value: str | None = None
    required: bool = False
    availability: Literal["available", "not_available", "unknown"] = "available"
    provenance: Provenance


class PacketContent(Model):
    language: str
    recipient_language: str
    subject: str
    summary: str
    fields: list[PacketField]
    message: str
    requested_actions: list[str]
    citations: list[dict[str, str]]
    attachments: list[dict[str, str]]
    victim_copy: dict[str, str]
    footer: str
    completeness: dict[str, Any]


class Approval(Model):
    actor_uid: str
    packet_id: str
    packet_version: Annotated[int, Field(ge=1)]
    confirmed_recipient_id: str
    content_hash: str
    approved_at: datetime


class ProblemDetail(Model):
    type: str
    title: str
    status: int
    code: str
    detail: str
    request_id: str
    field_errors: list[dict[str, str]] = Field(default_factory=list)
    retryable: bool = False


class Job(Model):
    job_id: str
    type: str
    state: Literal["queued", "running", "succeeded", "failed"]
    progress: dict[str, int]
    error: ProblemDetail | None = None
    result_ref: str | None = None


class JobAttributes(Model):
    type: Literal[
        "process_case",
        "process_evidence",
        "rebuild_packets",
        "verify_packet",
        "send_packet",
        "handoff_receiver",
        "compute_links",
        "pack_ingest",
        "pack_build",
        "eval_run",
        "synth_generate",
    ]
    schema_version: Literal["1"] = "1"
    case_id: str | None = None
    resource_id: str | None = None
    trace_id: str
    idempotency_key: str


class JobEnvelope(Model):
    attributes: JobAttributes
    payload: dict[str, Any]


class SafetyFlag(Model):
    type: Literal[
        "injection", "forbidden_request", "promise_of_recovery", "legal_conclusion", "pii"
    ]
    score: Annotated[float, Field(ge=0, le=1)]
    detail: str


class SafetyResult(Model):
    allow: bool
    flags: list[SafetyFlag]
    action: Literal["pass", "regenerate", "block"]


class LiveAuth(Model):
    type: Literal["auth"] = "auth"
    id_token: str
    app_check_token: str


class AudioFormat(Model):
    encoding: Literal["pcm_s16le"] = "pcm_s16le"
    sample_rate_hz: Literal[16000, 24000]
    channels: Literal[1] = 1


class LiveStart(Model):
    type: Literal["start"] = "start"
    case_id: str
    language: Literal["en", "hi"]
    audio: AudioFormat
    resume_handle: str | None = None


class Caption(Model):
    type: Literal["caption"] = "caption"
    role: Literal["user", "assistant"]
    text: str
    final: bool
    lang: str
    turn_id: str
