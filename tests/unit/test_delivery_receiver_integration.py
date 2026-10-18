"""Approved delivery through actual local MCP into scoped receiver views."""

import asyncio
import json

import pytest

from packages.intake.service import IntakeError
from packages.receiver.bridge import DEMO_RECIPIENT_ORGS, ReceiverDecisionBridge
from packages.receiver.service import ReceiverService
from packages.safety import Actor
from tests.unit.test_packet_service import approval, generate, make_packet_context


@pytest.fixture
def flow(tmp_path):
    c = make_packet_context(tmp_path)
    c.receiver = ReceiverService(
        c.repository,
        recipient_orgs=DEMO_RECIPIENT_ORGS,
        hold_adapter=c.adapter.actual.place_hold,
        decision_bridge=ReceiverDecisionBridge(c.intake, DEMO_RECIPIENT_ORGS),
        clock=lambda: c.clock[0],
    )
    c.intake.receiver = c.receiver
    c.staff = Actor("synthetic-officer", "receiver", "mock-bank")
    c.packet = generate(c)
    return c


def send(c):
    return asyncio.run(
        c.packets.approve(c.actor, c.case_id, c.packet["packetId"], approval(c.packet))
    )


def test_approved_send_projects_only_addressed_packet_and_deletion_removes_all(flow):
    c = flow
    assert c.receiver.queue(c.staff)["items"] == []
    assert not any(p.startswith("receiver") for p in c.repository.documents)
    sent = send(c)
    assert sent["status"] == "SENT"
    queue = c.receiver.queue(c.staff)["items"]
    assert len(queue) == 1 and queue[0]["packetId"] == c.packet["packetId"]
    path = f"receiverViews/mock-bank/cases/{c.case_id}/packets/{c.packet['packetId']}"
    projected = c.repository.get(path)
    raw = json.dumps(projected)
    assert c.actor.uid not in raw and "ownerUid" not in raw
    assert "transcript" not in raw and "signedUrl" not in raw
    assert projected["evidence"] == [] and projected["packet"]["content"]["attachments"] == []
    assert projected["minutesSincePayment"] == 20
    assert c.receiver.queue(Actor("other-officer", "receiver", "mock-cyber"))["items"] == []
    case = c.repository.get(f"cases/{c.case_id}")
    assert len(case["receiverProjectionRefs"]) == 1
    assert send(c) == sent
    assert len(c.repository.get(f"cases/{c.case_id}")["receiverProjectionRefs"]) == 1
    c.intake.delete_case(c.actor, c.case_id)
    assert not any(p.startswith(("receiver", "mockDeliveries/")) for p in c.repository.documents)
    assert not any(p.startswith(f"cases/{c.case_id}/events/") for p in c.repository.documents)


def test_no_approval_or_bad_approval_never_creates_receiver_feed(flow):
    c = flow
    with pytest.raises(IntakeError):
        asyncio.run(
            c.packets.approve(
                c.actor, c.case_id, c.packet["packetId"], approval(c.packet) | {"confirm": False}
            )
        )
    assert c.adapter.calls == 0
    assert not any(p.startswith("receiver") for p in c.repository.documents)


@pytest.mark.parametrize("expiry", [None, "invalid", 0])
def test_missing_or_invalid_internal_expiry_cannot_commit_receiver_delivery(flow, expiry):
    c = flow
    case = c.repository.get(f"cases/{c.case_id}")
    case["accessExpiresAtMs"] = expiry
    c.repository.set(f"cases/{c.case_id}", case)
    with pytest.raises(IntakeError) as error:
        send(c)
    assert error.value.code == "adapter_unavailable"
    assert not any(p.startswith("receiver") for p in c.repository.documents)
    assert c.packets.get(c.actor, c.case_id, c.packet["packetId"])["status"] != "SENT"


