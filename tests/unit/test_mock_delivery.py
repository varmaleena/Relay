"""Exercise actual registered MCP tools and repository-backed simulated outcomes."""

import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from packages.delivery import DeliveryError, DeliveryProjection, MockDeliveryService
from packages.delivery.adapter import LocalMCPDeliveryAdapter
from packages.intake.repository import MemoryRepository
from packages.packs.registry import PackRegistry

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def setup(tmp_path):
    shutil.copytree(ROOT / "packs", tmp_path / "packs")
    shutil.copytree(ROOT / "docs/pack-sources", tmp_path / "docs/pack-sources")
    registry = PackRegistry(tmp_path / "packs")
    repository = MemoryRepository()
    service = MockDeliveryService(
        repository,
        registry,
        allow_draft_preview=True,
        environment="local",
        demo_mode=True,
        require_case_record=False,
        clock=lambda: datetime(2026, 10, 15, tzinfo=UTC),
    )
    return service, repository, registry


def projection(**changes):
    return DeliveryProjection.model_validate(
        {
            "ownerUid": "synthetic-owner",
            "caseId": "case-synthetic",
            "caseRef": "RLY-SYNTHETIC",
            "packetId": "packet-synthetic",
            "packetVersion": 1,
            "contentHash": "a" * 64,
            "packId": "pack_in_cyber_rail",
            "packVersion": "0.1.0",
            "recipientId": "bank",
            "fields": {
                "payment.amount": "INR 45000",
                "payment.timestamp": "2026-10-15T00:00:00Z",
                "payment.transaction_ref": "SYNTHETIC-TXN",
            },
            "typology": "bank_impersonation",
            "simulation": {"minutesSincePayment": 20},
            **changes,
        }
    )


def test_real_registered_tools_and_durable_replay_without_persisting_packet_fields(setup):
    service, repository, registry = setup
    adapter = LocalMCPDeliveryAdapter(service)
    bank_tools = asyncio.run(adapter.bank_server.list_tools())
    assert {tool.name for tool in bank_tools} == {"submit_dispute", "place_hold", "get_status"}
    rail_tools = asyncio.run(adapter.rail_server.list_tools())
    assert {tool.name for tool in rail_tools} == {
        "file_report",
        "get_ticket",
        "list_recipients_notified",
    }
    first = asyncio.run(adapter.deliver(projection(), "synthetic-key"))
    assert first.simulated and first.status == "RECEIVED" and first.ticket_ref.startswith("SIM-IN-")
    restarted = MockDeliveryService(
        repository,
        registry,
        allow_draft_preview=True,
        environment="local",
        demo_mode=True,
        require_case_record=False,
    )
    assert (
        asyncio.run(LocalMCPDeliveryAdapter(restarted).deliver(projection(), "synthetic-key"))
        == first
    )
    assert len(repository.documents) == 1
    assert "SYNTHETIC-TXN" not in str(repository.documents)
    assert "INR 45000" not in str(repository.documents)


def test_payload_mutation_cannot_reuse_same_packet_version_key(setup):
    service, _, _ = setup
    asyncio.run(service.submit_dispute(projection(), "same"))
    with pytest.raises(DeliveryError, match="idempotency_conflict"):
        asyncio.run(service.submit_dispute(projection(contentHash="b" * 64), "same"))
    with pytest.raises(DeliveryError, match="idempotency_conflict"):
        asyncio.run(service.submit_dispute(projection(fields={}), "same"))


