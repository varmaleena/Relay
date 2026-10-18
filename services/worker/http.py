"""Private Cloud Run push worker. IAM authenticates callers before this app.

No browser-token bypass, public invoker, or polling loop is implemented here.
Deployment must grant run.invoker only to the configured push/scheduler identity.
"""

import asyncio
import base64
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from packages.common.logging import configure_logging
from packages.common.settings import Settings
from services.worker.main import JobPager

JOB_PATTERN = r"^job_[a-f0-9]{32}$"
JOB_TYPES = {
    "process_evidence",
    "process_case",
    "rebuild_packets",
    "verify_packet",
    "send_packet",
    "handoff_receiver",
    "pack_ingest",
    "pack_build",
}
MAX_BODY = 16_384
MAX_DISPATCH_SECONDS = 480
MAX_SWEEP_SECONDS = 540


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PushAttributes(StrictModel):
    type: Annotated[str, Field(min_length=1, max_length=80)]
    schemaVersion: Literal["1"]
    caseId: Annotated[str | None, Field(min_length=1, max_length=128)] = None
    resourceId: Annotated[str | None, Field(min_length=1, max_length=128)] = None
    traceId: Annotated[str, Field(min_length=1, max_length=128)]
    idempotencyKey: Annotated[str, Field(pattern=JOB_PATTERN)]

    @model_validator(mode="after")
    def resource_required(self):
        if self.caseId is None and self.resourceId is None:
            raise ValueError("case or resource reference required")
        return self


class PushMessage(StrictModel):
    data: Annotated[str, Field(min_length=1, max_length=4096)]
    attributes: PushAttributes
    messageId: Annotated[str | None, Field(max_length=128)] = None
    message_id: Annotated[str | None, Field(max_length=128)] = None
    publishTime: Annotated[str | None, Field(max_length=80)] = None
    publish_time: Annotated[str | None, Field(max_length=80)] = None
    orderingKey: Annotated[str | None, Field(max_length=128)] = None

    @model_validator(mode="after")
    def matching_documented_metadata_aliases(self):
        # Pub/Sub's current wrapped delivery examples include both spellings.
        # These are metadata only; all other extra fields remain forbidden.
        for camel, snake in (("messageId", "message_id"), ("publishTime", "publish_time")):
            if camel in self.model_fields_set and snake in self.model_fields_set:
                if getattr(self, camel) != getattr(self, snake):
                    raise ValueError("conflicting push metadata aliases")
        return self


class PushEnvelope(StrictModel):
    message: PushMessage
    subscription: Annotated[str, Field(min_length=1, max_length=300)]
    deliveryAttempt: Annotated[int | None, Field(ge=1, le=1000)] = None


class JobReference(StrictModel):
    jobId: Annotated[str, Field(pattern=JOB_PATTERN)]


def validate_cloud_worker(config: Settings) -> None:
    if (
        config.environment not in {"dev", "staging", "prod"}
        or config.service != "worker"
        or config.auth_mode != "firebase"
        or config.genai_mode != "live"
        or config.intake_storage_mode != "gcs"
        or not config.intake_enabled
        or not config.gcp_project_id
        or config.gcp_project_id.startswith("demo-")
    ):
        raise ValueError("HTTP worker requires explicit cloud worker configuration")
    if any(
        os.environ.get(name)
        for name in (
            "FIRESTORE_EMULATOR_HOST",
            "FIREBASE_AUTH_EMULATOR_HOST",
            "PUBSUB_EMULATOR_HOST",
            "STORAGE_EMULATOR_HOST",
            "FIREBASE_STORAGE_EMULATOR_HOST",
        )
    ):
        raise ValueError("HTTP worker forbids emulator environment")


def retry_response() -> JSONResponse:
    return JSONResponse({"code": "work_pending"}, status_code=503, headers={"Retry-After": "10"})


def _future(value: Any, now: datetime) -> bool:
    if value is None:
        return False
    if type(value) is not str:
        raise ValueError("invalid job time")
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("invalid job time")
    return timestamp > now


async def dispatch_job(service: Any, job_id: str) -> bool:
    """True acknowledges terminal work, deletion, or an active leased worker.

    Active leases can be ACKed because the durable sweep reclaims expired work.
    Queued/deferred or unclaimed work must be redelivered; no catch-all success.
    """
    job = await asyncio.to_thread(service.repository.get, f"jobs/{job_id}")
    if job is None or job.get("state") in {"succeeded", "failed"}:
        return True
    if job.get("state") not in {"queued", "running"}:
        return False
    now = service.clock()
    if job["state"] == "running" and _future(job.get("leaseUntil"), now):
        return True
    if _future(job.get("retryAfter"), now) or _future(job.get("leaseUntil"), now):
        return False
    kind = job.get("type")
    if kind == "process_evidence":
        await service.process_evidence(job_id)
    elif kind == "process_case" and service.planning is not None:
        await service.planning.process_case(job_id)
    elif kind in {"rebuild_packets", "verify_packet"} and service.packets is not None:
        await service.packets.process(job_id)
    elif kind == "send_packet" and service.packets is not None:
        await service.packets.process_delivery(job_id)
    elif kind == "handoff_receiver" and service.receiver_handoff is not None:
        await service.receiver_handoff.process(job_id)
    elif kind == "pack_ingest" and service.sources is not None:
        await service.sources.process(job_id)
    elif kind == "pack_build" and service.packstudio is not None:
        await service.packstudio.process(job_id)
    else:
        return False
    current = await asyncio.to_thread(service.repository.get, f"jobs/{job_id}")
    if current is None or current.get("state") in {"succeeded", "failed"}:
        return True
    return bool(
        current.get("state") == "running" and _future(current.get("leaseUntil"), service.clock())
    )


