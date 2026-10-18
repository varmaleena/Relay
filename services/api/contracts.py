"""M0 contract-only router. Business operations deliberately return HTTP 501.

The executable health shell is separate. Role metadata describes the intended
permission matrix; these stubs never authorize or execute a business action.
"""
# mypy: disable-error-code="valid-type,call-overload"
# Dynamic Pydantic create_model types are runtime schemas, not static type aliases.

import inspect
import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field, create_model

from packages.evaluation.models import EvalCaptureReport
from packages.schemas import (
    CaseFacts,
    CaseStatus,
    Classification,
    DeadlineState,
    Entity,
    EvidenceExtraction,
    Job,
    KeyFact,
    MissingItem,
    Model,
    Pack,
    PacketContent,
    PacketStatus,
    Plan,
    ProblemDetail,
    ReceiverBrief,
    VerificationCheck,
)

PositiveInt = Annotated[int, Field(ge=1)]
Language = Literal["en", "hi"]
Object = dict[str, Any]


def shape(model_name: str, **fields: Any) -> type[Model]:
    """Create a named strict schema; tuple fields supply an explicit default."""
    return create_model(
        model_name,
        __base__=Model,
        **{
            key: value if isinstance(value, tuple) else (value, ...)
            for key, value in fields.items()
        },
    )


