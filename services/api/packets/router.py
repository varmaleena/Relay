"""Owner-authenticated packet actions; approval and delivery are domain operations."""
# mypy: disable-error-code="valid-type"

from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import Response

from packages.intake.service import IntakeError
from packages.safety import Actor
from services.api.contracts import (
    AnswerRequest,
    AnswerResult,
    ApproveRequest,
    AsyncAccepted,
    AuditExport,
    Empty,
    Notification,
    Packet,
    PacketEdit,
    PacketEditResult,
    PacketGenerate,
    PdfDownload,
    SendResult,
)


def create_packet_router(service: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def actor(request: Request) -> Actor:
        value = getattr(request.state, "actor", None)
        if not isinstance(value, Actor):
            raise IntakeError(401, "unauthenticated")
        if not getattr(request.state, "intake_rate_counted", False):
            request.state.intake_rate = service.intake.rate_limit(value)
            request.state.intake_rate_counted = True
        return value

    def body(value: Any) -> Any:
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True)

    @router.post(
        "/cases/{case_id}/packets/generate",
        response_model=AsyncAccepted,
        status_code=202,
        operation_id="E45_generate",
    )
    async def generate(
        request: Request,
        case_id: str,
        data: PacketGenerate,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> Any:
        return service.generate(actor(request), case_id, body(data), idempotency_key)

    @router.get("/cases/{case_id}/packets", operation_id="E14")
    async def packets(request: Request, case_id: str) -> Any:
        return service.list(actor(request), case_id)

    @router.get("/cases/{case_id}/packets/{packet_id}", response_model=Packet, operation_id="E15")
    async def packet(request: Request, case_id: str, packet_id: str) -> Any:
        return service.public(service.get(actor(request), case_id, packet_id))

    @router.patch(
        "/cases/{case_id}/packets/{packet_id}", response_model=PacketEditResult, operation_id="E16"
    )
    async def edit(request: Request, case_id: str, packet_id: str, data: PacketEdit) -> Any:
        return service.edit(actor(request), case_id, packet_id, body(data))

    @router.post(
        "/cases/{case_id}/packets/{packet_id}/approve",
        response_model=SendResult,
        operation_id="E17",
    )
    async def approve(request: Request, case_id: str, packet_id: str, data: ApproveRequest) -> Any:
        return await service.approve(actor(request), case_id, packet_id, body(data))

    @router.get(
        "/cases/{case_id}/packets/{packet_id}/pdf", response_model=PdfDownload, operation_id="E18"
    )
    async def pdf(request: Request, case_id: str, packet_id: str) -> Any:
        return service.pdf(actor(request), case_id, packet_id)

    @router.get("/storage/packet/{token}", include_in_schema=False)
    async def pdf_bytes(token: str) -> Response:
        return Response(
            service.pdf_bytes(token),
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="relay-message.pdf"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.post(
        "/cases/{case_id}/packets/{packet_id}/answer",
        response_model=AnswerResult,
        operation_id="E19",
    )
    async def answer(
        request: Request,
        case_id: str,
        packet_id: str,
        data: AnswerRequest,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> Any:
        return service.answer(actor(request), case_id, packet_id, body(data), idempotency_key)

    @router.get("/cases/{case_id}/events", operation_id="E20")
    async def events(
        request: Request, case_id: str, limit: int = 50, cursor: str | None = None
    ) -> Any:
        return service.events(actor(request), case_id, limit, cursor)

    @router.get("/cases/{case_id}/export", response_model=AuditExport, operation_id="E21")
    async def export(request: Request, case_id: str) -> Any:
        return service.export(actor(request), case_id)

    @router.get("/cases/{case_id}/notifications", operation_id="E46_notifications")
    async def notifications(request: Request, case_id: str) -> Any:
        return service.notifications(actor(request), case_id)

    @router.post(
        "/cases/{case_id}/notifications/{notification_id}/read",
        response_model=Notification,
        operation_id="E47_read",
    )
    async def read(request: Request, case_id: str, notification_id: str, data: Empty) -> Any:
        return service.notifications(actor(request), case_id, notification_id)

    return router
