"""E1–E11 transport adapters; inference and durable data live in domain services."""
# mypy: disable-error-code="valid-type"
# Runtime named Pydantic contract models come from create_model.

from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response

from packages.intake.service import IntakeError, IntakeService
from packages.intake.storage import LocalFileBlobStore
from packages.safety import Actor
from services.api.contracts import (
    AsyncAccepted,
    Confirmation,
    ConfirmedEntities,
    ConsentCreate,
    CreatedCase,
    Empty,
    EvidenceView,
    FactsResult,
    FactsUpdate,
    Job,
    MessageRequest,
    MessageResult,
    Plan,
    ProcessRequest,
    RerunRequest,
    UploadRequest,
    UploadResult,
)


def create_intake_router(service: IntakeService) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def actor(request: Request) -> Actor:
        verified = getattr(request.state, "actor", None)
        if not isinstance(verified, Actor):
            raise IntakeError(401, "unauthenticated")
        if not getattr(request.state, "intake_rate_counted", False):
            request.state.intake_rate = service.rate_limit(
                verified,
                create=request.method == "POST" and request.url.path == "/api/v1/cases",
                client_key=request.client.host if request.client else "",
                deletion=request.method == "DELETE",
            )
            request.state.intake_rate_counted = True
        return verified

    def payload(model: Any) -> dict[str, Any]:
        return model.model_dump(mode="json", by_alias=True, exclude_unset=True)

    @router.post("/cases", response_model=CreatedCase, status_code=201, operation_id="E1")
    async def create(
        request: Request,
        body: ConsentCreate,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> Any:
        return service.create_case(actor(request), payload(body), idempotency_key)

    @router.get("/cases/{case_id}", operation_id="E2")
    async def get_case(request: Request, case_id: str) -> Any:
        return service.get_case(actor(request), case_id)

    @router.delete("/cases/{case_id}", status_code=204, operation_id="E3")
    async def delete(request: Request, case_id: str) -> Response:
        service.delete_case(actor(request), case_id)
        return Response(status_code=204)

    @router.patch("/cases/{case_id}/facts", response_model=FactsResult, operation_id="E4")
    async def facts(request: Request, case_id: str, body: FactsUpdate) -> Any:
        return service.update_facts(actor(request), case_id, payload(body))

    @router.post("/cases/{case_id}/messages", response_model=MessageResult, operation_id="E5")
    async def messages(
        request: Request,
        case_id: str,
        body: MessageRequest,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> Any:
        return await service.message(actor(request), case_id, payload(body), idempotency_key)

    @router.post(
        "/cases/{case_id}/uploads", response_model=UploadResult, status_code=201, operation_id="E6"
    )
    async def uploads(
        request: Request,
        case_id: str,
        body: UploadRequest,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> Any:
        return service.request_upload(actor(request), case_id, payload(body), idempotency_key)

    @router.post(
        "/cases/{case_id}/evidence/{evidence_id}/complete",
        response_model=AsyncAccepted,
        status_code=202,
        operation_id="E7",
    )
    async def complete(
        request: Request,
        case_id: str,
        evidence_id: str,
        body: Empty,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> Any:
        return service.finalize_upload(actor(request), case_id, evidence_id, idempotency_key)

    @router.get(
        "/cases/{case_id}/evidence/{evidence_id}", response_model=EvidenceView, operation_id="E8"
    )
    async def evidence(request: Request, case_id: str, evidence_id: str) -> Any:
        return service.get_evidence(actor(request), case_id, evidence_id)

    @router.post(
        "/cases/{case_id}/evidence/{evidence_id}/confirm",
        response_model=ConfirmedEntities,
        operation_id="E9",
    )
    async def confirm(
        request: Request,
        case_id: str,
        evidence_id: str,
        body: Confirmation,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> Any:
        return service.confirm_evidence(
            actor(request), case_id, evidence_id, payload(body), idempotency_key
        )

    @router.post("/cases/{case_id}/process", operation_id="E10")
    async def process(request: Request, case_id: str, body: ProcessRequest) -> Any:
        verified = actor(request)
        if service.planning is None:
            service.get_case(verified, case_id)
            raise IntakeError(501, "not_implemented", "Planning is not enabled in this runtime.")
        return JSONResponse(
            service.planning.enqueue(verified, case_id, payload(body)), status_code=202
        )

    @router.get("/cases/{case_id}/plan", response_model=Plan, operation_id="E12")
    async def plan(request: Request, case_id: str) -> Any:
        verified = actor(request)
        if service.planning is None:
            raise IntakeError(501, "not_implemented")
        return service.planning.get_plan(verified, case_id)

    @router.post("/cases/{case_id}/plan/rerun", status_code=202, operation_id="E13")
    async def rerun(request: Request, case_id: str, body: RerunRequest) -> Any:
        verified = actor(request)
        if service.planning is None:
            raise IntakeError(501, "not_implemented")
        return service.planning.enqueue(verified, case_id, payload(body), rerun=True)

    @router.get("/jobs/{job_id}", response_model=Job, operation_id="E11")
    async def jobs(request: Request, job_id: str) -> Any:
        return service.get_job(actor(request), job_id)

    if isinstance(service.storage, LocalFileBlobStore):
        local = service.storage

        @router.put("/storage/upload/{token}", status_code=204, include_in_schema=False)
        async def upload_object(request: Request, token: str) -> Response:
            try:
                capability = local.capability(token, actor(request).uid, "upload")
                _, case_id, evidence_id = capability["path"].split("/")
                evidence = service._evidence(
                    service.repository, actor(request), case_id, evidence_id
                )
                if evidence["status"] != "awaiting_upload":
                    raise IntakeError(409, "invalid_state_transition")
                if request.headers.get("content-type") != capability["mime"]:
                    raise IntakeError(415, "unsupported_media_type")
                received = bytearray()
                async for chunk in request.stream():
                    received.extend(chunk)
                    if len(received) > capability["size"]:
                        raise IntakeError(413, "payload_too_large")
                if len(received) != capability["size"]:
                    raise IntakeError(422, "validation_failed")
                # Recheck after the request stream: deletion or completion may
                # have raced a slow upload. Cleanup if the audit commit fails.
                fresh = service._evidence(service.repository, actor(request), case_id, evidence_id)
                if fresh["status"] != "awaiting_upload":
                    raise IntakeError(409, "invalid_state_transition")
                local.write(capability["path"], bytes(received), capability["mime"])
                try:

                    def record_upload(tx: Any) -> None:
                        current = service._evidence(tx, actor(request), case_id, evidence_id)
                        if current["status"] != "awaiting_upload":
                            raise IntakeError(409, "invalid_state_transition")
                        service._event(
                            tx,
                            case_id,
                            actor(request),
                            "evidence.bytes_received",
                            {"evidenceId": evidence_id},
                        )

                    service.repository.atomic(record_upload)
                except Exception:
                    local.delete(capability["path"])
                    raise
                return Response(status_code=204)
            except (ValueError, KeyError) as exc:
                if isinstance(exc, IntakeError):
                    raise
                raise IntakeError(403, "forbidden") from exc

        @router.get("/storage/preview/{token}", include_in_schema=False)
        async def preview(token: str) -> Response:
            # Short-lived signature provides read capability, never an upload path.
            try:
                import base64
                import json

                if len(token) > 2048:
                    raise IntakeError(403, "forbidden")
                encoded = token.split(".", 1)[0]
                untrusted = json.loads(
                    base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                )
                capability = local.capability(token, untrusted["uid"], "preview")
                _, case_id, evidence_id = capability["path"].split("/")
                evidence = service._evidence(
                    service.repository, Actor(capability["uid"], "victim"), case_id, evidence_id
                )
                if (
                    evidence.get("storagePath") != capability["path"]
                    or evidence["status"] != "ready"
                ):
                    raise IntakeError(403, "forbidden")
                disposition = "inline" if capability["mime"].startswith("image/") else "attachment"
                return Response(
                    local.read(capability["path"]),
                    media_type=capability["mime"],
                    headers={
                        "Content-Disposition": disposition,
                        "Cache-Control": "no-store",
                        "X-Content-Type-Options": "nosniff",
                    },
                )
            except (ValueError, TypeError, KeyError, FileNotFoundError) as exc:
                if isinstance(exc, IntakeError):
                    raise
                raise IntakeError(403, "forbidden") from exc

    return router


def intake_error_response(request: Request, error: IntakeError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        media_type="application/problem+json",
        headers={"Retry-After": str(error.retry_after or 60)} if error.status == 429 else None,
        content={
            "type": f"https://relay.example/errors/{error.code}",
            "title": error.code.replace("_", " "),
            "status": error.status,
            "code": error.code,
            "detail": error.detail,
            "requestId": getattr(request.state, "request_id", "unknown"),
            "fieldErrors": [],
            "retryable": error.status in {429, 502, 503, 504},
        },
    )
