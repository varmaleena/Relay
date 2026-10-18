"""Explicit human validation of possible links, scoped to receiver projections."""

# mypy: disable-error-code="valid-type"
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Request

from packages.intake.service import IntakeError
from packages.safety import Actor
from services.api.contracts import CaseLink, LinkResult, ValidateLink, page

CaseLinkList = page("CaseLinkList", CaseLink)


def create_linking_router(service: Any, rate_limiter: Any = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/console")

    def actor(request: Request) -> Actor:
        value = getattr(request.state, "actor", None)
        if not isinstance(value, Actor):
            raise IntakeError(401, "unauthenticated")
        service._org(value)
        if rate_limiter and not getattr(request.state, "intake_rate_counted", False):
            request.state.intake_rate = rate_limiter(value)
            request.state.intake_rate_counted = True
        return value

    @router.get("/cases/{case_id}/links", response_model=CaseLinkList, operation_id="E25")
    async def links(request: Request, case_id: str):
        return service.list(actor(request), case_id)

    @router.post("/links/{link_id}/validate", response_model=LinkResult, operation_id="E26")
    async def validate(
        request: Request,
        link_id: str,
        data: ValidateLink,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ):
        typed: Any = data
        return service.validate(
            actor(request), link_id, typed.decision, typed.note, str(idempotency_key)
        )

    return router