def test_registered_rail_tool_returns_honest_missing_mapping_and_scopes_ticket_reads(setup):
    service, _, _ = setup
    adapter = LocalMCPDeliveryAdapter(service)
    receipt = asyncio.run(adapter.deliver(projection(recipientId="cyber"), "rail"))
    assert receipt.status == "NEEDS_INFO" and receipt.adapter == "mcp-rail-mock"
    for owner, case in [("other-owner", "case-synthetic"), ("synthetic-owner", "other-case")]:
        with pytest.raises(ToolError):
            asyncio.run(
                adapter.rail_server.call_tool(
                    "get_ticket",
                    {
                        "owner_uid": owner,
                        "case_id": case,
                        "delivery_id": receipt.delivery_id,
                    },
                )
            )
    with pytest.raises(ToolError):
        asyncio.run(
            adapter.bank_server.call_tool(
                "get_status",
                {
                    "owner_uid": "synthetic-owner",
                    "case_id": "case-synthetic",
                    "delivery_id": receipt.delivery_id,
                },
            )
        )


@pytest.mark.emulator
def test_real_firestore_mock_receipt_survives_new_repository_and_deletes(tmp_path):
    import os
    from uuid import uuid4

    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    from packages.intake.repository import FirestoreRepository

    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    if not host:
        pytest.skip("Local emulator required; no cloud fallback")
    if not host.startswith(("127.0.0.1:", "localhost:")):
        pytest.fail("Loopback emulator only")
    client = firestore.Client(project="demo-relay-local", credentials=AnonymousCredentials())
    registry = PackRegistry(ROOT / "packs")
    owner = "synthetic-mock-" + uuid4().hex
    projected = projection(ownerUid=owner)
    first_service = MockDeliveryService(
        FirestoreRepository(client),
        registry,
        allow_draft_preview=True,
        environment="local",
        demo_mode=True,
        require_case_record=False,
    )
    receipt = None
    try:
        receipt = asyncio.run(LocalMCPDeliveryAdapter(first_service).deliver(projected, "stable"))
        restarted = MockDeliveryService(
            FirestoreRepository(client),
            registry,
            allow_draft_preview=True,
            environment="local",
            demo_mode=True,
            require_case_record=False,
        )
        assert (
            asyncio.run(LocalMCPDeliveryAdapter(restarted).deliver(projected, "stable")) == receipt
        )
        assert first_service.get_status(owner, projected.case_id, receipt.delivery_id)["simulated"]
    finally:
        if receipt:
            first_service.repository.atomic(
                lambda tx: first_service.cleanup_case(
                    tx, owner, projected.case_id, [receipt.delivery_id]
                )
            )
            assert first_service.repository.get(f"mockDeliveries/{receipt.delivery_id}") is None
        client.close()


def test_owner_case_and_version_isolation_and_deletion(setup):
    service, repository, _ = setup
    first = asyncio.run(service.submit_dispute(projection(), "shared-key"))
    second = asyncio.run(service.submit_dispute(projection(ownerUid="other-owner"), "shared-key"))
    third = asyncio.run(service.submit_dispute(projection(packetVersion=2), "shared-key"))
    assert len({first.delivery_id, second.delivery_id, third.delivery_id}) == 3
    for owner, case in [("other-owner", "case-synthetic"), ("synthetic-owner", "other-case")]:
        with pytest.raises(DeliveryError, match="not_found"):
            service.get_status(owner, case, first.delivery_id)
    repository.atomic(
        lambda tx: service.cleanup_case(
            tx, "synthetic-owner", "case-synthetic", [first.delivery_id, second.delivery_id]
        )
    )
    assert repository.get(f"mockDeliveries/{first.delivery_id}") is None
    assert repository.get(f"mockDeliveries/{second.delivery_id}") is not None


def test_missing_fields_wrong_adapter_and_unavailable_recipient(setup):
    service, _, _ = setup
    receipt = asyncio.run(service.submit_dispute(projection(fields={}), "empty"))
    assert receipt.status == "NEEDS_INFO"
    assert set(receipt.missing_items) == {
        "payment.amount",
        "payment.timestamp",
        "payment.transaction_ref",
    }
    with pytest.raises(DeliveryError, match="wrong_adapter"):
        asyncio.run(service.submit_dispute(projection(recipientId="cyber"), "wrong"))
    with pytest.raises(DeliveryError, match="recipient_unavailable"):
        asyncio.run(service.file_report(projection(recipientId="arbitrary-destination"), "wrong"))


