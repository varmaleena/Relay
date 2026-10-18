"""Source routes through the actual application boundary and both worker dispatchers.

Identity is explicitly injected; these tests do not claim Firebase cryptographic,
cloud IAM, isolated Linux-parser or model execution coverage.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from packages.common.auth import AuthenticationError
from packages.common.settings import Settings
from packages.intake.service import IntakeService
from packages.safety import Actor
from services.api.main import create_app
from services.worker.http import dispatch_job
from services.worker.main import process_jobs
from tests.unit.test_sources import source_context  # noqa: F401


class SourceIdentity:
    async def verify(self, id_token, app_check_token):
        if app_check_token != "synthetic-appcheck":
            raise AuthenticationError("app_check_failed")
        identities = {
            "reviewer": Actor("synthetic-reviewer", "reviewer", "review-org"),
            "colleague": Actor("synthetic-colleague", "reviewer", "review-org"),
            "foreign": Actor("synthetic-foreign", "reviewer", "other-org"),
            "victim": Actor("synthetic-victim", "victim"),
        }
        if id_token not in identities:
            raise AuthenticationError("unauthenticated")
        return identities[id_token]


def headers(identity="reviewer"):
    return {
        "Authorization": "Bearer " + identity,
        "X-Firebase-AppCheck": "synthetic-appcheck",
        "Idempotency-Key": str(uuid4()),
    }


@pytest.fixture
def application(source_context):  # noqa: F811
    service = IntakeService(source_context.service.repository, Mock(), None, None)
    service.sources = source_context.service
    source_context.service.parser = Mock(wraps=source_context.service.parser)
    config = Settings(
        intake_enabled=True, sources_enabled=True, allowed_fetch_domains="official.example"
    )
    with TestClient(create_app(config, SourceIdentity(), service)) as client:
        yield SimpleNamespace(client=client, service=service, source=source_context.service)


def create_source(application):
    response = application.client.post(
        "/api/v1/sources",
        headers=headers(),
        json={
            "kind": "upload",
            "title": "Synthetic official guidance",
            "publisher": "Synthetic publisher",
            "language": "en",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["sourceId"]


PAYLOAD = b"Synthetic official source guidance. " * 2300


def upload_source(application, source_id):
    assert len(PAYLOAD) > 65_536
    response = application.client.put(
        f"/api/v1/sources/{source_id}/upload",
        headers=headers() | {"Content-Type": "text/plain"},
        content=PAYLOAD,
    )
    assert response.status_code == 204, response.text


def test_exact_reviewer_upload_exceeds_general_limit_and_remains_unverified(application):
    source_id = create_source(application)
    upload_source(application, source_id)
    application.source.parser.assert_called_once_with(PAYLOAD, "text/plain")
    stored = application.service.repository.get("sources/" + source_id)
    assert stored["state"] == "uploaded" and stored["reviewStatus"] == "unverified"
    assert application.source.storage.read(stored["storagePath"]) == PAYLOAD
    assert application.service.repository.get("publishedPacks/" + source_id) is None


def test_source_upload_waiver_never_bypasses_auth_appcheck_or_reviewer_org(application):
    source_id = create_source(application)
    path = f"/api/v1/sources/{source_id}/upload"
    for identity, expected in ((None, 401), ("victim", 403), ("foreign", 404)):
        response = application.client.put(
            path,
            headers=({} if identity is None else headers(identity))
            | {"Content-Type": "text/plain"},
            content=PAYLOAD,
        )
        assert response.status_code == expected
    response = application.client.put(
        path,
        headers={"Authorization": "Bearer reviewer", "Content-Type": "text/plain"},
        content=PAYLOAD,
    )
    assert response.status_code == 401 and response.json()["code"] == "app_check_failed"
    application.source.parser.assert_not_called()
    assert application.service.repository.get("sources/" + source_id)["state"] == "created"


def test_body_limit_waiver_is_exact_and_other_routes_still_reject_large_bodies(application):
    source_id = create_source(application)
    paths = [
        "/api/v1/cases",
        "/api/v1/sources",
        f"/api/v1/sources/{source_id}/ingest",
        f"/api/v1/sources/{source_id}/upload/",
        "/api/v1/sources/src_invalid/upload",
    ]
    for path in paths:
        response = application.client.put(path, headers=headers(), content=PAYLOAD)
        assert response.status_code == 413, (path, response.text)
    response = application.client.post(
        f"/api/v1/sources/{source_id}/upload", headers=headers(), content=PAYLOAD
    )
    assert response.status_code == 413
    application.source.parser.assert_not_called()


def test_source_stream_still_has_its_own_route_size_bound(application, monkeypatch):
    source_id = create_source(application)
    monkeypatch.setattr("services.api.sources.router.MAX_BYTES", 70_000)
    chunks = (b"x" * 20000 for _ in range(4))
    response = application.client.put(
        f"/api/v1/sources/{source_id}/upload",
        headers=headers() | {"Content-Type": "text/plain"},
        content=chunks,
    )
    assert response.status_code == 413
    application.source.parser.assert_not_called()


@pytest.mark.parametrize("dispatcher", ["push", "local-poll"])
def test_source_ingest_job_org_scope_and_actual_worker_process(application, dispatcher):
    source_id = create_source(application)
    upload_source(application, source_id)
    accepted = application.client.post(
        f"/api/v1/sources/{source_id}/ingest", headers=headers(), json={}
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["jobId"]
    path = "/api/v1/jobs/" + job_id
    for identity in ("reviewer", "colleague"):
        response = application.client.get(path, headers=headers(identity))
        assert response.status_code == 200 and response.json()["state"] == "queued"
        assert "orgId" not in response.json() and "uid" not in response.json()
    assert application.client.get(path, headers=headers("foreign")).status_code == 404
    assert application.client.get(path, headers=headers("victim")).status_code == 403
    assert application.client.get(path).status_code == 401
    job = application.service.repository.get("jobs/" + job_id)
    assert "caseId" not in job and job["resourceId"] == source_id
    if dispatcher == "push":
        assert asyncio.run(dispatch_job(application.service, job_id)) is True
    else:
        snapshot = SimpleNamespace(id=job_id, to_dict=lambda: job)
        assert asyncio.run(
            process_jobs(application.service, [snapshot], application.service.clock())
        )
    response = application.client.get(path, headers=headers("colleague"))
    assert response.status_code == 200 and response.json()["state"] == "succeeded"
    passages = application.client.get(
        f"/api/v1/sources/{source_id}/passages", headers=headers("colleague")
    )
    assert passages.status_code == 200 and passages.json()["items"]
    assert passages.json()["items"][0]["text"].startswith("Synthetic official")
    assert application.source.parser.call_count == 2
    attempts = application.service.repository.get("jobs/" + job_id)["attempts"]
    assert asyncio.run(dispatch_job(application.service, job_id)) is True
    assert application.service.repository.get("jobs/" + job_id)["attempts"] == attempts


def test_source_routes_are_not_mounted_without_feature_flag(application):
    config = Settings(intake_enabled=True)
    with TestClient(create_app(config, SourceIdentity(), application.service)) as client:
        response = client.post(
            "/api/v1/sources",
            headers=headers(),
            json={
                "kind": "upload",
                "title": "Synthetic",
                "publisher": "Synthetic",
                "language": "en",
            },
        )
        assert response.status_code == 404
