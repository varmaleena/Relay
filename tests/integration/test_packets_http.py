"""Real ASGI packet routes with injected test identity, ADK and MCP domain code."""

import asyncio
import base64
import hashlib
import hmac
import io
import json
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from packages.common.auth import AuthenticationError
from packages.common.settings import Settings
from packages.safety import Actor
from services.api.main import create_app
from tests.unit.test_packet_service import approval, make_packet_context


class SyntheticIdentity:
    def __init__(self, owner_uid):
        self.owner_uid = owner_uid

    async def verify(self, id_token, app_check_token):
        if app_check_token != "synthetic-appcheck":
            raise AuthenticationError("app_check_failed")
        if id_token == "synthetic-owner-token":
            return Actor(self.owner_uid, "victim")
        if id_token == "synthetic-other-token":
            return Actor("synthetic-unrelated-owner", "victim")
        raise AuthenticationError("unauthenticated")


def headers(*, other=False):
    return {
        "Authorization": "Bearer synthetic-other-token"
        if other
        else "Bearer synthetic-owner-token",
        "X-Firebase-AppCheck": "synthetic-appcheck",
        "Idempotency-Key": str(uuid4()),
    }


@pytest.fixture
def http(tmp_path):
    context = make_packet_context(tmp_path)
    config = Settings(intake_enabled=True, planning_enabled=True, packets_enabled=True)
    app = create_app(config, SyntheticIdentity(context.actor.uid), intake_service=context.intake)
    with TestClient(app) as client:
        yield context, client, f"/api/v1/cases/{context.case_id}"


def generate_http(context, client, base):
    plan = context.planning.get_plan(context.actor, context.case_id)
    auth = headers()
    queued = client.post(base + "/packets/generate", json={"planId": plan["planId"]}, headers=auth)
    assert queued.status_code == 202, queued.text
    replay = client.post(base + "/packets/generate", json={"planId": plan["planId"]}, headers=auth)
    assert replay.json() == queued.json()
    asyncio.run(context.packets.process(queued.json()["jobId"]))
    listed = client.get(base + "/packets", headers=headers())
    assert listed.status_code == 200 and len(listed.json()["items"]) == 3
    packet_id = listed.json()["items"][0]["packetId"]
    packet = client.get(base + "/packets/" + packet_id, headers=headers())
    assert packet.status_code == 200, packet.text
    return packet.json()


def test_http_packet_identity_ownership_and_explicit_approval_gates(http):
    c, client, base = http
    assert client.get(base + "/packets").status_code == 401
    assert (
        client.get(
            base + "/packets", headers={"Authorization": "Bearer synthetic-owner-token"}
        ).status_code
        == 401
    )
    assert client.get(base + "/packets", headers=headers(other=True)).status_code == 403
    packet = generate_http(c, client, base)
    url = base + "/packets/" + packet["packetId"]
    assert client.get(url, headers=headers(other=True)).status_code == 403
    assert client.post(url + "/approve", json={}, headers=headers()).status_code == 422
    assert (
        client.post(
            url + "/approve", json=approval(packet) | {"confirm": False}, headers=headers()
        ).status_code
        == 422
    )
    assert (
        client.post(
            url + "/approve",
            json=approval(packet) | {"confirmedRecipientId": "other"},
            headers=headers(),
        ).status_code
        == 403
    )
    assert (
        client.post(
            url + "/approve", json=approval(packet) | {"packetVersion": 9}, headers=headers()
        ).status_code
        == 409
    )
    assert (
        client.post(
            url + "/approve", json=approval(packet), headers=headers(other=True)
        ).status_code
        == 403
    )
    assert c.adapter.calls == 0