def test_receiver_ack_and_registered_mcp_hold_match_victim_and_audit(flow):
    c = flow
    send(c)
    delivery = next(v for p, v in c.repository.documents.items() if p.startswith("mockDeliveries/"))
    assert delivery["holds"] == {}
    for action, expected in [("acknowledge", "ACKNOWLEDGED"), ("place_hold_simulated", "ACTIONED")]:
        body = {"action": action, "packetVersion": 1}
        outcome = asyncio.run(c.receiver.decide(c.staff, c.case_id, c.packet["packetId"], body))
        assert outcome["status"] == expected
        assert c.packets.get(c.actor, c.case_id, c.packet["packetId"])["status"] == expected
        assert (
            asyncio.run(c.receiver.decide(c.staff, c.case_id, c.packet["packetId"], body))
            == outcome
        )
    delivery = next(v for p, v in c.repository.documents.items() if p.startswith("mockDeliveries/"))
    assert len(delivery["holds"]) == 1
    assert outcome["adapterResult"]["status"] == "HOLD_RECORDED"
    events = c.packets.events(c.actor, c.case_id)["items"]
    assert any(e["action"] == "receiver.acknowledge" for e in events)
    assert any(e["action"] == "receiver.place_hold_simulated" for e in events)


def test_wrong_org_and_stale_packet_cannot_mutate_victim_or_invoke_hold(flow):
    c = flow
    send(c)
    body = {"action": "place_hold_simulated", "packetVersion": 1}
    with pytest.raises(IntakeError):
        asyncio.run(
            c.receiver.decide(
                Actor("other", "receiver", "mock-cyber"), c.case_id, c.packet["packetId"], body
            )
        )
    case = c.repository.get(f"cases/{c.case_id}")
    case["factsRevision"] += 1
    case["facts"]["ongoingContact"] = True
    c.repository.set(f"cases/{c.case_id}", case)
    for action in ("acknowledge", "place_hold_simulated"):
        with pytest.raises(IntakeError):
            asyncio.run(
                c.receiver.decide(
                    c.staff,
                    c.case_id,
                    c.packet["packetId"],
                    {"action": action, "packetVersion": 1},
                )
            )
    delivery = next(v for p, v in c.repository.documents.items() if p.startswith("mockDeliveries/"))
    assert delivery["holds"] == {}
    assert c.packets.get(c.actor, c.case_id, c.packet["packetId"])["status"] == "SENT"


@pytest.mark.parametrize(
    "result",
    [
        None,
        {"holdRef": "FAKE", "status": "HOLD_RECORDED", "ticketRef": "unsafe", "simulated": True},
    ],
)
def test_mcp_hold_adapter_rejects_malformed_results_without_echo(flow, result):
    from mcp.types import CallToolResult

    from packages.delivery.models import DeliveryError

    class FakeServer:
        async def call_tool(self, tool, arguments):
            assert tool == "place_hold"
            return CallToolResult(content=[], structured_content=result)

    adapter = flow.adapter.actual
    adapter.bank_server = FakeServer()
    with pytest.raises(DeliveryError, match="^mock_hold_failed$"):
        asyncio.run(adapter.place_hold("owner", "case", "delivery_" + "a" * 64, "key"))


def test_mcp_hold_timeout_is_bounded_and_errors_not_echoed(flow, monkeypatch):
    from packages.delivery.models import DeliveryError

    async def timeout(awaitable, *, timeout):
        assert timeout == 5
        awaitable.close()
        raise TimeoutError("credential-shaped provider content must never be echoed")

    monkeypatch.setattr("packages.delivery.adapter.asyncio.wait_for", timeout)
    with pytest.raises(DeliveryError, match="^mock_hold_failed$"):
        asyncio.run(flow.adapter.actual.place_hold("owner", "case", "delivery_" + "a" * 64, "key"))


