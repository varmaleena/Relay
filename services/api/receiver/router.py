"""No receiver endpoint returns a full victim case document."""
# mypy: disable-error-code="valid-type"

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from packages.intake.service import IntakeError
from packages.safety import Actor
from services.api.contracts import (
    DecisionRequest,
    DecisionResult,
    ReceiverCaseSummary,
    ReceiverCaseView,
    page,
)

ReceiverCasePage = page("ReceiverCasePage", ReceiverCaseSummary)


def create_receiver_router(service: Any, rate_limiter: Any = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/console")

    def body(data: Any) -> Any:
        return data.model_dump(mode="json", by_alias=True, exclude_unset=True)

    def actor(request: Request) -> Actor:
        value = getattr(request.state, "actor", None)
        if not isinstance(value, Actor):
            raise IntakeError(401, "unauthenticated")
        service._org(value)
        if rate_limiter and not getattr(request.state, "intake_rate_counted", False):
            request.state.intake_rate = rate_limiter(value)
            request.state.intake_rate_counted = True
        return value

    @router.get("/cases", response_model=ReceiverCasePage, operation_id="E22")
    async def queue(
        request: Request,
        status: str | None = None,
        urgency: str | None = None,
        typology: str | None = Query(default=None, max_length=80),
        limit: int = Query(default=25, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=256),
    ):
        return service.queue(
            actor(request),
            status=status,
            urgency=urgency,
            typology=typology,
            limit=limit,
            cursor=cursor,
        )

    @router.get("/cases/{case_id}", response_model=ReceiverCaseView, operation_id="E23")
    async def dossier(
        request: Request, case_id: str, packetId: str | None = Query(default=None, max_length=128)
    ):
        return await service.get_case(actor(request), case_id, packetId)

    @router.post(
        "/cases/{case_id}/packets/{packet_id}/decision",
        response_model=DecisionResult,
        operation_id="E24",
    )
    async def decide(
        request: Request,
        case_id: str,
        packet_id: str,
        data: DecisionRequest,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ):
        return await service.decide(
            actor(request),
            case_id,
            packet_id,
            body(data),
            idempotency_key=str(idempotency_key),
        )

    return router
