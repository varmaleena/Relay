from unittest.mock import patch

import pytest
from pydantic import ValidationError

from packages.common.emulator_auth import EmulatorIdentityVerifier
from packages.common.settings import Settings


@pytest.mark.parametrize(
    "overrides",
    [
        {"environment": "dev", "gcp_project_id": "demo-relay-local"},
        {"gcp_project_id": "work-511514"},
        {"gcp_project_id": "demo-relay-local", "auth_emulator_host": "evil.example:9099"},
    ],
)
def test_auth_emulator_cannot_be_enabled_for_cloud_or_remote(overrides):
    with pytest.raises(ValidationError, match="auth emulator"):
        Settings(auth_mode="emulator", **overrides)


def test_production_auth_rejects_accidental_emulator_environment(monkeypatch):
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    with pytest.raises(ValidationError, match="production auth"):
        Settings()


def test_local_emulator_requires_explicit_environment(monkeypatch):
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    with pytest.raises(ValueError, match="environment"):
        EmulatorIdentityVerifier("demo-relay-local", "127.0.0.1:9099")


def test_actual_admin_verifier_checks_emulator_token_revocation(monkeypatch):
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    verifier = EmulatorIdentityVerifier("demo-relay-local", "127.0.0.1:9099")
    verifier._app = object()
    with patch(
        "firebase_admin.auth.verify_id_token",
        return_value={"uid": "synthetic", "firebase": {"sign_in_provider": "anonymous"}},
    ) as token_verify:
        assert verifier._verify("emulator-issued-token").uid == "synthetic"
        assert token_verify.call_args.kwargs["check_revoked"] is True


def test_local_live_intake_separates_demo_identity_from_cloud_model_project():
    settings = Settings(
        auth_mode="emulator",
        gcp_project_id="demo-relay-local",
        genai_project_id="work-511514",
        intake_enabled=True,
        genai_mode="live",
        genai_location="global",
        model_reasoning="gemini-3.8-flash",
    )
    assert settings.genai_project_id != settings.gcp_project_id