@pytest.fixture
def requested_flow(flow):
    from packages.common.identifiers import canonical_hash
    from packages.schemas import PacketContent, PacketField, Provenance

    c = flow
    content = PacketContent.model_validate(c.packet["content"])
    content.fields.append(
        PacketField(
            key="contact.identifier",
            label="Caller identifier",
            value=None,
            availability="unknown",
            provenance=Provenance(source="victim_statement", reference="contact.identifier"),
        )
    )
    c.packet["content"] = content.model_dump(mode="json", by_alias=True)
    c.packet["contentHash"] = canonical_hash(c.packet["content"])
    c.repository.atomic(lambda tx: c.packets._save(tx, c.case_id, c.packet))
    send(c)
    asyncio.run(
        c.receiver.decide(
            c.staff,
            c.case_id,
            c.packet["packetId"],
            {
                "action": "request_info",
                "packetVersion": 1,
                "requestedItems": ["contact.identifier"],
                "message": "Please provide the caller identifier if available.",
            },
        )
    )
    case = c.repository.get(f"cases/{c.case_id}")
    c.request_id = case["informationRequestIds"][0]
    c.answer = {
        "requestId": c.request_id,
        "ifVersion": 1,
        "answers": [{"itemKey": "contact.identifier", "value": "synthetic-caller"}],
    }
    return c


def test_needs_info_answer_versions_reverifies_then_requires_fresh_explicit_send(requested_flow):
    from uuid import uuid4

    c = requested_flow
    before = c.packets.get(c.actor, c.case_id, c.packet["packetId"])
    assert before["informationRequests"][0]["requestedItems"] == [
        {"key": "contact.identifier", "label": "Caller identifier"}
    ]
    result = c.packets.answer(c.actor, c.case_id, c.packet["packetId"], c.answer, str(uuid4()))
    assert result["version"] == 2 and result["status"] == "DRAFT" and result["requiresApproval"]
    packet = c.packets.get(c.actor, c.case_id, c.packet["packetId"])
    assert packet["delivery"] is None and not packet["verification"]["passed"]
    assert packet["informationRequests"][0]["state"] == "answered"
    assert c.adapter.calls == 1
    assert (
        c.repository.get(f"cases/{c.case_id}/packets/{c.packet['packetId']}/versions/1")["status"]
        == "NEEDS_INFO"
    )
    asyncio.run(c.packets.process(result["jobId"]))
    packet = c.packets.get(c.actor, c.case_id, c.packet["packetId"])
    assert packet["status"] == "VERIFIED" and c.adapter.calls == 1
    with pytest.raises(IntakeError):
        asyncio.run(c.packets.approve(c.actor, c.case_id, c.packet["packetId"], approval(c.packet)))
    asyncio.run(c.packets.approve(c.actor, c.case_id, c.packet["packetId"], approval(packet)))
    assert c.adapter.calls == 2
    result = asyncio.run(
        c.receiver.decide(
            c.staff, c.case_id, c.packet["packetId"], {"action": "acknowledge", "packetVersion": 2}
        )
    )
    assert result["status"] == "ACKNOWLEDGED"
    assert c.packets.get(c.actor, c.case_id, c.packet["packetId"])["status"] == "ACKNOWLEDGED"


def test_answer_idempotency_is_actor_body_scoped_and_no_duplicate_version(requested_flow):
    from uuid import uuid4

    c, key = requested_flow, str(uuid4())
    result = c.packets.answer(c.actor, c.case_id, c.packet["packetId"], c.answer, key)
    assert c.packets.answer(c.actor, c.case_id, c.packet["packetId"], c.answer, key) == result
    altered = c.answer | {"answers": [{"itemKey": "contact.identifier", "value": "other-caller"}]}
    with pytest.raises(IntakeError) as error:
        c.packets.answer(c.actor, c.case_id, c.packet["packetId"], altered, key)
    assert error.value.code == "idempotency_conflict"
    with pytest.raises(IntakeError):
        c.packets.answer(
            Actor("other-victim", "victim"), c.case_id, c.packet["packetId"], c.answer, key
        )
    assert c.packets.get(c.actor, c.case_id, c.packet["packetId"])["version"] == 2


