"""No-inference readiness probes; dependency clients are isolated test doubles."""

import asyncio
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.api_core.exceptions import PermissionDenied

from packages.common.settings import Settings
from services.api.main import create_app
from services.api.readiness import HEALTH_RESOURCE, ServingReadiness


class Database:
    project = "synthetic-project"

    def __init__(self):
        self.calls = 0
        self.failure = None
        self.delay = 0

    def document(self, path):
        assert path == HEALTH_RESOURCE
        return self

    def get(self, *, timeout, retry):
        assert timeout > 0 and retry is None
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.failure:
            raise self.failure
        # A missing health document still verifies the read RPC. Data is ignored.
        return SimpleNamespace(exists=False, private_data="synthetic-private-data")


class Bucket:
    def __init__(self, name):
        self.name, self.calls = name, 0
        self.present = True
        self.failure = None

    def blob(self, name):
        assert name == HEALTH_RESOURCE
        return self

    def exists(self, *, timeout, retry):
        assert timeout > 0 and retry is None
        self.calls += 1
        if self.failure:
            raise self.failure
        return self.present

    def reload(self, **kwargs):
        raise AssertionError("bucket metadata permission must not be required")


class Publisher:
    topic = "projects/synthetic-project/topics/relay-jobs"
    client = object()

    def __call__(self, *args, **kwargs):
        raise AssertionError("readiness must not publish a job")


class NoInference:
    def __getattr__(self, name):
        raise AssertionError("readiness must not invoke or query a model")


def setup_cloud():
    config = Settings.model_construct(
        environment="dev",
        intake_enabled=True,
        auth_mode="firebase",
        intake_storage_mode="gcs",
        genai_mode="live",
        gcp_project_id="synthetic-project",
        model_reasoning="gemini-3-synthetic",
        genai_location="global",
        bucket_evidence="synthetic-evidence",
        bucket_exports="synthetic-exports",
        pubsub_topic_jobs=Publisher.topic,
    )
    service = SimpleNamespace(
        repository=SimpleNamespace(client=Database(), job_publisher=Publisher()),
        storage=SimpleNamespace(bucket=Bucket(config.bucket_evidence)),
        export_storage=SimpleNamespace(bucket=Bucket(config.bucket_exports)),
        intake_agent=NoInference(),
        evidence_agent=NoInference(),
        planning=None,
        packets=None,
    )
    return config, service


def test_local_default_readiness_remains_503_without_cloud_or_model_calls():
    with TestClient(create_app(Settings())) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "deps": {"firestore": "not_verified", "pubsub": "not_verified", "genai": "not_verified"},
    }


def test_cloud_http_readiness_probes_only_serving_dependencies_and_labels_configured():
    config, service = setup_cloud()
    with TestClient(create_app(config, intake_service=service)) as client:
        response = client.get("/api/v1/readyz")
        assert response.status_code == 200, response.text
        assert client.get("/readyz").status_code == 200
    body = response.json()
    assert body["scope"] == "serving_dependencies"
    assert body["deps"] == {
        "firestore": "verified",
        "evidence_storage": "verified",
        "export_storage": "verified",
        "pubsub": "configured",
        "genai": "configured",
    }
    assert "model_inference" in body["notProbed"] and "queue_delivery" in body["notProbed"]
    assert "synthetic-project" not in response.text and "private_data" not in response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert (
        service.repository.client.calls
        == service.storage.bucket.calls
        == service.export_storage.bucket.calls
        == 1
    )


@pytest.mark.parametrize("dependency", ["database", "evidence", "exports"])
def test_permission_failure_is_503_and_does_not_expose_exception_or_resource_names(dependency):
    config, service = setup_cloud()
    target = {
        "database": service.repository.client,
        "evidence": service.storage.bucket,
        "exports": service.export_storage.bucket,
    }[dependency]
    target.failure = PermissionDenied("synthetic-private-project/resource denied")
    with TestClient(create_app(config, intake_service=service)) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert "unavailable" in response.text
    assert "synthetic-private" not in response.text and "denied" not in response.text


def test_missing_export_sentinel_cannot_claim_storage_readiness():
    config, service = setup_cloud()
    service.export_storage.bucket.present = False
    with TestClient(create_app(config, intake_service=service)) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["deps"]["export_storage"] == "sentinel_missing"


def test_bounded_timeout_does_not_wait_for_slow_dependency_or_claim_verification():
    config, service = setup_cloud()
    service.repository.client.delay = 0.15
    probe = ServingReadiness(
        config, service, rpc_timeout=0.01, overall_timeout=0.02, cache_seconds=0
    )

    async def check():
        started = time.monotonic()
        body = await probe.check()
        return body, time.monotonic() - started

    body, elapsed = asyncio.run(check())
    assert elapsed < 0.1
    assert body["status"] == "not_ready" and body["deps"]["firestore"] == "timeout"


@pytest.mark.parametrize("missing", ["publisher", "model", "exports"])
def test_configured_is_not_assumed_when_runtime_dependency_is_missing(missing):
    config, service = setup_cloud()
    if missing == "publisher":
        service.repository.job_publisher = None
    elif missing == "model":
        service.intake_agent = None
    else:
        service.export_storage = None
    body = asyncio.run(ServingReadiness(config, service).check())
    assert body["status"] == "not_ready" and "not_configured" in body["deps"].values()


def test_emulator_environment_prevents_cloud_verification(monkeypatch):
    config, service = setup_cloud()
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8095")
    body = asyncio.run(ServingReadiness(config, service).check())
    assert body["status"] == "not_ready" and body["deps"]["firestore"] == "not_verified"
    assert service.repository.client.calls == 0
