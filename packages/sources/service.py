"""Reviewer-org immutable sources and durable pack_ingest jobs, without publication."""

import asyncio
import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, ValidationError

from packages.common.identifiers import canonical_hash, new_id
from packages.intake.service import IntakeError, stamp
from packages.safety.guard import scrub_credentials
from packages.schemas import Model
from packages.sources.fetch import MAX_BYTES, MIMES, SourceRejected
from packages.sources.storage import parse_source


class SourceRequest(Model):
    kind: Literal["upload", "url"]
    url: str | None = Field(default=None, max_length=4096)
    title: str = Field(min_length=1, max_length=300)
    publisher: str = Field(min_length=1, max_length=200)
    language: str = Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")


class SourceService:
    def __init__(
        self, repository, storage, fetcher, *, api_base_url: str, parser=parse_source, clock=None
    ):
        self.repository, self.storage, self.fetcher = repository, storage, fetcher
        self.api_base_url, self.parser = api_base_url.rstrip("/"), parser
        self.clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def reviewer(actor):
        if (
            actor.role not in {"reviewer", "admin"}
            or not actor.uid
            or not actor.org_id
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", actor.org_id)
        ):
            raise IntakeError(403, "forbidden")
        return actor.org_id

    def _source(self, tx, actor, source_id):
        org = self.reviewer(actor)
        if not re.fullmatch(r"src_[a-f0-9]{32}", source_id):
            raise IntakeError(404, "not_found")
        source = tx.get("sources/" + source_id)
        if not source or source["orgId"] != org:
            raise IntakeError(404, "not_found")
        return source

    def create(self, actor, body, key):
        org = self.reviewer(actor)
        try:
            request = SourceRequest.model_validate(body)
            key = str(UUID(key))
            if request.kind == "url":
                if not request.url:
                    raise ValueError()
                self.fetcher.validate(request.url)
            elif request.url is not None:
                raise ValueError()
            data = request.model_dump(mode="json", by_alias=True)
            if any(
                scrub_credentials(value) != value
                for value in data.values()
                if isinstance(value, str)
            ):
                raise ValueError()
        except (ValueError, ValidationError, SourceRejected):
            raise IntakeError(422, "source_not_allowed") from None
        scope = canonical_hash({"org": org, "uid": actor.uid, "key": key})
        source_id, body_hash = "src_" + scope[:32], canonical_hash(data)

        def write(tx):
            previous = tx.get("sources/" + source_id)
            if previous:
                if previous["requestHash"] != body_hash:
                    raise IntakeError(409, "idempotency_conflict")
                return previous
            value = {
                **data,
                "sourceId": source_id,
                "orgId": org,
                "createdBy": actor.uid,
                "createdAt": stamp(self.clock()),
                "requestHash": body_hash,
                "state": "created",
                "passageIds": [],
                "jobIds": [],
                "reviewStatus": "unverified",
            }
            tx.set("sources/" + source_id, value)
            return value

        value = self.repository.atomic(write)
        return {
            "sourceId": source_id,
            "uploadUrl": f"{self.api_base_url}/api/v1/sources/{source_id}/upload"
            if value["kind"] == "upload"
            else None,
        }

    async def upload(self, actor, source_id, content: bytes, mime: str):
        source = self._source(self.repository, actor, source_id)
        if source["kind"] != "upload" or mime not in MIMES or not 0 < len(content) <= MAX_BYTES:
            raise IntakeError(422, "source_not_allowed")
        try:
            pages = await asyncio.to_thread(self.parser, content, mime)
            self._passages(source_id, pages)
        except Exception:
            raise IntakeError(422, "source_not_allowed") from None
        digest = hashlib.sha256(content).hexdigest()
        path = f"sources/{source['orgId']}/{source_id}/{digest}.snapshot"

        def reserve(tx):
            current = self._source(tx, actor, source_id)
            if current.get("sha256") and current["sha256"] != digest:
                raise IntakeError(409, "invalid_state_transition")
            if current["state"] not in {"created", "uploaded", "uploading"}:
                raise IntakeError(409, "invalid_state_transition")
            current.update(sha256=digest, storagePath=path, mime=mime, state="uploading")
            tx.set("sources/" + source_id, current)

        self.repository.atomic(reserve)
        await asyncio.to_thread(self.storage.put_once, path, content, mime)

        def finish(tx):
            current = self._source(tx, actor, source_id)
            if current.get("sha256") != digest:
                raise IntakeError(409, "version_conflict")
            if current["state"] != "uploading":
                return
            current.update(state="uploaded")
            tx.set("sources/" + source_id, current)

        self.repository.atomic(finish)

    def ingest(self, actor, source_id, key=None):
        try:
            request_key = str(UUID(key)) if key is not None else None
        except (ValueError, TypeError, AttributeError):
            raise IntakeError(422, "validation_failed") from None

        def enqueue(tx):
            source = self._source(tx, actor, source_id)
            scoped_key = (
                canonical_hash({"uid": actor.uid, "key": request_key}) if request_key else None
            )
            if scoped_key and scoped_key in source.get("ingestRequests", {}):
                return source["ingestRequests"][scoped_key]
            if source["state"] == "ready" or source["state"] == "ingesting":
                return source["jobIds"][-1]
            if source["kind"] == "upload" and source["state"] not in {"uploaded", "failed"}:
                raise IntakeError(409, "invalid_state_transition")
            if len(source["jobIds"]) >= 3:
                raise IntakeError(429, "rate_limited")
            job_id = new_id("job")
            source["jobIds"].append(job_id)
            if scoped_key:
                source.setdefault("ingestRequests", {})[scoped_key] = job_id
            source.update(state="ingesting")
            tx.set("sources/" + source_id, source)
            tx.set(
                "jobs/" + job_id,
                {
                    "jobId": job_id,
                    "type": "pack_ingest",
                    "resourceId": source_id,
                    "uid": actor.uid,
                    "orgId": source["orgId"],
                    "state": "queued",
                    "attempts": 0,
                    "createdAt": stamp(self.clock()),
                    "progress": {"step": 0, "total": 1},
                    "error": None,
                },
            )
            return job_id

        job_id = self.repository.atomic(enqueue)
        return {"jobId": job_id, "statusUrl": "/api/v1/jobs/" + job_id}

    @staticmethod
    def _passages(source_id, pages):
        passages: list[dict[str, Any]] = []
        if not isinstance(pages, list) or len(pages) > 200:
            raise SourceRejected("Parser page limit")
        total = 0
        for page, text in pages:
            if not isinstance(text, str) or (
                page is not None and (type(page) is not int or not 1 <= page <= 200)
            ):
                raise SourceRejected("Invalid parser output")
            total += len(text)
            if total > 500000 or scrub_credentials(text) != text:
                raise SourceRejected("Unsafe or oversized source text")
            for start in range(0, len(text), 2000):
                chunk = text[start : start + 2000]
                if not chunk.strip():
                    continue
                passages.append(
                    {
                        "passageId": f"{source_id}:p{len(passages) + 1:04d}",
                        "text": chunk,
                        "page": page,
                        "offsetStart": start,
                        "offsetEnd": start + len(chunk),
                    }
                )
        if not passages or len(passages) > 400:
            raise SourceRejected("Source passage limit")
        return passages

    async def process(self, job_id):
        def claim(tx):
            job = tx.get("jobs/" + job_id)
            if (
                not job
                or job.get("type") != "pack_ingest"
                or job["state"] not in {"queued", "running"}
            ):
                return None
            now = stamp(self.clock())
            if any(job.get(field) and job[field] > now for field in ("leaseUntil", "retryAfter")):
                return None
            source = tx.get("sources/" + job["resourceId"])
            if (
                not source
                or source["orgId"] != job["orgId"]
                or source["jobIds"][-1] != job_id
                or job["attempts"] >= 3
            ):
                job.update(state="failed", error=self.problem())
                tx.set("jobs/" + job_id, job)
                return None
            job.update(
                state="running",
                attempts=job["attempts"] + 1,
                claimToken=new_id("srcclaim"),
                leaseUntil=stamp(self.clock() + timedelta(seconds=90)),
            )
            tx.set("jobs/" + job_id, job)
            return job, source

        claimed = self.repository.atomic(claim)
        if not claimed:
            return
        job, source = claimed
        try:
            if source["kind"] == "url":
                fetched = await asyncio.to_thread(self.fetcher.fetch, source["url"])
                content, mime, final_url = fetched.content, fetched.mime, fetched.final_url
            else:
                content = await asyncio.to_thread(self.storage.read, source["storagePath"])
                mime, final_url = source["mime"], None
            pages = await asyncio.to_thread(self.parser, content, mime)
            passages = self._passages(source["sourceId"], pages)
            digest = hashlib.sha256(content).hexdigest()
            if source.get("sha256") and source["sha256"] != digest:
                raise SourceRejected("Source snapshot changed")
            path = f"sources/{source['orgId']}/{source['sourceId']}/{digest}.snapshot"
            await asyncio.to_thread(self.storage.put_once, path, content, mime)

            def finish(tx):
                current_job = tx.get("jobs/" + job_id)
                current = tx.get("sources/" + source["sourceId"])
                if (
                    not current_job
                    or current_job.get("claimToken") != job["claimToken"]
                    or not current
                    or current["jobIds"][-1] != job_id
                    or current["orgId"] != job["orgId"]
                ):
                    raise IntakeError(409, "version_conflict")
                for passage in passages:
                    tx.set(f"sources/{source['sourceId']}/passages/{passage['passageId']}", passage)
                current.update(
                    state="ready",
                    sha256=digest,
                    storagePath=path,
                    mime=mime,
                    finalUrl=final_url,
                    retrievedAt=stamp(self.clock()),
                    passageIds=[p["passageId"] for p in passages],
                    passageCount=len(passages),
                    extractionHash=canonical_hash(passages),
                    reviewStatus="unverified",
                )
                current_job.update(
                    state="succeeded", leaseUntil=None, progress={"step": 1, "total": 1}, error=None
                )
                tx.set("sources/" + source["sourceId"], current)
                tx.set("jobs/" + job_id, current_job)

            self.repository.atomic(finish)
        except Exception:

            def fail(tx):
                latest = tx.get("jobs/" + job_id)
                current = tx.get("sources/" + source["sourceId"])
                if latest and latest.get("claimToken") == job["claimToken"]:
                    latest.update(state="failed", leaseUntil=None, error=self.problem())
                    tx.set("jobs/" + job_id, latest)
                    if current and current["jobIds"][-1] == job_id:
                        current.update(state="failed")
                        tx.set("sources/" + source["sourceId"], current)

            self.repository.atomic(fail)

    def passages(self, actor, source_id, *, q=None, limit=25, cursor=None):
        source = self._source(self.repository, actor, source_id)
        if source["state"] != "ready":
            raise IntakeError(409, "invalid_state_transition")
        ids = source["passageIds"]
        if cursor and cursor not in ids:
            raise IntakeError(400, "bad_request")
        if q and (len(q) > 200 or scrub_credentials(q) != q):
            raise IntakeError(422, "validation_failed")
        start = ids.index(cursor) + 1 if cursor else 0
        matches = []
        for passage_id in ids[start:]:
            passage = self.repository.get(f"sources/{source_id}/passages/{passage_id}")
            if not passage:
                raise IntakeError(503, "resource_unavailable")
            if not q or q.casefold() in passage["text"].casefold():
                matches.append(passage)
                if len(matches) > min(max(limit, 1), 100):
                    break
        bounded = min(max(limit, 1), 100)
        return {
            "items": matches[:bounded],
            "nextCursor": matches[bounded - 1]["passageId"] if len(matches) > bounded else None,
        }

    @staticmethod
    def problem():
        return {
            "type": "https://relay.example/errors/source_not_allowed",
            "title": "Source ingestion failed",
            "status": 422,
            "code": "source_not_allowed",
            "detail": "Source validation or bounded parsing failed.",
            "requestId": new_id("req"),
            "fieldErrors": [],
            "retryable": False,
        }
