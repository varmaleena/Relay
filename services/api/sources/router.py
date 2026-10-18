"""E29–31; original snapshots are never served as active HTML/PDF content."""
# mypy: disable-error-code="valid-type"

import asyncio
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response

from packages.intake.service import IntakeError
from packages.safety import Actor
from packages.sources.fetch import MAX_BYTES
from services.api.contracts import AsyncAccepted, Empty, Passage, SourceCreate, SourceCreated, page

PassagePage = page("PassagePage", Passage)


def create_source_router(service: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/sources")

    def body(data: Any) -> Any:
        return data.model_dump(by_alias=True)

    def reviewer(request):
        actor = getattr(request.state, "actor", None)
        if not isinstance(actor, Actor):
            raise IntakeError(401, "unauthenticated")
        service.reviewer(actor)
        return actor

    @router.post("", response_model=SourceCreated, status_code=201, operation_id="E29")
    async def create(
        request: Request, data: SourceCreate, key: Annotated[UUID, Header(alias="Idempotency-Key")]
    ):
        return service.create(reviewer(request), body(data), str(key))

    @router.put("/{source_id}/upload", status_code=204)
    async def upload(request: Request, source_id: str):
        actor = reviewer(request)
        service._source(service.repository, actor, source_id)
        mime = request.headers.get("content-type", "").split(";", 1)[0].lower()
        content = bytearray()
        try:
            async with asyncio.timeout(30):
                async for chunk in request.stream():
                    content.extend(chunk)
                    if len(content) > MAX_BYTES:
                        raise IntakeError(413, "validation_failed")
        except TimeoutError:
            raise IntakeError(408, "timeout") from None
        await service.upload(actor, source_id, bytes(content), mime)
        return Response(status_code=204)

    @router.post(
        "/{source_id}/ingest", response_model=AsyncAccepted, status_code=202, operation_id="E30"
    )
    async def ingest(
        request: Request,
        source_id: str,
        data: Empty,
        key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ):
        return service.ingest(reviewer(request), source_id, str(key))

    @router.get("/{source_id}/passages", response_model=PassagePage, operation_id="E31")
    async def passages(
        request: Request,
        source_id: str,
        q: str | None = Query(None, max_length=200),
        limit: int = Query(25, ge=1, le=100),
        cursor: str | None = Query(None, max_length=128),
    ):
        return service.passages(reviewer(request), source_id, q=q, limit=limit, cursor=cursor)

    return router
