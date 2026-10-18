"""Strict extraction DTOs retain provenance that executable Pack schemas lack."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from packages.schemas import Model, Source

Text = Annotated[str, Field(min_length=1, max_length=2000)]
Short = Annotated[str, Field(min_length=1, max_length=300)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
RuleId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]


class SourcePassage(Model):
    model_config = ConfigDict(frozen=True)
    passage_id: Short
    text: Text
    page: int | None = Field(default=None, ge=1, le=200)
    offset_start: int = Field(ge=0)
    offset_end: int = Field(gt=0)
    text_sha256: Digest


class ImmutableSource(Model):
    model_config = ConfigDict(frozen=True)
    source: Source
    passages: tuple[SourcePassage, ...] = Field(min_length=1, max_length=400)
    extraction_hash: Digest


class EvidenceSpan(Model):
    passage_id: Short
    offset_start: int = Field(ge=0)
    offset_end: int = Field(gt=0)
    quote: Text
    paraphrase: Text
    passage_sha256: Digest


class Candidate(Model):
    id: RuleId
    source_refs: list[Short] = Field(min_length=1, max_length=8)
    evidence_spans: list[EvidenceSpan] = Field(min_length=1, max_length=8)
    status: Literal["unverified"] = "unverified"
    ambiguous: bool = False
    conflict: bool = False
    notes: str = Field(default="", max_length=1000)


class ChannelCandidate(Model):
    type: Literal["phone", "portal", "app", "email", "in_person", "website"]
    value: Short


class RecipientCandidate(Candidate):
    name: Short
    recipient_type: Literal[
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
    channels: list[ChannelCandidate] = Field(default_factory=list, max_length=6)


class RecipientsPass(Model):
    items: list[RecipientCandidate] = Field(default_factory=list, max_length=12)


class DeadlineCandidate(Candidate):
    applies_to: list[Short] = Field(min_length=1, max_length=8)
    from_event: Literal["payment_timestamp", "discovery_timestamp", "report_timestamp"] | None = (
        None
    )
    duration: str | None = Field(default=None, max_length=80)
    wording: Text
    obligation: Literal["mandatory", "advisory", "unclear"]
    consequence: str = Field(default="", max_length=2000)


class DeadlinesPass(Model):
    items: list[DeadlineCandidate] = Field(default_factory=list, max_length=12)


class RemedyCandidate(Candidate):
    summary: Text
    eligibility: str = Field(default="", max_length=2000)
    coverage: str = Field(default="", max_length=2000)
    limits: str = Field(default="", max_length=1000)
    conditions: str = Field(default="", max_length=2000)


class RemediesPass(Model):
    items: list[RemedyCandidate] = Field(default_factory=list, max_length=12)


class SequenceCandidate(Candidate):
    recipient_name: Short
    order: int | None = Field(default=None, ge=1, le=30)
    rationale: Text
    form_fields: list[Short] = Field(default_factory=list, max_length=30)
    unordered: bool = True


class SequencingPass(Model):
    items: list[SequenceCandidate] = Field(default_factory=list, max_length=12)


class SupportCandidate(Candidate):
    name: Short
    channel: Short


class SupportPass(Model):
    items: list[SupportCandidate] = Field(default_factory=list, max_length=12)


class RuleVerdict(Model):
    item_id: RuleId
    verdict: Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED", "CONTRADICTED"]
    missing: str | None = Field(default=None, max_length=2000)
    passage_refs: list[Short] = Field(min_length=1, max_length=8)


class CriticOutput(Model):
    verdicts: list[RuleVerdict] = Field(max_length=12)


class ReviewedCandidate(Model):
    item_id: RuleId
    pass_name: Literal["recipients", "deadlines", "remedies", "sequencing", "support"]
    verdict: RuleVerdict
    status: Literal["unverified"] = "unverified"
    excluded: bool
    requires_human_review: Literal[True] = True


class PackBuildResult(Model):
    status: Literal["draft"] = "draft"
    jurisdiction_code: str
    name: str
    archetype: Literal["centralized_rail", "mandatory_reimbursement", "fragmented"]
    source_proof_hash: Digest
    sources: list[Source]
    recipients: RecipientsPass
    deadlines: DeadlinesPass
    remedies: RemediesPass
    sequencing: SequencingPass
    support: SupportPass
    review: list[ReviewedCandidate]
    prompt_version: Literal["packbuilder-v1"] = "packbuilder-v1"
    model: str
    completed_passes: list[str]
    requires_human_review: Literal[True] = True
