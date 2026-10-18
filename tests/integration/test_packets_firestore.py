"""M3 local durability through actual ADK planning and registered MCP mocks."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from packages.delivery import MockDeliveryService
from packages.delivery.adapter import LocalMCPDeliveryAdapter
from packages.intake.repository import FirestoreRepository
from packages.intake.service import IntakeError, IntakeService
from packages.packets.service import PacketService
from packages.planning.service import PlanningService
from tests.unit.test_packet_service import SyntheticPipeline, approval, make_packet_context


@pytest.mark.emulator
def test_firestore_packet_versions_outbox_restart_receipt_replay_and_full_delete(tmp_path):
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    if not host:
        pytest.skip("Local Firestore emulator required; no cloud fallback")
    if not host.startswith(("127.0.0.1:", "localhost:")):
        pytest.fail("Only the loopback emulator is permitted")
    client = firestore.Client(project="demo-relay-local", credentials=AnonymousCredentials())
    c = make_packet_context(tmp_path, FirestoreRepository(client))
    try:
        plan = c.planning.get_plan(c.actor, c.case_id)
        body, key = {"planId": plan["planId"]}, str(uuid4())
        job = c.packets.generate(c.actor, c.case_id, body, key)
        assert c.packets.generate(c.actor, c.case_id, body, key) == job
        # Rebuild services and repositories before claiming the persisted job.
        intake = IntakeService(
            FirestoreRepository(client), c.intake.storage, None, None, clock=lambda: c.clock[0]
        )
        intake.planning = PlanningService(intake, c.planning.workflow)
        mock = MockDeliveryService(
            intake.repository,
            c.registry,
            allow_draft_preview=True,
            environment="local",
            demo_mode=True,
            clock=lambda: c.clock[0],
        )
        packets = PacketService(intake, SyntheticPipeline(), LocalMCPDeliveryAdapter(mock))
        intake.packets = packets
        asyncio.run(packets.process(job["jobId"]))
        packet_id = packets.list(c.actor, c.case_id)["items"][0]["packetId"]
        original = packets.get(c.actor, c.case_id, packet_id)
        edit = packets.edit(
            c.actor, c.case_id, packet_id, {"ifVersion": 1, "message": "Synthetic revised report."}
        )
        asyncio.run(packets.process(edit["jobId"]))
        current = packets.get(c.actor, c.case_id, packet_id)
        assert current["version"] == 2 and current["status"] == "VERIFIED"
        first_version = intake.repository.get(f"cases/{c.case_id}/packets/{packet_id}/versions/1")
        assert first_version is not None
        assert first_version["content"] == original["content"]
        with pytest.raises(IntakeError):
            asyncio.run(packets.approve(c.actor, c.case_id, packet_id, approval(original)))
        # Lose the API response after the mock persisted its receipt.
        c.adapter.actual = LocalMCPDeliveryAdapter(mock)
        c.adapter.fail_after = True
        packets.adapter = c.adapter
        with pytest.raises(IntakeError):
            asyncio.run(packets.approve(c.actor, c.case_id, packet_id, approval(current)))
        pending_packet = intake.repository.get(f"cases/{c.case_id}/packets/{packet_id}")
        assert pending_packet is not None
        pending = pending_packet["deliveryPending"]
        c.clock[0] += timedelta(minutes=2)
        restarted = PacketService(intake, SyntheticPipeline(), LocalMCPDeliveryAdapter(mock))
        intake.packets = restarted
        asyncio.run(restarted.process_delivery(pending))
        sent = restarted.get(c.actor, c.case_id, packet_id)
        assert sent["status"] == "SENT" and sent["delivery"]["simulated"]
        assert (
            asyncio.run(restarted.approve(c.actor, c.case_id, packet_id, approval(sent)))[
                "delivery"
            ]
            == sent["delivery"]
        )
        case = intake.repository.get(f"cases/{c.case_id}")
        assert case is not None
        assert len(case["deliveryIds"]) == 1
        intake.delete_case(c.actor, c.case_id)
        assert intake.repository.get(f"cases/{c.case_id}") is None
        for collection in ("packets", "approvals", "notifications"):
            assert not list(client.collection(f"cases/{c.case_id}/{collection}").stream())
        assert not list(
            client.collection(f"cases/{c.case_id}/packets/{packet_id}/versions").stream()
        )
        for delivery_id in case["deliveryIds"]:
            assert intake.repository.get(f"mockDeliveries/{delivery_id}") is None
        for job_id in case["jobIds"]:
            assert intake.repository.get(f"jobs/{job_id}") is None
    finally:
        if c.repository.get(f"cases/{c.case_id}"):
            c.intake.delete_case(c.actor, c.case_id)
        client.close()
