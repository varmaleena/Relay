"""Source fetch SSRF, parser trust boundaries and immutable reviewer ingestion."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from packages.intake.repository import MemoryRepository
from packages.intake.service import IntakeError
from packages.safety import Actor
from packages.sources.fetch import (
    MAX_BYTES,
    FetchedSource,
    OfficialFetcher,
    SourceRejected,
    public_ip,
)
from packages.sources.parse_worker import extract
from packages.sources.service import SourceService
from packages.sources.storage import LocalSourceStore, parse_source


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "169.254.169.254",
        "10.0.0.1",
        "192.168.1.1",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "224.0.0.1",
    ],
)
def test_nonpublic_and_metadata_addresses_rejected(address):
    with pytest.raises(SourceRejected):
        public_ip(address)


@pytest.mark.parametrize(
    "url",
    [
        "http://official.example/",
        "https://official.example.evil/",
        "https://u:p@official.example/",
        "https://official.example:444/",
        "https://official.example/#fragment",
        "https://official.example/\\evil",
        "https://169.254.169.254/",
        "https://official.example/?access_token=synthetic",
    ],
)
def test_source_url_checks_precede_any_connection(url):
    fetcher = OfficialFetcher({"official.example"}, resolver=lambda host: ["8.8.8.8"])
    with pytest.raises(SourceRejected):
        fetcher.validate(url)


def test_all_dns_answers_checked_not_only_first():
    fetcher = OfficialFetcher({"official.example"}, resolver=lambda host: ["8.8.8.8", "127.0.0.1"])
    with pytest.raises(SourceRejected):
        fetcher.validate("https://official.example/")


class Response:
    def __init__(self, content=b"Official source text", *, status=200, headers=None):
        self.status, self.content = status, content
        self.headers = headers or {"Content-Type": "text/plain"}

    def getheader(self, name):
        return self.headers.get(name)

    def read(self, size):
        value, self.content = self.content[:size], self.content[size:]
        return value


def fetcher_for(responses, *, resolver=None):
    calls = []

    class Connection:
        sock = None

        def __init__(self, host, address, timeout):
            calls.append((host, address, timeout))

        def request(self, method, target, headers):
            assert method == "GET" and headers["Accept-Encoding"] == "identity"

        def getresponse(self):
            return responses.pop(0)

        def close(self):
            pass

    return OfficialFetcher(
        {"official.example"}, resolver=resolver or (lambda host: ["8.8.8.8"]), connection=Connection
    ), calls


def test_redirect_rechecks_dns_and_rebinding_cannot_connect_private():
    answers = iter([["8.8.8.8"], ["127.0.0.1"]])
    fetcher, calls = fetcher_for(
        [Response(status=302, headers={"Location": "/next"})], resolver=lambda host: next(answers)
    )
    with pytest.raises(SourceRejected):
        fetcher.fetch("https://official.example/start")
    assert len(calls) == 1 and calls[0][1] == "8.8.8.8"


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "application/javascript"},
        {"Content-Type": "text/html", "Content-Encoding": "gzip"},
        {"Content-Type": "text/plain", "Content-Length": str(MAX_BYTES + 1)},
    ],
)
def test_mime_compressed_and_declared_oversize_blocked(headers):
    fetcher, _ = fetcher_for([Response(headers=headers)])
    with pytest.raises(SourceRejected):
        fetcher.fetch("https://official.example/")


def test_actual_html_parser_strips_active_content_and_preserves_visible_offsets():
    pages = extract(
        b'<html><p>Official guidance.</p><script>alert("secret")</script>'
        b"<style>bad</style><iframe>hidden</iframe><p>Contact bank.</p></html>",
        "text/html",
    )
    text = pages[0][1]
    assert "Official guidance." in text and "Contact bank." in text
    assert "secret" not in text and "hidden" not in text and "bad" not in text
    assert "<" not in text
    passages = SourceService._passages("src_" + "a" * 32, pages)
    for item in passages:
        assert text[item["offsetStart"] : item["offsetEnd"]] == item["text"]


def test_non_linux_default_parser_explicitly_fails_closed(monkeypatch):
    import packages.sources.storage as storage

    monkeypatch.setattr(storage.os, "name", "nt")
    with pytest.raises(SourceRejected, match="hard limits unavailable"):
        parse_source(b"Official source.", "text/plain")


@pytest.fixture
def source_context(tmp_path):
    clock = [datetime.now(UTC)]
    store = LocalSourceStore(tmp_path / "sources")
    fetcher = SimpleNamespace(
        validate=lambda url: ("official.example", "8.8.8.8", "/"),
        fetch=lambda url: FetchedSource(b"Official guidance. " * 250, "text/plain", url),
    )
    service = SourceService(
        MemoryRepository(),
        store,
        fetcher,
        api_base_url="http://127.0.0.1:8000",
        parser=extract,
        clock=lambda: clock[0],
    )
    actor = Actor("synthetic-reviewer", "reviewer", "review-org")
    return SimpleNamespace(service=service, actor=actor, clock=clock, store=store)


def source_create(c, kind="upload"):
    return c.service.create(
        c.actor,
        {
            "kind": kind,
            "title": "Synthetic official guidance",
            "publisher": "Synthetic official publisher",
            "language": "en",
            **({"url": "https://official.example/policy"} if kind == "url" else {}),
        },
        str(uuid4()),
    )["sourceId"]


def test_upload_immutable_passages_job_replay_and_org_scope(source_context):
    c = source_context
    source_id = source_create(c)
    content = b"Official guidance. " * 250
    asyncio.run(c.service.upload(c.actor, source_id, content, "text/plain"))
    with pytest.raises(IntakeError) as error:
        asyncio.run(c.service.upload(c.actor, source_id, b"Changed source.", "text/plain"))
    assert error.value.status == 409
    key = str(uuid4())
    job = c.service.ingest(c.actor, source_id, key)
    assert c.service.ingest(c.actor, source_id, key) == job
    asyncio.run(c.service.process(job["jobId"]))
    asyncio.run(c.service.process(job["jobId"]))
    source = c.service.repository.get("sources/" + source_id)
    assert source["state"] == "ready" and source["reviewStatus"] == "unverified"
    assert c.store.read(source["storagePath"]) == content
    first = c.service.passages(c.actor, source_id, limit=1)
    assert first["nextCursor"]
    second = c.service.passages(c.actor, source_id, limit=1, cursor=first["nextCursor"])
    assert first["items"][0]["passageId"] != second["items"][0]["passageId"]
    assert c.service.passages(c.actor, source_id, q="absent")["items"] == []
    with pytest.raises(IntakeError) as error:
        c.service.passages(Actor("other", "reviewer", "foreign-org"), source_id)
    assert error.value.status == 404
    with pytest.raises(IntakeError):
        c.service.passages(Actor("victim", "victim"), source_id)


def test_url_job_restart_and_secret_upload_rejection(source_context):
    c = source_context
    source_id = source_create(c, "url")
    queued = c.service.ingest(c.actor, source_id)
    restarted = SourceService(
        c.service.repository,
        c.store,
        c.service.fetcher,
        api_base_url="http://127.0.0.1:8000",
        parser=extract,
    )
    asyncio.run(restarted.process(queued["jobId"]))
    assert restarted.passages(c.actor, source_id)["items"]
    source_id = source_create(c)
    with pytest.raises(IntakeError):
        asyncio.run(c.service.upload(c.actor, source_id, b"My OTP is 123456", "text/plain"))
    assert c.service.repository.get("sources/" + source_id)["state"] == "created"


def test_live_third_attempt_lease_respected_before_cap(source_context):
    c = source_context
    source_id = source_create(c, "url")
    queued = c.service.ingest(c.actor, source_id)
    path = "jobs/" + queued["jobId"]
    job = c.service.repository.get(path)
    job.update(
        state="running", attempts=3, leaseUntil=(c.clock[0] + timedelta(seconds=30)).isoformat()
    )
    c.service.repository.set(path, job)
    asyncio.run(c.service.process(queued["jobId"]))
    assert c.service.repository.get(path)["state"] == "running"
    c.clock[0] += timedelta(seconds=31)
    asyncio.run(c.service.process(queued["jobId"]))
    assert c.service.repository.get(path)["state"] == "failed"


def test_pinned_tls_connects_numeric_address_and_checks_peer_and_hostname(monkeypatch):
    import packages.sources.fetch as module
    from packages.sources.fetch import PinnedHTTPS

    calls: list[tuple[Any, ...]] = []

    class Raw:
        def settimeout(self, timeout):
            assert timeout == 2

        def connect(self, address):
            calls.append(("connect", address))

        def getpeername(self):
            return ("8.8.8.8", 443)

        def close(self):
            calls.append(("close",))

    class TLS:
        def wrap_socket(self, raw, *, server_hostname):
            calls.append(("tls", server_hostname))
            return raw

    monkeypatch.setattr(module.socket, "socket", lambda *args: Raw())
    monkeypatch.setattr(module.ssl, "create_default_context", lambda: TLS())
    connection = PinnedHTTPS("official.example", "8.8.8.8", 2)
    connection.connect()
    assert calls == [("connect", ("8.8.8.8", 443)), ("tls", "official.example")]
    monkeypatch.setattr(Raw, "getpeername", lambda self: ("127.0.0.1", 443))
    with pytest.raises(SourceRejected):
        PinnedHTTPS("official.example", "8.8.8.8", 2).connect()


def test_actual_source_router_auth_upload_ingest_passages(source_context):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from services.api.sources.router import create_source_router

    c = source_context
    app = FastAPI()

    @app.middleware("http")
    async def test_identity(request: Request, call_next):
        request.state.actor = c.actor if request.headers.get("test-reviewer") == "yes" else None
        return await call_next(request)

    @app.exception_handler(IntakeError)
    async def safe_error(request, error):
        return JSONResponse({"code": error.code}, status_code=error.status)

    app.include_router(create_source_router(c.service))
    payload = {
        "kind": "upload",
        "title": "Synthetic source",
        "publisher": "Official fixture",
        "language": "en",
    }
    headers = {"test-reviewer": "yes", "Idempotency-Key": str(uuid4())}
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/sources", json=payload, headers={"Idempotency-Key": str(uuid4())}
            ).status_code
            == 401
        )
        created = client.post("/api/v1/sources", json=payload, headers=headers)
        assert created.status_code == 201, created.text
        assert (
            client.post("/api/v1/sources", json=payload, headers=headers).json() == created.json()
        )
        source_id = created.json()["sourceId"]
        base = "/api/v1/sources/" + source_id
        uploaded = client.put(
            base + "/upload",
            content=b"Official synthetic guidance.",
            headers=headers | {"Content-Type": "text/plain"},
        )
        assert uploaded.status_code == 204, uploaded.text
        queued = client.post(base + "/ingest", json={}, headers=headers)
        assert queued.status_code == 202, queued.text
        asyncio.run(c.service.process(queued.json()["jobId"]))
        passages = client.get(base + "/passages", headers=headers)
        assert passages.status_code == 200, passages.text
        assert passages.json()["items"][0]["text"] == "Official synthetic guidance."
        assert client.get(base + "/snapshot", headers=headers).status_code == 404
