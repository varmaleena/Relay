from unittest.mock import patch

from fastapi import Request
from fastapi.testclient import TestClient

from packages.common.auth import AuthenticationError, FirebaseIdentityVerifier
from packages.common.settings import Settings
from packages.safety import Actor
from services.api.main import create_app


class TestIdentity:
    __test__ = False

    async def verify(self, id_token: str, app_check_token: str) -> Actor:
        if id_token != "synthetic-token":
            raise AuthenticationError("unauthenticated")
        if app_check_token != "synthetic-appcheck":
            raise AuthenticationError("app_check_failed")
        return Actor("test-victim", "victim")


def test_health_and_readiness_do_not_claim_cloud_readiness():
    with TestClient(create_app(Settings(), TestIdentity())) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/api/v1/healthz").status_code == 200
        readiness = client.get("/readyz")
        assert readiness.status_code == 503
        assert readiness.json()["deps"]["genai"] == "not_verified"
        assert client.get("/api/v1/config/public").json()["supportedLanguages"] == ["en", "hi"]
        assert client.get("/api/v1/version").json()["gitSha"] == "development"


def test_authentication_appcheck_problem_envelope_and_no_fake_bypass():
    with TestClient(create_app(Settings(), TestIdentity())) as client:
        anonymous = client.get("/api/v1/cases/other")
        assert anonymous.status_code == 401
        assert anonymous.json()["code"] == "unauthenticated"
        assert anonymous.headers["content-type"].startswith("application/problem+json")
        assert anonymous.headers["cache-control"] == "no-store"
        missing_appcheck = client.get(
            "/api/v1/cases/other", headers={"Authorization": "Bearer synthetic-token"}
        )
        assert missing_appcheck.status_code == 401
        assert missing_appcheck.json()["code"] == "app_check_failed"
        future = client.get(
            "/api/v1/cases/other",
            headers={
                "Authorization": "Bearer synthetic-token",
                "X-Firebase-AppCheck": "synthetic-appcheck",
            },
        )
        assert future.status_code == 404
        assert future.json()["code"] == "not_found"
    with TestClient(create_app(Settings())) as production_verifier_client:
        response = production_verifier_client.get(
            "/api/v1/cases/other",
            headers={
                "Authorization": "Bearer synthetic-token",
                "X-Firebase-AppCheck": "synthetic-appcheck",
            },
        )
        assert response.status_code == 401


def test_request_ids_cors_language_and_validation_redact_inputs():
    app = create_app(Settings(), TestIdentity())

    @app.get("/test-validation")
    async def validation_probe(request: Request, count: int):
        return {"count": count}

    headers = {
        "Authorization": "Bearer synthetic-token",
        "X-Firebase-AppCheck": "synthetic-appcheck",
        "X-Request-Id": "test_request",
        "Accept-Language": "hi",
    }
    with TestClient(app) as client:
        invalid = client.get("/test-validation?count=secret123456", headers=headers)
        assert invalid.status_code == 422
        assert "secret123456" not in invalid.text
        request_id = invalid.json()["requestId"]
        assert request_id.startswith("req_") and len(request_id) == 36
        assert request_id != "test_request"
        assert invalid.headers["X-Request-Id"] == request_id
        anonymous_hi = client.get("/test-validation", headers={"Accept-Language": "hi"})
        assert anonymous_hi.json()["detail"] == "आगे बढ़ने के लिए साइन इन करें।"
        trusted_cors = client.options(
            "/healthz",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
        )
        assert trusted_cors.headers["access-control-allow-origin"] == "http://localhost:5173"
        untrusted = client.options(
            "/healthz",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" not in untrusted.headers


def test_firebase_admin_verifies_revocation_and_appcheck():
    verifier = FirebaseIdentityVerifier("work-511514")
    verifier._app = object()
    with (
        patch(
            "firebase_admin.auth.verify_id_token", return_value={"uid": "test", "role": "victim"}
        ) as id_check,
        patch("firebase_admin.app_check.verify_token", return_value={}) as app_check,
    ):
        actor = verifier._verify("id-token", "app-token")
        assert actor.uid == "test"
        assert id_check.call_args.kwargs["check_revoked"] is True
        assert app_check.call_args.kwargs["app"] is verifier._app
    with patch(
        "firebase_admin.auth.verify_id_token", side_effect=ValueError("do not disclose token")
    ):
        try:
            verifier._verify("id-token", "app-token")
        except AuthenticationError as error:
            assert error.code == "unauthenticated"
    with (
        patch(
            "firebase_admin.auth.verify_id_token", return_value={"uid": "test", "role": "victim"}
        ),
        patch("firebase_admin.app_check.verify_token", side_effect=ValueError("bad token")),
    ):
        try:
            verifier._verify("id-token", "app-token")
        except AuthenticationError as error:
            assert error.code == "app_check_failed"
