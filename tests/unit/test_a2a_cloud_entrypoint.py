"""Cloud entrypoint builds only scoped Firestore + brief dependencies, no inference."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from packages.common.settings import Settings
from services.a2a_receiver import http


def settings(**changes):
    return Settings(
        service="a2a",
        environment="dev",
        genai_mode="live",
        auth_mode="firebase",
        gcp_project_id="work-511514",
        genai_location="global",
        model_reasoning="gemini-3-flash-preview",
        allowed_origins="https://relay.example.invalid",
        a2a_receiver_url="https://relay-dev-a2a-example.run.app/",
        **changes,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"service": "api"},
        {"environment": "local"},
        {"genai_mode": "replay"},
        {"auth_mode": "emulator"},
        {"a2a_receiver_url": "https://untrusted.example.invalid"},
        {"a2a_receiver_url": "https://x.run.app/path"},
        {"a2a_receiver_url": "https://x.run.app:8443/"},
    ],
)
def test_explicit_cloud_runtime_required(monkeypatch, change):
    monkeypatch.setenv("A2A_PRIVATE_IAM_REQUIRED", "true")
    config = settings().model_copy(update=change)
    with pytest.raises(ValueError):
        http.validate_cloud_settings(config)


@pytest.mark.parametrize(
    "variable", ["FIRESTORE_EMULATOR_HOST", "FIREBASE_AUTH_EMULATOR_HOST", "STORAGE_EMULATOR_HOST"]
)
def test_cloud_never_uses_emulators(monkeypatch, variable):
    monkeypatch.setenv("A2A_PRIVATE_IAM_REQUIRED", "true")
    monkeypatch.setenv(variable, "127.0.0.1:1234")
    with pytest.raises(ValueError):
        http.validate_cloud_settings(settings())


def test_private_iam_configuration_is_explicit(monkeypatch):
    monkeypatch.delenv("A2A_PRIVATE_IAM_REQUIRED", raising=False)
    with pytest.raises(ValueError):
        http.validate_cloud_settings(settings())


def test_minimal_assembly_closes_clients_and_health_never_runs_model(monkeypatch):
    monkeypatch.setenv("A2A_PRIVATE_IAM_REQUIRED", "true")
    for variable in (
        "FIRESTORE_EMULATOR_HOST",
        "FIREBASE_AUTH_EMULATOR_HOST",
        "STORAGE_EMULATOR_HOST",
    ):
        monkeypatch.delenv(variable, raising=False)
    config = settings()
    monkeypatch.setattr(http, "Settings", lambda: config)
    state = SimpleNamespace(database_closed=False, model_closed=False)

    class Database:
        def __init__(self, **kwargs):
            assert kwargs == {"project": "work-511514", "database": "(default)"}

        def close(self):
            state.database_closed = True

        def document(self, *args, **kwargs):
            pytest.fail("Health or startup must not read case data")

    class Model:
        def __init__(self, config):
            pass

        async def close(self):
            state.model_closed = True

        async def generate(self, *args, **kwargs):
            pytest.fail("Health or startup must not run inference")

    monkeypatch.setattr(http.firestore, "Client", Database)
    monkeypatch.setattr(http, "GoogleGenAIClient", Model)
    app = http.create_receiver_app()
    with TestClient(app) as client:
        assert client.get("/api/v1/healthz").status_code == 200
        assert client.get("/.well-known/agent-card.json").status_code == 200
        assert client.post("/api/v1/console/cases").status_code == 404
    assert state.model_closed and state.database_closed