Flags = shape(
    "Flags", distress=(bool, False), injection_attempt=(bool, False), low_confidence=(bool, False)
)
Verification = shape(
    "Verification", passed=bool, checks=list[VerificationCheck], iterations=(int, 0)
)
Delivery = shape(
    "Delivery",
    adapter=Literal["mcp-rail-mock", "mcp-bank-mock", "a2a-receiver"],
    ticket_ref=str,
    simulated=Literal[True],
    sent_at=str,
    status=(str, "RECEIVED"),
    missing_items=(list[str], []),
)
PacketSummary = shape(
    "PacketSummary",
    packet_id=str,
    recipient_id=str,
    version=PositiveInt,
    status=PacketStatus,
    recipient_name=(str, ""),
    stale=(bool, False),
    plan_id=(str, ""),
    delivery=(Delivery | None, None),
)
InformationRequest = shape(
    "InformationRequest",
    request_id=str,
    packet_version=PositiveInt,
    requested_items=list[MissingItem],
    message=str,
    state=Literal["open", "answered", "cancelled"],
    created_at=str,
    answered_at=(str | None, None),
    answer_version=(PositiveInt | None, None),
)
Packet = shape(
    "Packet",
    packet_id=str,
    recipient_id=str,
    version=PositiveInt,
    status=PacketStatus,
    content=PacketContent,
    verification=Verification,
    delivery=(Delivery | None, None),
    deadlines=(list[DeadlineState], []),
    recipient_name=(str, ""),
    plan_id=(str, ""),
    stale=(bool, False),
    facts_revision=(int, 0),
    content_hash=(str, ""),
    information_requests=(list[InformationRequest], []),
)
PdfDownload = shape("PdfDownload", download_url=str, expires_at=str)
PacketGenerate = shape("PacketGenerateRequest", plan_id=str)
Notification = shape(
    "Notification",
    notification_id=str,
    packet_id=str,
    kind=str,
    created_at=str,
    read_at=(str | None, None),
    text=str,
)
Event = shape(
    "Event",
    event_id=str,
    ts=str,
    actor_type=Literal["victim", "receiver", "agent", "system", "reviewer"],
    actor_id=str,
    action=str,
    target_type=str,
    target_id=str,
    payload_hash=str,
    trace_id=str,
    details=(Object, {}),
)
Pointer = shape("EvidencePointer", case_ref=str, entity_type=str)
Explanation = shape(
    "LinkExplanation",
    text=str,
    confidence_band=Literal["possible", "likely"],
    evidence_pointers=list[Pointer],
)
LinkValidation = shape(
    "LinkValidation",
    decision=Literal["related", "not_related"] | None,
    by=(str | None, None),
    at=(str | None, None),
)
CaseLink = shape(
    "CaseLink",
    link_id=str,
    case_refs=list[str],
    shared_entity_types=list[str],
    strength=Annotated[float, Field(ge=0, le=1)],
    explanation=Explanation,
    validation=LinkValidation,
)
ReceiverCaseSummary = shape(
    "ReceiverCaseSummary",
    case_id=str,
    case_ref=str,
    packet_id=str,
    recipient_name=str,
    urgency=str,
    typology=str,
    status=PacketStatus,
    updated_at=str,
)
ReceiverCaseView = shape(
    "ReceiverCaseView",
    case_ref=str,
    jurisdiction=str,
    urgency=str,
    typology=str,
    authorization_type=str,
    minutes_since_payment=int | None,
    key_facts=list[KeyFact],
    packet=Packet,
    evidence=list[Object],
    timeline=list[Event],
    links=list[CaseLink],
    brief=ReceiverBrief,
    brief_status=(Literal["generated", "unavailable"], "unavailable"),
)
TranscriptTurn = shape(
    "TranscriptTurn", turn_id=str, role=Literal["user", "assistant"], text=str, lang=str, ts=str
)
EvidenceSummary = shape(
    "EvidenceSummary",
    evidence_id=str,
    type=str,
    status=Literal["awaiting_upload", "queued", "ready", "rejected"],
)
CaseView = shape(
    "CaseView",
    case_id=str,
    case_ref=str,
    status=CaseStatus,
    facts=CaseFacts,
    classification=(Classification | None, None),
    flags=Flags,
    plan=(Plan | None, None),
    packets=(list[PacketSummary], []),
    facts_revision=(int, 0),
    created_at=(str | None, None),
    updated_at=(str | None, None),
    ttl_at=(str | None, None),
    transcript=(list[TranscriptTurn], []),
    evidence=(list[EvidenceSummary], []),
)
AuditExport = shape(
    "AuditExport",
    case=CaseView,
    packets=list[Packet],
    events=list[Event],
    evidence=list[EvidenceExtraction],
    pipeline=list[Object],
)
PackSummary = shape(
    "PackSummary",
    pack_id=str,
    version=str,
    jurisdiction=str,
    status=Literal["draft", "reviewed", "published", "retired"],
    name=str,
)
RuleVerdict = shape(
    "RuleVerdict",
    item_id=str,
    verdict=Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED", "CONTRADICTED"],
    missing=(str | None, None),
    passage_refs=list[str],
)
PackDraftItem = shape(
    "PackDraftItem",
    id=str,
    body=Object,
    source_refs=list[str],
    supporting_paraphrase=str,
    status=Literal["unverified", "verified"],
    conflict=(bool, False),
)
PackDraft = shape(
    "PackDraft",
    recipients=(list[PackDraftItem], []),
    sequencing=(list[PackDraftItem], []),
    deadlines=(list[PackDraftItem], []),
    liability_rules=(list[PackDraftItem], []),
    forms=(list[PackDraftItem], []),
    crisis_support=(list[PackDraftItem], []),
    conflicts=(list[Object], []),
)
PackBuild = shape(
    "PackBuild",
    state=Literal["queued", "running", "draft", "reviewed", "published", "failed"],
    passes=list[Object],
    draft=PackDraft,
    verdicts=list[RuleVerdict],
    eval_vs_gold=(Object | None, None),
    revision=(PositiveInt, 1),
    reviews=(dict[str, Object], {}),
    publication_blockers=(list[str], []),
    source_ids=(list[str], []),
)
Metric = shape(
    "Metric",
    system=str,
    metric=str,
    slice=str,
    value=float | None,
    ci_low=float | None,
    ci_high=float | None,
    n=Annotated[int, Field(ge=0)],
)
RunSummary = shape(
    "RunSummary", run_id=str, dataset_version=str, n=int, started_at=str, finished_at=str | None
)
RunReport = shape(
    "RunReport",
    run_id=(str, ""),
    execution_mode=(Literal["offline_fixture", "not_measured"], "not_measured"),
    capture_report=(EvalCaptureReport | None, None),
    dataset_version=str,
    n=int,
    date=str,
    systems=list[str],
    metrics=list[Metric],
    pack_builder=Object,
    redteam=Object,
    latency=Object,
    cost_per_case=Object,
)
EvidenceView = shape(
    "EvidenceView",
    evidence_id=str,
    type=str,
    status=str,
    extraction=(EvidenceExtraction | None, None),
    safety=Object,
    preview_url=str,
)
AsyncAccepted = shape("AsyncAccepted", job_id=str, status_url=str)
ConsentCreate = shape(
    "CreateCaseRequest", language=Language, country_hint=(str | None, None), consent_version=str
)
CreatedCase = shape(
    "CreatedCase", case_id=str, case_ref=str, status=Literal["INTAKE"], created_at=str
)
FactsUpdate = shape(
    "FactsUpdateRequest",
    facts=CaseFacts,
    source=Literal["confirmed"],
    if_revision=(Annotated[int, Field(ge=0)] | None, None),
)
FactsResult = shape(
    "FactsResult",
    facts=CaseFacts,
    missing_minimum=list[str],
    reprocess_recommended=bool,
    facts_revision=(int, 0),
)
MessageRequest = shape(
    "MessageRequest",
    text=Annotated[str, Field(min_length=1, max_length=4000)],
    lang=(str | None, None),
    evidence_ids=(list[str], []),
)
Reply = shape("Reply", text=str, lang=str)
MessageResult = shape(
    "MessageResult",
    turn_id=str,
    reply=Reply,
    facts_delta=CaseFacts,
    missing_minimum=list[str],
    processing_queued=bool,
    flags=Flags,
    facts_revision=(int, 0),
)
UploadRequest = shape(
    "UploadRequest",
    kind=Literal["screenshot", "chat_export", "receipt", "other"],
    mime=Literal["image/png", "image/jpeg", "image/webp", "application/pdf", "text/plain"],
    size_bytes=Annotated[int, Field(gt=0, le=10485760)],
    sha256=(str | None, None),
)
UploadResult = shape(
    "UploadResult",
    evidence_id=str,
    upload_url=str,
    method=Literal["PUT"],
    headers=dict[str, str],
    expires_at=str,
)
EntityDecision = shape(
    "EntityDecision",
    entity_id=str,
    decision=Literal["confirm", "edit", "unrelated"],
    value=(str | None, None),
)
Confirmation = shape("EvidenceConfirmRequest", items=list[EntityDecision])
ConfirmedEntities = shape("ConfirmedEntities", entities=list[Entity], missing_minimum=list[str])
ProcessRequest = shape("ProcessRequest", force=(bool, False), preview_draft=(bool, False))
RerunRequest = shape(
    "RerunRequest",
    jurisdiction_code=(str | None, None),
    pack_version=(str | None, None),
    preview_draft=(bool, False),
)
FieldEdit = shape(
    "FieldEdit",
    key=str,
    value=str,
    availability=(Literal["available", "not_available"], "available"),
)
PacketEdit = shape(
    "PacketEditRequest",
    message=(str | None, None),
    fields=(list[FieldEdit], []),
    if_version=PositiveInt,
)
PacketEditResult = shape(
    "PacketEditResult", packet_id=str, version=PositiveInt, status=Literal["DRAFT"], job_id=str
)
ApproveRequest = shape(
    "ApproveRequest", confirm=Literal[True], confirmed_recipient_id=str, packet_version=PositiveInt
)
SendResult = shape("SendResult", packet_id=str, status=Literal["SENT"], delivery=Delivery)
AnswerItem = shape(
    "AnswerItem",
    item_key=str,
    value=str,
    availability=(Literal["available", "not_available"], "available"),
)
AnswerRequest = shape(
    "AnswerRequest", request_id=str, answers=list[AnswerItem], if_version=PositiveInt
)
# Answer creates a new version; fresh E17 approval is required for re-send.
AnswerResult = shape(
    "AnswerResult",
    packet_id=str,
    version=PositiveInt,
    status=Literal["VERIFIED", "DRAFT"],
    requires_approval=Literal[True],
    job_id=(str | None, None),
)
DecisionRequest = shape(
    "DecisionRequest",
    action=Literal["acknowledge", "request_info", "place_hold_simulated", "reject", "escalate"],
    reason=(str | None, None),
    requested_items=(list[str], []),
    message=(str | None, None),
    packet_version=PositiveInt,
)
AdapterResult = shape("AdapterResult", ref=str, status=str, simulated=Literal[True], text=str)
DecisionResult = shape(
    "DecisionResult",
    packet_id=str,
    status=PacketStatus,
    adapter_result=(AdapterResult | None, None),
)
ValidateLink = shape(
    "ValidateLinkRequest", decision=Literal["related", "not_related"], note=(str | None, None)
)
LinkResult = shape("LinkResult", link_id=str, decision=Literal["related", "not_related"])
SourceCreate = shape(
    "SourceCreateRequest",
    kind=Literal["upload", "url"],
    url=(str | None, None),
    title=str,
    publisher=str,
    language=str,
)
SourceCreated = shape("SourceCreated", source_id=str, upload_url=(str | None, None))
Passage = shape(
    "Passage", passage_id=str, text=str, page=int | None, offset_start=int, offset_end=int
)
BuildRequest = shape(
    "BuildRequest",
    source_ids=Annotated[list[str], Field(min_length=1)],
    jurisdiction_code=str,
    name=str,
    archetype=Literal["centralized_rail", "mandatory_reimbursement", "fragmented"],
    gold_pack_id=(str | None, None),
)
BuildCreated = shape("BuildCreated", build_id=str, job_id=str, status_url=str)
RuleReviewRequest = shape(
    "RuleReviewRequest",
    action=Literal["accept", "edit", "reject"],
    if_revision=PositiveInt,
    edit=(Object | None, None),
    note=(str | None, None),
)
RuleReviewResult = shape("RuleReviewResult", rule_id=str, state=str, revision=PositiveInt)
PackReviewChecklist = shape(
    "PackReviewChecklist",
    sources_checked=Literal[True],
    contacts_checked=Literal[True],
    scope_conditions_checked=Literal[True],
    languages_checked=Literal[True],
)
PublishRequest = shape(
    "PublishRequest",
    reviewer_name=Annotated[str, Field(min_length=1)],
    notes=str,
    accept_unverified_rule_ids=(list[str], []),
    pack_draft=Pack,
    if_revision=PositiveInt,
    review_checklist=PackReviewChecklist,
)
PublishedPack = shape("PublishedPack", pack_id=str, version=str, status=Literal["published"])
RetireRequest = shape("RetireRequest", reason=Annotated[str, Field(min_length=1)])
RetireResult = shape("RetireResult", pack_id=str, version=str, status=Literal["retired"])
Failure = shape("Failure", case_id=str, input_ref=str, expected=Any, actual=Any, note=str)
EvalRequest = shape(
    "EvalRequest",
    kind=Literal["smoke", "full"],
    dataset_version=str,
    systems=Annotated[
        list[
            Literal[
                "relay", "baseline", "ablation_rules", "ablation_no_verifier", "ablation_no_pack"
            ]
        ],
        Field(min_length=1),
    ],
)
EvalCreated = shape("EvalCreated", run_id=str, job_id=str)
ResetResult = shape("ResetResult", seeded=Literal[True])
ScenarioCreated = shape("ScenarioCreated", case_id=str)
AdapterBehavior = shape(
    "AdapterBehavior",
    bank_mode=Literal["success", "needs_info", "funds_moved", "auto"],
    rail_mode=Literal["success", "misrouted"],
)
Ok = shape("Ok", status=Literal["ok"])
Ready = shape("Ready", status=Literal["ready"], deps=dict[str, bool])
Version = shape("Version", git_sha=str, built_at=str)
PublicConfig = shape(
    "PublicConfig",
    supported_languages=list[str],
    demo_mode=bool,
    sim_banner=str,
    planning_enabled=(bool, False),
    draft_pack_preview_available=(bool, False),
    packets_enabled=(bool, False),
    live_enabled=(bool, False),
    sources_enabled=(bool, False),
    packstudio_enabled=(bool, False),
    linking_enabled=(bool, False),
)
Empty = shape("EmptyRequest")


