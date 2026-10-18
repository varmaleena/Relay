from datetime import UTC, datetime
from unittest.mock import Mock

from packages.intake.repository import MemoryRepository
from packages.linking.delivery import index_approved_delivery


def test_only_approved_confirmed_scammer_values_reach_hasher():
    repo, linking = MemoryRepository(), Mock()
    entries = []
    for index, (value, role, status) in enumerate(
        [
            ("approved@fictional", "scammer", "confirmed"),
            ("private@fictional", "scammer", "confirmed"),
            ("victim@fictional", "victim", "confirmed"),
            ("extracted@fictional", "scammer", "extracted"),
        ]
    ):
        entries.append(
            {
                "entityId": f"entity-{index}",
                "type": "upi_id",
                "rawValue": value,
                "normalizedValue": value,
                "role": role,
                "status": status,
                "confidence": 1.0,
            }
        )
    repo.set(
        "cases/case_fixture/evidence/ev_fixture",
        {
            "status": "ready",
            "extraction": {
                "evidenceId": "ev_fixture",
                "documentType": "synthetic",
                "entities": entries,
                "summary": "Synthetic fixture",
                "confidence": 1.0,
                "model": "fixture",
                "promptVersion": "fixture",
            },
        },
    )
    case = {
        "caseId": "case_fixture",
        "caseRef": "RLY-2026-FIXTURE",
        "evidenceIds": ["ev_fixture"],
        "createdAt": datetime.now(UTC).isoformat(),
        "facts": {"country": {"value": "IN"}},
        "receiverProjectionRefs": [{"orgId": "mock-bank", "packetId": "packet_fixture"}],
    }
    packet = {
        "content": {
            "fields": [
                {"value": "approved@fictional"},
                {"value": "victim@fictional"},
                {"value": "extracted@fictional"},
            ]
        }
    }
    repo.atomic(lambda tx: index_approved_delivery(linking, tx, case, packet))
    args, kwargs = linking.replace_case.call_args
    assert args[2] == [
        {"type": "upi_id", "value": "approved@fictional", "role": "scammer", "status": "confirmed"}
    ]
    assert args[1] == {"mock-bank"} and kwargs["case_id"] == "case_fixture"
    assert kwargs["tx"] is not None
