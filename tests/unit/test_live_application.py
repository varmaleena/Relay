"""Main API WebSocket integration, without model or network calls."""

from fastapi.testclient import TestClient
from starlette.routing import WebSocketRoute

from services.api.main import create_app
from tests.unit.test_live_gateway import Provider, context, start  # noqa: F401
from tests.unit.test_live_runtime import settings


def test_enabled_gateway_mounts_at_api_boundary_and_releases_case_lease(context):  # noqa: F811
    c = context
    provider = Provider()
    config = settings(allowed_origins="https://relay.test")
    app = create_app(config, c.verifier, c.intake, live_provider=provider)
    with TestClient(app) as client:
        assert client.get("/api/v1/config/public").json()["liveEnabled"] is True
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            ws.send_json({"type": "text", "text": "I paid by UPI."})
            assert ws.receive_json()["role"] == "user"
            assert ws.receive_json()["text"] == "How did you pay?"
            assert ws.receive_bytes() == b"\0\0" * 320
            ws.send_json({"type": "end"})
            assert ws.receive_json()["reason"] == "ended"
    assert provider.closed
    assert not any(path.startswith("liveSessions/") for path in c.repo.documents)


def test_disabled_gateway_has_no_websocket_route(context):  # noqa: F811
    c = context
    app = create_app(settings(live_enabled=False), c.verifier, c.intake)
    assert not any(isinstance(route, WebSocketRoute) for route in app.routes)
    with TestClient(app) as client:
        assert client.get("/api/v1/config/public").json()["liveEnabled"] is False


def test_case_deletion_cascades_active_live_session_and_resumption(context):  # noqa: F811
    from services.live_gateway.registry import LiveSessionRegistry

    c = context
    registry = LiveSessionRegistry(c.intake)
    record = registry.acquire(c.actor, c.case_id, "en")
    registry.resumption(record, "synthetic-provider-handle")
    assert any(path.startswith("liveSessions/") for path in c.repo.documents)
    c.intake.delete_case(c.actor, c.case_id)
    assert not any(
        path.startswith(("liveSessions/", "liveUsers/", "liveResumptions/"))
        for path in c.repo.documents
    )