def page(name: str, item: Any) -> type[Model]:
    return shape(name, items=list[item], next_cursor=(str | None, None))


# Roles are authenticated claims. owner/org scope is an additional requirement.
# Admin has no victim approval or institution-decision permission.
OPERATIONS = [
    ("E1", "POST", "/cases", "V", ConsentCreate, CreatedCase, 201, "owner"),
    (
        "E2",
        "GET",
        "/cases/{caseId}",
        "VRA",
        None,
        CaseView | ReceiverCaseView,
        200,
        "owner_or_addressed_projection",
    ),
    ("E3", "DELETE", "/cases/{caseId}", "VA", None, None, 204, "owner_or_admin"),
    ("E4", "PATCH", "/cases/{caseId}/facts", "V", FactsUpdate, FactsResult, 200, "owner"),
    ("E5", "POST", "/cases/{caseId}/messages", "V", MessageRequest, MessageResult, 200, "owner"),
    ("E6", "POST", "/cases/{caseId}/uploads", "V", UploadRequest, UploadResult, 201, "owner"),
    (
        "E7",
        "POST",
        "/cases/{caseId}/evidence/{evidenceId}/complete",
        "V",
        Empty,
        AsyncAccepted,
        202,
        "owner",
    ),
    (
        "E8",
        "GET",
        "/cases/{caseId}/evidence/{evidenceId}",
        "VR",
        None,
        EvidenceView,
        200,
        "owner_or_packet_attachment",
    ),
    (
        "E9",
        "POST",
        "/cases/{caseId}/evidence/{evidenceId}/confirm",
        "V",
        Confirmation,
        ConfirmedEntities,
        200,
        "owner",
    ),
    (
        "E10",
        "POST",
        "/cases/{caseId}/process",
        "VA",
        ProcessRequest,
        AsyncAccepted,
        202,
        "owner_or_admin",
    ),
    ("E11", "GET", "/jobs/{jobId}", "VA", None, Job, 200, "resource_owner_or_admin"),
    ("E12", "GET", "/cases/{caseId}/plan", "V", None, Plan, 200, "owner"),
    (
        "E13",
        "POST",
        "/cases/{caseId}/plan/rerun",
        "VA",
        RerunRequest,
        AsyncAccepted,
        202,
        "owner_demo_or_admin",
    ),
    (
        "E14",
        "GET",
        "/cases/{caseId}/packets",
        "V",
        None,
        page("PacketList", PacketSummary),
        200,
        "owner",
    ),
    (
        "E15",
        "GET",
        "/cases/{caseId}/packets/{packetId}",
        "VR",
        None,
        Packet,
        200,
        "owner_or_recipient_org",
    ),
    (
        "E16",
        "PATCH",
        "/cases/{caseId}/packets/{packetId}",
        "V",
        PacketEdit,
        PacketEditResult,
        200,
        "owner",
    ),
    (
        "E17",
        "POST",
        "/cases/{caseId}/packets/{packetId}/approve",
        "V",
        ApproveRequest,
        SendResult,
        200,
        "owner_current_version_approval",
    ),
    (
        "E18",
        "GET",
        "/cases/{caseId}/packets/{packetId}/pdf",
        "VR",
        None,
        PdfDownload,
        200,
        "owner_or_recipient_org",
    ),
    (
        "E19",
        "POST",
        "/cases/{caseId}/packets/{packetId}/answer",
        "V",
        AnswerRequest,
        AnswerResult,
        200,
        "owner_no_implicit_resend",
    ),
    (
        "E20",
        "GET",
        "/cases/{caseId}/events",
        "VA",
        None,
        page("EventPage", Event),
        200,
        "owner_or_admin",
    ),
    ("E21", "GET", "/cases/{caseId}/export", "V", None, AuditExport, 200, "owner"),
    (
        "E22",
        "GET",
        "/console/cases",
        "R",
        None,
        page("ReceiverCasePage", ReceiverCaseSummary),
        200,
        "recipient_org",
    ),
    ("E23", "GET", "/console/cases/{caseId}", "R", None, ReceiverCaseView, 200, "recipient_org"),
    (
        "E24",
        "POST",
        "/console/cases/{caseId}/packets/{packetId}/decision",
        "R",
        DecisionRequest,
        DecisionResult,
        200,
        "recipient_org_human_decision",
    ),
    (
        "E25",
        "GET",
        "/console/cases/{caseId}/links",
        "R",
        None,
        page("CaseLinkList", CaseLink),
        200,
        "authorized_link_projection",
    ),
    (
        "E26",
        "POST",
        "/console/links/{linkId}/validate",
        "R",
        ValidateLink,
        LinkResult,
        200,
        "authorized_link",
    ),
    (
        "E27",
        "GET",
        "/packs",
        "VRPA",
        None,
        page("PackList", PackSummary),
        200,
        "published_or_reviewer_org",
    ),
    (
        "E28",
        "GET",
        "/packs/{packId}/versions/{version}",
        "VRPA",
        None,
        Pack,
        200,
        "published_redacted_or_reviewer_org",
    ),
    ("E29", "POST", "/sources", "PA", SourceCreate, SourceCreated, 201, "reviewer_org"),
    ("E30", "POST", "/sources/{sourceId}/ingest", "PA", Empty, AsyncAccepted, 202, "reviewer_org"),
    (
        "E31",
        "GET",
        "/sources/{sourceId}/passages",
        "PA",
        None,
        page("PassagePage", Passage),
        200,
        "reviewer_org",
    ),
    ("E32", "POST", "/pack-builds", "PA", BuildRequest, BuildCreated, 202, "reviewer_org"),
    ("E33", "GET", "/pack-builds/{buildId}", "PA", None, PackBuild, 200, "reviewer_org"),
    (
        "E34",
        "PATCH",
        "/pack-builds/{buildId}/rules/{ruleId}",
        "PA",
        RuleReviewRequest,
        RuleReviewResult,
        200,
        "reviewer_org",
    ),
    (
        "E35",
        "POST",
        "/pack-builds/{buildId}/publish",
        "PA",
        PublishRequest,
        PublishedPack,
        200,
        "reviewer_org_explicit_publication",
    ),
    (
        "E36",
        "POST",
        "/packs/{packId}/versions/{version}/retire",
        "PA",
        RetireRequest,
        RetireResult,
        200,
        "reviewer_org",
    ),
    ("E37", "GET", "/eval/runs", "PA", None, page("RunPage", RunSummary), 200, "reviewer_or_admin"),
    ("E38", "GET", "/eval/runs/{runId}", "PA", None, RunReport, 200, "public_only_if_public_eval"),
    (
        "E39",
        "GET",
        "/eval/runs/{runId}/failures",
        "PA",
        None,
        page("FailurePage", Failure),
        200,
        "reviewer_or_admin",
    ),
    ("E40", "POST", "/eval/runs", "A", EvalRequest, EvalCreated, 202, "admin"),
    ("E41", "POST", "/demo/reset", "A", Empty, ResetResult, 200, "admin_demo_only"),
    (
        "E42",
        "POST",
        "/demo/scenarios/{name}/load",
        "A",
        Empty,
        ScenarioCreated,
        201,
        "admin_demo_only",
    ),
    ("E43", "PUT", "/demo/adapters/behavior", "A", AdapterBehavior, Ok, 200, "admin_demo_only"),
    ("E44_health", "GET", "/healthz", "", None, Ok, 200, "public"),
    ("E44_ready", "GET", "/readyz", "", None, Ready, 200, "public"),
    ("E44_version", "GET", "/version", "", None, Version, 200, "public"),
    (
        "E45_generate",
        "POST",
        "/cases/{caseId}/packets/generate",
        "V",
        PacketGenerate,
        AsyncAccepted,
        202,
        "owner_current_plan",
    ),
    (
        "E46_notifications",
        "GET",
        "/cases/{caseId}/notifications",
        "V",
        None,
        page("NotificationList", Notification),
        200,
        "owner",
    ),
    (
        "E47_read",
        "POST",
        "/cases/{caseId}/notifications/{notificationId}/read",
        "V",
        Empty,
        Notification,
        200,
        "owner",
    ),
    ("E44_config", "GET", "/config/public", "", None, PublicConfig, 200, "public"),
]


