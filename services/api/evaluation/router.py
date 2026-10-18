"""E37–40: immutable evaluator evidence; public report access is opt-in."""
# mypy: disable-error-code="valid-type"

import asyncio
from typing import Any

from fastapi import APIRouter, Query, Request

from services.api.contracts import EvalCreated, EvalRequest, Failure, RunReport, RunSummary, page


def create_evaluation_router(service):
    router = APIRouter(prefix="/api/v1/eval")

    def actor(request):
        return getattr(request.state, "actor", None)

    @router.get("/runs", response_model=page("RunPage", RunSummary), operation_id="E37")
    async def runs(
        request: Request, limit: int = Query(default=20, ge=1, le=100), cursor: str | None = None
    ):
        return await asyncio.to_thread(service.runs, actor(request), limit=limit, cursor=cursor)

    @router.get("/runs/{run_id}", response_model=RunReport, operation_id="E38")
    async def report(request: Request, run_id: str):
        return await asyncio.to_thread(service.report, actor(request), run_id)

    @router.get(
        "/runs/{run_id}/failures", response_model=page("FailurePage", Failure), operation_id="E39"
    )
    async def failures(
        request: Request,
        run_id: str,
        system: str | None = None,
        metric: str | None = None,
        slice: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        cursor: str | None = None,
    ):
        return await asyncio.to_thread(
            service.failures,
            actor(request),
            run_id,
            system=system,
            metric=metric,
            slice=slice,
            limit=limit,
            cursor=cursor,
        )

    @router.post("/runs", response_model=EvalCreated, status_code=202, operation_id="E40")
    async def create(request: Request, data: EvalRequest):
        value: Any = data
        return service.create(actor(request), value.model_dump(mode="json", by_alias=True))

    return router
