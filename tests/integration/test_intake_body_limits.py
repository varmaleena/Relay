"""Bounded streaming request ingestion and unknown-field privacy, real ASGI stack."""

from fastapi import Request
from fastapi.testclient import TestClient

from packages.common.settings import Settings
from packages.safety import Actor
from packages.schemas import Model
from services.api.main import create_app


class TestVerifier:
    __test__ = False

    async def verify(self, id_token, app_check_token):
        return Actor("synthetic-body-test", "victim")


class KnownBody(Model):
    name: str


def test_json_body_bound_covers_declared_and_chunked_framing_and_preserves_small_body():
    app = create_app(Settings(), TestVerifier())

    @app.post("/body-probe")
    async def probe(body: KnownBody):
        return {"name": body.name}

    headers = {"Authorization": "Bearer synthetic-test", "X-Firebase-AppCheck": "synthetic-test"}
    with TestClient(app) as client:
        oversized = client.post("/body-probe", json={"name": "x" * 70_000}, headers=headers)
        assert oversized.status_code == 413
        assert oversized.json()["code"] == "payload_too_large"
        assert oversized.headers["X-Request-Id"] == oversized.json()["requestId"]

        def chunks():
            yield b'{"name":"'
            for _ in range(9):
                yield b"x" * 8192
            yield b'"}'

        chunked = client.post(
            "/body-probe",
            content=chunks(),
            headers={**headers, "Transfer-Encoding": "chunked", "Content-Type": "application/json"},
        )
        assert chunked.status_code == 413
        normal = client.post("/body-probe", json={"name": "Synthetic example"}, headers=headers)
        assert normal.status_code == 200 and normal.json()["name"] == "Synthetic example"


def test_unknown_field_names_redacted_but_known_schema_location_preserved():
    app = create_app(Settings(), TestVerifier())

    @app.post("/privacy-probe")
    async def probe(body: KnownBody):
        return {"name": body.name}

    headers = {"Authorization": "Bearer synthetic-test", "X-Firebase-AppCheck": "synthetic-test"}
    with TestClient(app) as client:
        unknown = client.post(
            "/privacy-probe", json={"name": "safe", "OTP123456": "secret-value"}, headers=headers
        )
        assert unknown.status_code == 422
        assert "OTP123456" not in unknown.text and "secret-value" not in unknown.text
        assert unknown.json()["fieldErrors"][0]["field"] == "body"
        known = client.post("/privacy-probe", json={"name": 123}, headers=headers)
        assert known.status_code == 422
        assert known.json()["fieldErrors"][0]["field"] == "body.name"


def test_upload_stream_keeps_its_independent_larger_limit():
    app = create_app(Settings(), TestVerifier())

    @app.put("/api/v1/storage/upload/test-capability")
    async def upload(request: Request):
        return {"bytes": len(await request.body())}

    with TestClient(app) as client:
        response = client.put(
            "/api/v1/storage/upload/test-capability",
            content=b"x" * 70_000,
            headers={
                "Authorization": "Bearer synthetic-test",
                "X-Firebase-AppCheck": "synthetic-test",
            },
        )
        assert response.status_code == 200 and response.json()["bytes"] == 70_000