def contract_app() -> FastAPI:
    """Generate the entire future API independently of the M0 health shell."""
    app = FastAPI(
        title="Relay API contracts",
        version="0.1.0",
        description=(
            "M0 design contracts only. Future business operations return 501; not implemented."
        ),
    )

    @app.exception_handler(HTTPException)
    async def contract_error(request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=ProblemDetail(
                type="https://relay.example/errors/not_implemented",
                title="Contract only",
                status=error.status_code,
                code="not_implemented",
                detail=str(error.detail),
                request_id=request.headers.get("X-Request-Id", "contract-only"),
            ).model_dump(by_alias=True),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ProblemDetail(
                type="https://relay.example/errors/validation_failed",
                title="Request validation failed",
                status=422,
                code="validation_failed",
                detail="Request does not match the contract",
                request_id=request.headers.get("X-Request-Id", "contract-only"),
                field_errors=[
                    {
                        "field": ".".join(map(str, item["loc"])),
                        "message": item["msg"],
                        "code": item["type"],
                    }
                    for item in error.errors()
                ],
            ).model_dump(by_alias=True),
        )

    router = APIRouter(prefix="/api/v1")
    for operation_id, method, path, roles, request, response, status, scope in OPERATIONS:

        async def stub(**kwargs: Any) -> None:
            raise HTTPException(
                status_code=501, detail="Contract only: implementation belongs to a later milestone"
            )

        parameters = [
            inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)
            for name in re.findall(r"\{([^}]+)\}", path)
        ]
        if request is not None:
            stub.__annotations__["body"] = request
            # FastAPI recognizes required request body from a no-default signature.
            parameters += [
                inspect.Parameter(
                    "body", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=request
                ),
            ]
        stub.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
        router.add_api_route(
            path,
            stub,
            methods=[method],
            response_model=response,
            status_code=status,
            operation_id=operation_id,
            summary=f"{operation_id}: contract only",
            responses={
                code: {"model": ProblemDetail}
                for code in [400, 401, 403, 404, 409, 413, 415, 422, 429, 500, 501, 502, 503, 504]
            },
            openapi_extra={
                "x-relay-roles": list(roles),
                "x-relay-scope": scope,
                "x-relay-implemented": False,
                "x-relay-human-approval": operation_id in {"E17", "E24", "E35"},
                "x-relay-idempotency": method == "POST",
            },
        )
    app.include_router(router)
    return app


def business_contract_router() -> APIRouter:
    """Only future business contracts; health routes belong to the shell."""
    router = APIRouter()
    for route in contract_app().routes:
        if getattr(route, "operation_id", "").startswith("E44"):
            continue
        if getattr(route, "path", "").startswith("/api/v1"):
            router.routes.append(route)
    return router