def test_http_generate_edit_verify_send_tracker_events_and_audit_export(http):
    c, client, base = http
    packet = generate_http(c, client, base)
    url = base + "/packets/" + packet["packetId"]
    changed_fact = client.patch(
        url,
        json={"ifVersion": 1, "fields": [{"key": "payment.amount", "value": "INR 999999"}]},
        headers=headers(),
    )
    assert changed_fact.status_code == 422
    assert client.get(url, headers=headers()).json()["version"] == 1
    edited = client.patch(
        url, json={"ifVersion": 1, "message": "Synthetic correction."}, headers=headers()
    )
    assert edited.status_code == 200 and edited.json()["version"] == 2
    assert (
        client.post(url + "/approve", json=approval(packet), headers=headers()).status_code == 409
    )
    asyncio.run(c.packets.process(edited.json()["jobId"]))
    current = client.get(url, headers=headers()).json()
    sent = client.post(url + "/approve", json=approval(current), headers=headers())
    assert sent.status_code == 200, sent.text
    assert sent.json()["delivery"]["simulated"] and sent.json()["delivery"]["ticketRef"].startswith(
        "SIM-"
    )
    assert (
        client.post(url + "/approve", json=approval(current), headers=headers()).json()
        == sent.json()
    )
    assert c.adapter.calls == 1
    notifications = client.get(base + "/notifications", headers=headers())
    assert notifications.status_code == 200 and notifications.json()["items"]
    notification_id = notifications.json()["items"][0]["notificationId"]
    read = client.post(base + f"/notifications/{notification_id}/read", json={}, headers=headers())
    assert read.status_code == 200 and read.json()["readAt"]
    assert (
        client.post(
            base + "/notifications/nonexistent/read", json={}, headers=headers()
        ).status_code
        == 404
    )
    events = client.get(base + "/events?limit=2", headers=headers())
    assert events.status_code == 200 and len(events.json()["items"]) == 2
    assert events.json()["nextCursor"]
    more = client.get(
        base + "/events", params={"cursor": events.json()["nextCursor"]}, headers=headers()
    )
    assert more.status_code == 200
    assert {e["eventId"] for e in events.json()["items"]}.isdisjoint(
        e["eventId"] for e in more.json()["items"]
    )
    assert client.get(base + "/events?cursor=unrelated", headers=headers()).status_code == 400
    exported = client.get(base + "/export", headers=headers())
    assert exported.status_code == 200, exported.text
    assert len(exported.json()["packets"]) == 3 and exported.json()["case"]["caseId"] == c.case_id
    assert client.post(url + "/answer", json={}, headers=headers()).status_code == 422
    assert (
        client.post(
            url + "/answer",
            json={
                "requestId": "missing-request",
                "ifVersion": current["version"],
                "answers": [{"itemKey": "payment.reference", "value": "TEST0000000001"}],
            },
            headers=headers(),
        ).status_code
        == 409
    )


def test_http_stale_sources_block_generation_and_approval(http):
    c, client, base = http
    packet = generate_http(c, client, base)
    c.intake.update_facts(c.actor, c.case_id, {"facts": {"victimBank": "Synthetic changed bank"}})
    url = base + "/packets/" + packet["packetId"]
    assert client.get(url, headers=headers()).json()["stale"]
    assert (
        client.post(url + "/approve", json=approval(packet), headers=headers()).status_code == 409
    )
    denied = client.post(
        base + "/packets/generate", json={"planId": packet["planId"]}, headers=headers()
    )
    assert denied.status_code == 409 and c.adapter.calls == 0


def test_http_pdf_is_real_signed_scoped_version_bound_and_blocked_after_delete(http):
    c, client, base = http
    packet = generate_http(c, client, base)
    url = base + "/packets/" + packet["packetId"]
    assert client.get(url + "/pdf").status_code == 401
    assert client.get(url + "/pdf", headers=headers(other=True)).status_code == 403
    result = client.get(url + "/pdf", headers=headers())
    assert result.status_code == 200, result.text
    capability = urlsplit(result.json()["downloadUrl"]).path
    download = client.get(capability)  # Capability itself grants short-lived download access.
    assert download.status_code == 200 and download.content.startswith(b"%PDF-")
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["cache-control"] == "no-store"
    assert len(PdfReader(io.BytesIO(download.content)).pages) >= 1
    tampered = capability[:-1] + ("0" if capability[-1] != "0" else "1")
    assert client.get(tampered).status_code == 403
    # Correctly signed but expired capabilities must also fail.
    token = capability.rsplit("/", 1)[1]
    encoded = token.split(".", 1)[0]
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    payload["exp"] = 1
    expired = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(c.intake.storage.secret, expired.encode(), hashlib.sha256).hexdigest()
    assert client.get("/api/v1/storage/packet/" + expired + "." + signature).status_code == 403
    edit = client.patch(url, json={"ifVersion": 1, "message": "Synthetic v2"}, headers=headers())
    assert edit.status_code == 200
    assert client.get(capability).status_code == 403
    asyncio.run(c.packets.process(edit.json()["jobId"]))
    fresh = client.get(url + "/pdf", headers=headers())
    assert fresh.status_code == 200
    new_capability = urlsplit(fresh.json()["downloadUrl"]).path
    assert client.get(new_capability).status_code == 200
    assert client.delete(base, headers=headers()).status_code == 204
    assert client.get(new_capability).status_code in {403, 404}


def test_authenticated_route_crash_is_not_reported_as_identity_failure(caplog):
    app = create_app(Settings(), SyntheticIdentity("synthetic-owner"))

    @app.get("/synthetic-route-error")
    async def unexpected_failure():
        raise RuntimeError("synthetic-private-payload-should-not-log")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/synthetic-route-error", headers=headers())
    assert response.status_code == 500
    assert "identity_unavailable" not in response.text
    assert "synthetic-private-payload-should-not-log" not in response.text
    assert "identity.verification_failed" not in caplog.text
    assert "synthetic-private-payload-should-not-log" not in caplog.text
