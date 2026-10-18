"""Explicit reviewer-org Pack Studio mutations; no service/model auth shortcut."""

# mypy: disable-error-code="valid-type"
import asyncio
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Request

from packages.intake.service import IntakeError
from packages.safety import Actor
from services.api.contracts import (
    BuildCreated,
    BuildRequest,
    PackBuild,
    PublishedPack,
    PublishRequest,
    RetireRequest,
    RetireResult,
    RuleReviewRequest,
    RuleReviewResult,
)


def create_packstudio_router(service: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def actor(request):
        value = getattr(request.state, "actor", None)
        if not isinstance(value, Actor):
            raise IntakeError(401, "unauthenticated")
        service.reviewer(value)
        return value

    def body(data):
        return data.model_dump(mode="json", by_alias=True, exclude_unset=True)

    @router.post("/pack-builds", response_model=BuildCreated, status_code=202, operation_id="E32")
    async def create(
        request: Request, data: BuildRequest, key: Annotated[UUID, Header(alias="Idempotency-Key")]
    ):
        return await asyncio.to_thread(service.create, actor(request), body(data), str(key))

    @router.get("/pack-builds/{build_id}", response_model=PackBuild, operation_id="E33")
    async def get(request: Request, build_id: str):
        return service.get(actor(request), build_id)

    @router.patch(
        "/pack-builds/{build_id}/rules/{rule_id}",
        response_model=RuleReviewResult,
        operation_id="E34",
    )
    async def review(
        request: Request,
        build_id: str,
        rule_id: str,
        data: RuleReviewRequest,
        key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ):
        return await asyncio.to_thread(
            service.review, actor(request), build_id, rule_id, body(data), str(key)
        )

    @router.post(
        "/pack-builds/{build_id}/publish", response_model=PublishedPack, operation_id="E35"
    )
    async def publish(
        request: Request,
        build_id: str,
        data: PublishRequest,
        key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ):
        return await asyncio.to_thread(
            service.publish, actor(request), build_id, body(data), str(key)
        )

    @router.post(
        "/packs/{pack_id}/versions/{version}/retire",
        response_model=RetireResult,
        operation_id="E36",
    )
    async def retire(
        request: Request,
        pack_id: str,
        version: str,
        data: RetireRequest,
        key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ):
        return service.retire(actor(request), pack_id, version, body(data), str(key))

    return router