@pytest.mark.parametrize("state", ["absent", "wrong_owner", "deleting", "expired"])
def test_runtime_delivery_requires_live_owned_case_in_same_write_transaction(setup, state):
    service, repository, _ = setup
    service.require_case_record = True
    case: dict[str, Any] = {"victimUid": "synthetic-owner", "ttlAt": "2026-10-16T00:00:00Z"}
    if state == "wrong_owner":
        case["victimUid"] = "other-owner"
    if state == "deleting":
        case["deleting"] = True
    if state == "expired":
        case["ttlAt"] = "2026-10-14T00:00:00Z"
    if state != "absent":
        repository.set("cases/case-synthetic", case)
    with pytest.raises(DeliveryError, match="case_unavailable"):
        asyncio.run(service.submit_dispute(projection(), "guarded"))
    assert not any(path.startswith("mockDeliveries/") for path in repository.documents)


@pytest.mark.parametrize(
    "mode,minutes,expected",
    [
        ("success", None, "HOLD_RECORDED"),
        ("funds_moved", 1, "FUNDS_ALREADY_MOVED"),
        ("auto", 90, "HOLD_RECORDED"),
        ("auto", 90.01, "FUNDS_ALREADY_MOVED"),
        ("auto", None, "REJECTED"),
    ],
)
def test_hold_simulation_rules_are_exact_and_idempotent(setup, mode, minutes, expected):
    service, _, _ = setup
    sent = asyncio.run(
        service.submit_dispute(
            projection(simulation={"bankMode": mode, "minutesSincePayment": minutes}), "send"
        )
    )
    first = asyncio.run(
        service.place_hold("synthetic-owner", "case-synthetic", sent.delivery_id, "hold")
    )
    assert first.status == expected and first.simulated and first.hold_ref.startswith("SIM-HOLD-")
    assert (
        asyncio.run(
            service.place_hold("synthetic-owner", "case-synthetic", sent.delivery_id, "hold")
        )
        == first
    )


def test_rail_uses_only_pack_category_mapping_and_explicit_misroute(setup):
    service, _, registry = setup
    result = asyncio.run(
        service.file_report(projection(recipientId="cyber", category="invented"), "unmapped")
    )
    assert (
        result.status == "NEEDS_INFO"
        and "pack.typology_categories.bank_impersonation" in result.missing_items
    )
    path = registry.root / "india-cyber-rail.yaml"
    body = yaml.safe_load(path.read_text(encoding="utf-8"))
    # Synthetic routing fixture only; no claim of an official rail category.
    next(r for r in body["recipients"] if r["id"] == "cyber")["typology_categories"] = {
        "bank_impersonation": "SYNTHETIC_CATEGORY"
    }
    path.write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")
    for category, mode, expected in [
        ("SYNTHETIC_CATEGORY", "normal", "ROUTED"),
        ("wrong", "normal", "MISROUTED_SIMULATED"),
        ("SYNTHETIC_CATEGORY", "misrouted", "MISROUTED_SIMULATED"),
    ]:
        result = asyncio.run(
            service.file_report(
                projection(recipientId="cyber", category=category, simulation={"railMode": mode}),
                category + mode,
            )
        )
        assert result.status == expected and result.simulated


@pytest.mark.parametrize(
    "changes",
    [
        {"transcript": []},
        {"fields": {"facts": {"secret": "x"}}},
        {"fields": {"otp": "123456"}},
        {"fields": {"note": "my password is fake-secret"}},
        {"fields": {"blob": "x" * 4001}},
        {"simulation": {"minutesSincePayment": float("nan")}},
    ],
)
def test_projection_rejects_case_material_secrets_and_unbounded_inputs(changes):
    with pytest.raises(ValidationError):
        projection(**changes)