@pytest.mark.parametrize(
    "change",
    [
        "extra",
        "duplicate",
        "secret",
        "known",
        "wrong_version",
        "wrong_request",
        "wrong_org",
        "wrong_hash",
        "stale",
        "expiry",
    ],
)
def test_answer_invalid_input_never_versions_or_sends(requested_flow, change):
    from copy import deepcopy
    from uuid import uuid4

    c = requested_flow
    body = deepcopy(c.answer)
    if change == "extra":
        body["answers"].append({"itemKey": "invented", "value": "unsafe"})
    elif change == "duplicate":
        body["answers"] *= 2
    elif change == "secret":
        body["answers"][0]["value"] = "My OTP is 123456"
    elif change == "known":
        body["answers"] = [{"itemKey": "payment.amount", "value": "INR 1"}]
    elif change == "wrong_version":
        body["ifVersion"] = 2
    elif change == "wrong_request":
        body["requestId"] = "missing"
    elif change in {"wrong_org", "wrong_hash"}:
        path = f"cases/{c.case_id}/informationRequests/{c.request_id}"
        request = c.repository.get(path)
        request["orgId" if change == "wrong_org" else "contentHash"] = "wrong"
        c.repository.set(path, request)
    else:
        path = f"cases/{c.case_id}"
        case = c.repository.get(path)
        if change == "stale":
            case["facts"]["ongoingContact"] = True
        else:
            case["accessExpiresAtMs"] = 0
        c.repository.set(path, case)
    with pytest.raises(IntakeError):
        c.packets.answer(c.actor, c.case_id, c.packet["packetId"], body, str(uuid4()))
    packet = c.repository.get(f"cases/{c.case_id}/packets/{c.packet['packetId']}")
    assert packet["version"] == 1 and c.adapter.calls == 1


def test_optional_unavailable_answer_stays_explicit_without_fabricated_value(requested_flow):
    from uuid import uuid4

    c = requested_flow
    c.answer["answers"] = [
        {"itemKey": "contact.identifier", "value": "", "availability": "not_available"}
    ]
    result = c.packets.answer(c.actor, c.case_id, c.packet["packetId"], c.answer, str(uuid4()))
    asyncio.run(c.packets.process(result["jobId"]))
    packet = c.packets.get(c.actor, c.case_id, c.packet["packetId"])
    field = next(f for f in packet["content"]["fields"] if f["key"] == "contact.identifier")
    assert field["value"] is None and field["availability"] == "not_available"
    assert packet["status"] == "VERIFIED" and c.adapter.calls == 1
    assert "contact.identifier" not in c.repository.get(f"cases/{c.case_id}")["facts"].get(
        "unavailableFields", []
    )


def test_e19_http_contract_no_request_conflict_and_answer_job(requested_flow):
    from uuid import uuid4

    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from services.api.packets.router import create_packet_router

    c = requested_flow
    app = FastAPI()

    @app.middleware("http")
    async def actor_context(request: Request, call_next):
        request.state.actor = c.actor
        return await call_next(request)

    @app.exception_handler(IntakeError)
    async def problem(request, exc):
        return JSONResponse({"code": exc.code}, status_code=exc.status)

    app.include_router(create_packet_router(c.packets))
    url = f"/api/v1/cases/{c.case_id}/packets/{c.packet['packetId']}/answer"
    with TestClient(app) as client:
        response = client.post(
            url,
            json=c.answer | {"requestId": "no_request"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 409
        response = client.post(url, json=c.answer, headers={"Idempotency-Key": str(uuid4())})
        assert response.status_code == 200, response.text
        assert response.json()["jobId"].startswith("job_")
        assert response.json()["requiresApproval"] and response.json()["status"] == "DRAFT"
        assert client.post(url, json=c.answer).status_code == 422
    assert c.adapter.calls == 1