class DurableSweep:
    """One bounded page and at most one heavy job; checkpoint after processing.

    Cursors survive Cloud Run cold starts. Concurrent requests may repeat a page;
    domain leases/idempotency handle duplicates. An interrupted dispatch never
    checkpoints beyond that job. No process-local pagination assumption is used.
    """

    def __init__(self, service: Any):
        self.service = service

    async def run(self) -> None:
        started = time.monotonic()
        repository = self.service.repository
        client = repository.client
        cursor = await asyncio.to_thread(repository.get, "workerSweepState/jobs")
        pager = JobPager()
        last_id = cursor.get("lastId") if cursor else None
        if last_id is not None:
            if not re.fullmatch(JOB_PATTERN, last_id):
                raise ValueError("invalid durable job cursor")
            pager.cursor = {"__name__": client.collection("jobs").document(last_id)}
        page = await asyncio.to_thread(pager.fetch, client)
        checkpoint = page[-1].id if len(page) == 25 else None
        for index, snapshot in enumerate(page):
            job = snapshot.to_dict()
            if not job or job.get("type") not in JOB_TYPES:
                continue
            now = self.service.clock()
            if _future(job.get("leaseUntil"), now) or _future(job.get("retryAfter"), now):
                continue
            await dispatch_job(self.service, snapshot.id)
            # Resume at the next job, rather than skipping the unprocessed tail.
            checkpoint = snapshot.id if index < len(page) - 1 or len(page) == 25 else None
            break
        await asyncio.to_thread(
            repository.atomic, lambda tx: tx.set("workerSweepState/jobs", {"lastId": checkpoint})
        )
        if self.service.packets is not None:
            await self._deadlines()
        # Leave room for bounded cleanup after processing; long model work must
        # not cause a newly-started deletion to consume the request deadline.
        if time.monotonic() - started < MAX_SWEEP_SECONDS - 30:
            await self._retention()

    async def _retention(self) -> None:
        from packages.intake.retention import cleanup_expired_cases

        await asyncio.to_thread(cleanup_expired_cases, self.service, limit=1)

    async def _deadlines(self) -> None:
        from packages.packets.deadlines import check_case_deadlines

        repository = self.service.repository
        client = repository.client
        cursor = await asyncio.to_thread(repository.get, "workerSweepState/cases")
        query = client.collection("cases").order_by("__name__").limit(25)
        last_id = cursor.get("lastId") if cursor else None
        if last_id is not None:
            if not re.fullmatch(r"case_[a-f0-9]{32}", last_id):
                raise ValueError("invalid durable case cursor")
            query = query.start_after({"__name__": client.collection("cases").document(last_id)})
        page = await asyncio.to_thread(lambda: list(query.stream()))
        for snapshot in page:
            await asyncio.to_thread(check_case_deadlines, self.service.packets, snapshot.id)
        checkpoint = page[-1].id if len(page) == 25 else None
        await asyncio.to_thread(
            repository.atomic, lambda tx: tx.set("workerSweepState/cases", {"lastId": checkpoint})
        )


def create_worker_app(settings: Settings | None = None, intake_service: Any = None) -> FastAPI:
    config = settings or Settings()
    validate_cloud_worker(config)
    configure_logging()
    runtime_model = None
    if intake_service is None:
        from services.api.runtime import create_intake_runtime

        intake_service, runtime_model = create_intake_runtime(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            if runtime_model is not None:
                await runtime_model.close()
                intake_service.repository.client.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    @app.get("/api/v1/healthz")
    async def health():
        return {"status": "ok"}

    @app.post("/pubsub/push")
    async def push(request: Request):
        chunks = bytearray()
        async for chunk in request.stream():
            if len(chunks) + len(chunk) > MAX_BODY:
                return JSONResponse({"code": "payload_too_large"}, status_code=413)
            chunks.extend(chunk)
        try:
            envelope = PushEnvelope.model_validate_json(bytes(chunks))
            decoded = base64.b64decode(envelope.message.data, validate=True)
            if len(decoded) > 2048:
                raise ValueError("payload too large")
            reference = JobReference.model_validate_json(decoded)
            if reference.jobId != envelope.message.attributes.idempotencyKey:
                raise ValueError("mismatched job reference")
        except (ValueError, ValidationError):
            return JSONResponse({"code": "invalid_push"}, status_code=400)
        try:
            done = await asyncio.wait_for(
                dispatch_job(intake_service, reference.jobId), timeout=MAX_DISPATCH_SECONDS
            )
        except Exception:
            return retry_response()
        return Response(status_code=204) if done else retry_response()

    @app.post("/internal/sweep")
    async def sweep(request: Request):
        # Scheduler sends an empty body; arbitrary case/job payloads are rejected.
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > 2:
                return JSONResponse({"code": "invalid_sweep"}, status_code=400)
            payload.extend(chunk)
        if bytes(payload).strip() not in {b"", b"{}"}:
            return JSONResponse({"code": "invalid_sweep"}, status_code=400)
        try:
            await asyncio.wait_for(DurableSweep(intake_service).run(), timeout=MAX_SWEEP_SECONDS)
        except Exception:
            return retry_response()
        return Response(status_code=204)

    return app
