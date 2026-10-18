"""Admin rehearsal controls require a configured private synthetic namespace."""

# mypy: disable-error-code="valid-type"
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Request

from packages.intake.service import IntakeError
from packages.safety import Actor
from services.api.contracts import AdapterBehavior, Empty, Ok, ResetResult, ScenarioCreated


def create_demo_router(service: Any, rate_limiter: Any = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/demo")

    def actor(request: Request) -> Actor:
        value = getattr(request.state, "actor", None)
        if not isinstance(value, Actor):
            raise IntakeError(401, "unauthenticated")
        service._admin(value, service.namespace)
        if rate_limiter and not getattr(request.state, "intake_rate_counted", False):
            request.state.intake_rate = rate_limiter(value)
            request.state.intake_rate_counted = True
        return value

    @router.post("/reset", operation_id="E41", response_model=ResetResult)
    async def reset(
        request: Request,
        data: Empty,
        namespace: Annotated[str, Header(alias="X-Demo-Namespace")],
        confirmation: Annotated[str, Header(alias="X-Demo-Reset-Confirm")],
        key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ):
        return service.reset(actor(request), namespace, str(key), confirmation)

    @router.post(
        "/scenarios/{name}/load",
        operation_id="E42",
        response_model=ScenarioCreated,
        status_code=201,
    )
    async def load(
        request: Request,
        name: str,
        data: Empty,
        namespace: Annotated[str, Header(alias="X-Demo-Namespace")],
        key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ):
        return service.load(actor(request), namespace, name, str(key))

    @router.put("/adapters/behavior", operation_id="E43", response_model=Ok)
    async def behavior(
        request: Request,
        data: AdapterBehavior,
        namespace: Annotated[str, Header(alias="X-Demo-Namespace")],
        key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ):
        typed: Any = data
        return service.behavior(
            actor(request), namespace, typed.model_dump(mode="json", by_alias=True), str(key)
        )

    return router
