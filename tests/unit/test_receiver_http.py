"""Actual receiver ASGI routes with a test-only injected identity boundary."""

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from packages.intake.service import IntakeError
from packages.safety import Actor
from services.api.receiver.router import create_receiver_router
from tests.unit.test_receiver_service import setup  # noqa: F401


def test_receiver_http_isolation_projection_decision_and_validation(setup):  # noqa: F811
    app = FastAPI()

    @app.middleware("http")
    async def test_identity(request: Request, call_next):
        identities = {
            "receiver": setup.actor,
            "other": Actor("other", "receiver", "mock-cyber"),
            "victim": Actor("victim", "victim"),
        }
        request.state.actor = identities.get(request.headers.get("test-identity"))
        return await call_next(request)

    @app.exception_handler(IntakeError)
    async def safe_error(request, error):
        return JSONResponse({"code": error.code}, status_code=error.status)

    app.include_router(create_receiver_router(setup.service))
    with TestClient(app) as client:
        base = "/api/v1/console/cases"
        assert client.get(base).status_code == 401
        assert client.get(base, headers={"test-identity": "victim"}).status_code == 403
        assert client.get(base, headers={"test-identity": "other"}).json()["items"] == []
        headers = {"test-identity": "receiver", "Idempotency-Key": str(uuid4())}
        queue = client.get(base, headers=headers)
        assert queue.status_code == 200
        assert queue.json()["items"][0]["packetId"] == "packet_a"
        detail = client.get(base + "/case_a?packetId=packet_a", headers=headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()["briefStatus"] == "unavailable"
        assert "ownerUid" not in detail.text and "unapprovedFullCase" not in detail.text
        assert client.get(base + "/case_a", headers={"test-identity": "other"}).status_code == 404
        decision = base + "/case_a/packets/packet_a/decision"
        intent = {"action": "acknowledge", "packetVersion": 1}
        assert (
            client.post(decision, headers={"test-identity": "receiver"}, json=intent).status_code
            == 422
        )
        assert (
            client.post(
                decision,
                headers={"test-identity": "receiver", "Idempotency-Key": "not-a-uuid"},
                json=intent,
            ).status_code
            == 422
        )
        assert (
            client.post(
                decision,
                headers=headers,
                json={
                    "action": "acknowledge",
                    "packetVersion": 2,
                },
            ).status_code
            == 409
        )
        assert (
            client.post(
                decision,
                headers=headers,
                json={
                    "action": "reject",
                    "packetVersion": 1,
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                decision,
                headers=headers,
                json={
                    "action": "acknowledge",
                    "packetVersion": 1,
                    "unknown": "blocked",
                },
            ).status_code
            == 422
        )
        headers["Idempotency-Key"] = str(uuid4())
        approved = client.post(
            decision,
            headers=headers,
            json={
                "action": "acknowledge",
                "packetVersion": 1,
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "ACKNOWLEDGED"
        replay = client.post(decision, headers=headers, json=intent)
        assert replay.status_code == 200 and replay.json() == approved.json()
        conflict = client.post(
            decision,
            headers=headers,
            json={
                "action": "escalate",
                "packetVersion": 1,
                "reason": "Synthetic review needed.",
            },
        )
        assert conflict.status_code == 409
        assert len(setup.bridge) == 1
        assert (
            client.get(base + "/case_a", headers=headers).json()["packet"]["status"]
            == "ACKNOWLEDGED"
        )
