"""Recipient isolation, explicit decisions and bounded minimal projections."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.common.identifiers import canonical_hash
from packages.delivery.models import HoldReceipt
from packages.intake.repository import MemoryRepository
from packages.intake.service import IntakeError
from packages.receiver.service import ReceiverService
from packages.safety import Actor
from packages.schemas import PacketContent, PacketField, Provenance

ORGS = {"bank": "mock-bank", "cyber": "mock-cyber", "payment-app": "mock-payment-app"}


class NoFullCaseRepository(MemoryRepository):
    def get(self, path):
        assert not path.startswith("cases/"), "Receiver must not load a full victim case"
        return super().get(path)


class HoldAdapter:
    def __init__(self):
        self.calls = []
        self.before = None
        self.fail = False

    async def __call__(self, owner, case_id, delivery_id, key):
        self.calls.append((owner, case_id, delivery_id, key))
        if self.before:
            self.before()
        if self.fail:
            raise OSError("synthetic-private-content")
        return HoldReceipt(
            hold_ref="SIM-HOLD-000001",
            ticket_ref="SIM-IN-000001",
            status="HOLD_RECORDED",
            simulated=True,
        )


def submitted(recipient="bank", packet_id="packet_a", *, missing=False, version=1):
    content = PacketContent(
        language="en",
        recipient_language="en",
        subject="Synthetic report",
        summary="Synthetic approved facts.",
        fields=[
            PacketField(
                key="payment.transaction_ref",
                label="Transaction reference",
                value=None if missing else "SYNTHETIC-REF",
                required=True,
                provenance=Provenance(source="confirmed"),
            )
        ],
        message="Please review this synthetic report.",
        requested_actions=["Review"],
        citations=[],
        attachments=[],
        victim_copy={"lang": "en", "text": "Synthetic copy"},
        footer="Simulated only.",
        completeness={"score": 0.0 if missing else 1.0},
    )
    body = content.model_dump(mode="json", by_alias=True)
    return {
        "packetId": packet_id,
        "recipientId": recipient,
        "recipientName": "Synthetic " + recipient,
        "version": version,
        "status": "SENT",
        "content": body,
        "verification": {"passed": True, "checks": [], "iterations": 1},
        "delivery": {
            "adapter": "mcp-bank-mock",
            "ticketRef": "SIM-IN-000001",
            "simulated": True,
            "sentAt": "2026-10-17T00:00:00Z",
        },
        "deadlines": [],
        "planId": "plan_a",
        "stale": False,
        "factsRevision": 1,
        "contentHash": canonical_hash(body),
        "unapprovedFullCase": {"secret": "must not cross"},
    }


@pytest.fixture
def setup():
    repo = NoFullCaseRepository()
    clock = [datetime.now(UTC)]
    adapter, bridge = HoldAdapter(), []
    service = ReceiverService(
        repo,
        recipient_orgs=ORGS,
        hold_adapter=adapter,
        decision_bridge=lambda tx, event: bridge.append(event),
        clock=lambda: clock[0],
    )

    def project(packet=None, case_id="case_a", urgency="high"):
        packet = packet or submitted()
        receipt = {
            "deliveryId": "delivery_" + "a" * 64,
            "ticketRef": "SIM-IN-000001",
            "simulated": True,
        }
        plan = {
            "countryCode": "IN",
            "classification": {
                "typology": "bank_impersonation",
                "authorizationType": "authorized_manipulated",
                "urgency": {"level": urgency},
            },
        }
        return repo.atomic(
            lambda tx: service.project_delivery(
                tx,
                owner_uid="synthetic-owner",
                case_id=case_id,
                case_ref="SYN-CASE",
                packet=packet,
                plan=plan,
                receipt=receipt,
                access_expires_at_ms=int((clock[0] + timedelta(hours=2)).timestamp() * 1000),
            )
        )

    project()
    return SimpleNamespace(
        repo=repo,
        service=service,
        clock=clock,
        adapter=adapter,
        bridge=bridge,
        project=project,
        actor=Actor("receiver_a", "receiver", "mock-bank"),
    )


def decision(action, **updates):
    return {"action": action, "packetVersion": 1, **updates}


def test_queue_and_dossier_contain_only_addressed_approved_projection(setup):
    c = setup
    assert len(c.service.queue(c.actor)["items"]) == 1
    result = asyncio.run(c.service.get_case(c.actor, "case_a"))
    assert result["packet"]["packetId"] == "packet_a" and result["minutesSincePayment"] is None
    assert result["briefStatus"] == "unavailable"
    assert "unapprovedFullCase" not in str(result) and "ownerUid" not in str(result)
    assert result["evidence"] == [] and result["links"] == []
    assert c.adapter.calls == []


@pytest.mark.parametrize(
    "actor",
    [
        Actor("victim", "victim"),
        Actor("admin", "admin"),
        Actor("receiver", "receiver"),
        Actor("other", "receiver", "mock-cyber"),
    ],
)
def test_role_org_isolation_never_grants_raw_case_or_other_packet(actor, setup):
    with pytest.raises(IntakeError):
        asyncio.run(setup.service.get_case(actor, "case_a"))
    assert setup.adapter.calls == []


def test_queue_is_sorted_urgency_then_age_and_cursor_stays_org_scoped(setup):
    c = setup
    c.project(submitted(packet_id="packet_critical"), case_id="case_critical", urgency="critical")
    c.project(submitted(packet_id="packet_normal"), case_id="case_normal", urgency="normal")
    first = c.service.queue(c.actor, limit=1)
    assert first["items"][0]["urgency"] == "critical" and first["nextCursor"]
    second = c.service.queue(c.actor, limit=1, cursor=first["nextCursor"])
    assert second["items"][0]["urgency"] == "high"
    with pytest.raises(IntakeError):
        c.service.queue(Actor("other", "receiver", "mock-cyber"), cursor=first["nextCursor"])
    assert len(c.service.queue(c.actor, urgency="normal")["items"]) == 1


def test_multiple_addressed_packets_can_be_selected_explicitly(setup):
    c = setup
    c.project(submitted(packet_id="packet_b"))
    assert len(c.service.queue(c.actor)["items"]) == 2
    assert asyncio.run(c.service.get_case(c.actor, "case_a"))["packet"]["packetId"] == "packet_b"
    assert (
        asyncio.run(c.service.get_case(c.actor, "case_a", "packet_a"))["packet"]["packetId"]
        == "packet_a"
    )


@pytest.mark.parametrize("state", ["expired", "deleting"])
def test_expired_or_deleting_projection_fails_closed(setup, state):
    c = setup
    if state == "expired":
        c.clock[0] += timedelta(hours=3)
    else:
        path = "receiverViews/mock-bank/cases/case_a"
        parent = c.repo.get(path)
        parent["deleting"] = True
        c.repo.set(path, parent)
    with pytest.raises(IntakeError):
        asyncio.run(c.service.get_case(c.actor, "case_a"))


def test_explicit_acknowledgment_is_version_bound_and_idempotent(setup):
    c = setup
    with pytest.raises(IntakeError):
        asyncio.run(
            c.service.decide(
                c.actor, "case_a", "packet_a", decision("acknowledge", packetVersion=2)
            )
        )
    result = asyncio.run(c.service.decide(c.actor, "case_a", "packet_a", decision("acknowledge")))
    assert result["status"] == "ACKNOWLEDGED"
    assert (
        asyncio.run(c.service.decide(c.actor, "case_a", "packet_a", decision("acknowledge")))
        == result
    )
    assert len(c.bridge) == 1 and c.adapter.calls == []
    assert c.bridge[0]["actor"] == c.actor and c.bridge[0]["packetVersion"] == 1


@pytest.mark.parametrize("action", ["reject", "escalate"])
def test_reject_and_escalate_need_reason_and_record_human_actor(setup, action):
    c = setup
    with pytest.raises(IntakeError):
        asyncio.run(c.service.decide(c.actor, "case_a", "packet_a", decision(action)))
    result = asyncio.run(
        c.service.decide(
            c.actor, "case_a", "packet_a", decision(action, reason="Synthetic staff reason")
        )
    )
    assert result["status"] == ("REJECTED" if action == "reject" else "SENT")
    assert c.bridge[0]["reason"] == "Synthetic staff reason"


def test_request_info_only_names_missing_approved_fields_and_creates_request(setup):
    c = setup
    c.project(submitted(packet_id="packet_missing", missing=True))
    body = decision(
        "request_info",
        requestedItems=["payment.transaction_ref"],
        message="Please provide the transaction reference if available.",
    )
    result = asyncio.run(c.service.decide(c.actor, "case_a", "packet_missing", body))
    assert result["status"] == "NEEDS_INFO" and c.bridge[0]["requestId"].startswith("request_")
    assert len([key for key in c.repo.documents if "/requests/" in key]) == 1
    with pytest.raises(IntakeError):
        asyncio.run(
            c.service.decide(
                c.actor, "case_a", "packet_missing", body | {"requestedItems": ["password"]}
            )
        )


def test_hold_only_runs_after_explicit_matching_human_decision_and_replays(setup):
    c = setup
    assert c.adapter.calls == []
    result = asyncio.run(
        c.service.decide(c.actor, "case_a", "packet_a", decision("place_hold_simulated"))
    )
    assert result["status"] == "ACTIONED" and result["adapterResult"]["simulated"]
    assert result["adapterResult"]["ref"].startswith("SIM-HOLD-")
    assert len(c.adapter.calls) == 1
    assert (
        asyncio.run(
            c.service.decide(c.actor, "case_a", "packet_a", decision("place_hold_simulated"))
        )
        == result
    )
    assert len(c.adapter.calls) == 1


def test_hold_adapter_failure_does_not_report_action_or_immediately_double_call(setup):
    c = setup
    c.adapter.fail = True
    for _ in range(2):
        with pytest.raises(IntakeError) as error:
            asyncio.run(
                c.service.decide(c.actor, "case_a", "packet_a", decision("place_hold_simulated"))
            )
        assert error.value.status == 503
    assert len(c.adapter.calls) == 1 and c.bridge == []
    assert asyncio.run(c.service.get_case(c.actor, "case_a"))["packet"]["status"] == "SENT"


def test_new_packet_version_during_hold_cannot_receive_old_decision_status(setup):
    c = setup
    c.adapter.before = lambda: c.project(submitted(version=2))
    with pytest.raises(IntakeError) as error:
        asyncio.run(
            c.service.decide(c.actor, "case_a", "packet_a", decision("place_hold_simulated"))
        )
    assert error.value.code == "version_conflict"
    current = asyncio.run(c.service.get_case(c.actor, "case_a"))["packet"]
    assert current["version"] == 2 and current["status"] == "SENT"


def test_cleanup_removes_projection_private_requests_decisions_and_queue(setup):
    c = setup
    c.project(submitted(packet_id="packet_missing", missing=True))
    asyncio.run(
        c.service.decide(
            c.actor,
            "case_a",
            "packet_missing",
            decision("request_info", requestedItems=["payment.transaction_ref"]),
        )
    )
    c.repo.atomic(
        lambda tx: c.service.cleanup_case(
            tx,
            "case_a",
            [
                {"orgId": "mock-bank", "packetId": "packet_a"},
                {"orgId": "mock-bank", "packetId": "packet_missing"},
            ],
        )
    )
    assert c.repo.documents == {}


def test_generated_brief_cached_privately_and_bound_to_packet_status(setup):
    calls = []

    async def make(projection):
        calls.append(projection)
        return setup.service._basic_brief(projection)

    setup.service.brief_maker = make
    first = asyncio.run(setup.service.get_case(setup.actor, "case_a"))
    second = asyncio.run(setup.service.get_case(setup.actor, "case_a"))
    assert first["briefStatus"] == second["briefStatus"] == "generated"
    assert len(calls) == 1
    public, private, _ = setup.service._paths("mock-bank", "case_a", "packet_a")
    assert not any(key.startswith("brief") for key in setup.repo.get(public))
    assert setup.repo.get(private)["brief"] == first["brief"]
    asyncio.run(
        setup.service.decide(
            setup.actor,
            "case_a",
            "packet_a",
            {
                "action": "acknowledge",
                "packetVersion": 1,
            },
        )
    )
    asyncio.run(setup.service.get_case(setup.actor, "case_a"))
    assert len(calls) == 2


def test_failed_or_mismatched_brief_never_cached_and_poll_is_bounded(setup):
    calls = []

    async def make(projection):
        calls.append(projection)
        brief = setup.service._basic_brief(projection)
        brief["completenessScore"] = 0.5
        return brief

    setup.service.brief_maker = make
    for _ in range(2):
        result = asyncio.run(setup.service.get_case(setup.actor, "case_a"))
        assert result["briefStatus"] == "unavailable"
    assert len(calls) == 1
    _, private, _ = setup.service._paths("mock-bank", "case_a", "packet_a")
    assert "brief" not in setup.repo.get(private)
    setup.clock[0] += timedelta(minutes=3)
    asyncio.run(setup.service.get_case(setup.actor, "case_a"))
    assert len(calls) == 2


def test_brief_projection_change_during_generation_cannot_commit(setup):
    async def make(projection):
        setup.project(submitted(version=2))
        return setup.service._basic_brief(projection)

    setup.service.brief_maker = make
    with pytest.raises(IntakeError) as error:
        asyncio.run(setup.service.get_case(setup.actor, "case_a"))
    assert error.value.status == 409
    _, private, _ = setup.service._paths("mock-bank", "case_a", "packet_a")
    assert "brief" not in setup.repo.get(private)


def test_trusted_preflight_denies_stale_facts_before_any_hold(setup):
    class StaleBridge:
        def validate(self, tx, decision):
            assert decision["actor"] == setup.actor
            assert decision["packetVersion"] == 1
            assert decision["contentHash"] == submitted()["contentHash"]
            raise IntakeError(409, "version_conflict")

        def __call__(self, tx, decision):
            pytest.fail("No final mutation after failed preflight")

    setup.service.decision_bridge = StaleBridge()
    with pytest.raises(IntakeError) as error:
        asyncio.run(
            setup.service.decide(
                setup.actor,
                "case_a",
                "packet_a",
                {
                    "action": "place_hold_simulated",
                    "packetVersion": 1,
                },
            )
        )
    assert error.value.status == 409
    assert setup.adapter.calls == []
    assert not any("/decisions/" in path for path in setup.repo.documents)


def test_explicit_idempotency_key_conflict_replay_and_actor_scope(setup):
    from uuid import uuid4

    key = str(uuid4())
    body = {"action": "place_hold_simulated", "packetVersion": 1}
    first = asyncio.run(setup.service.decide(setup.actor, "case_a", "packet_a", body, key))
    assert asyncio.run(setup.service.decide(setup.actor, "case_a", "packet_a", body, key)) == first
    assert len(setup.adapter.calls) == 1
    assert len(setup.bridge) == 1
    with pytest.raises(IntakeError) as error:
        asyncio.run(
            setup.service.decide(
                setup.actor,
                "case_a",
                "packet_a",
                {
                    "action": "acknowledge",
                    "packetVersion": 1,
                },
                key,
            )
        )
    assert error.value.status == 409
    assert len(setup.adapter.calls) == 1
    second_actor = Actor("receiver_b", "receiver", "mock-bank")
    asyncio.run(setup.service.decide(second_actor, "case_a", "packet_a", body, key))
    assert len(setup.adapter.calls) == 2
