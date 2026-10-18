"""Actual approved local MCP delivery followed by trusted fact correction."""

from uuid import uuid4

import pytest

from packages.intake.service import IntakeError
from packages.linking.core import Hasher
from packages.linking.receiver import ReceiverLinks
from packages.linking.service import LinkingService
from tests.unit.test_delivery_receiver_integration import flow, send  # noqa: F401


def test_approved_delivery_fact_update_revokes_link_proof(flow):  # noqa: F811
    c = flow
    send(c)
    linking = LinkingService(c.repository, Hasher(b"x" * 32))
    case = c.repository.get(f"cases/{c.case_id}")
    ref = case["caseRef"]
    entities = [
        {"type": "upi_id", "value": "ring@fictional", "role": "scammer", "status": "confirmed"}
    ]
    linking.replace_case(ref, {"mock-bank"}, entities, c.clock[0], case_id=c.case_id)
    expiry = case["accessExpiresAtMs"]
    linking.replace_case("RLY_OTHER", {"mock-bank"}, entities, c.clock[0], case_id="other")
    c.repository.set(
        "receiverViews/mock-bank/cases/other",
        {
            "caseRef": "RLY_OTHER",
            "latestPacketId": "p",
            "packetIds": ["p"],
            "accessExpiresAtMs": expiry,
        },
    )
    c.repository.set(
        "receiverViews/mock-bank/cases/other/packets/p",
        {
            "caseRef": "RLY_OTHER",
            "accessExpiresAtMs": expiry,
            "packet": {"packetId": "p", "version": 1, "contentHash": "synthetic", "status": "SENT"},
        },
    )
    receiver_links = ReceiverLinks(linking, clock=lambda: c.clock[0])
    old = receiver_links.list(c.staff, c.case_id)["items"][0]["linkId"]
    c.intake.update_facts(c.actor, c.case_id, {"facts": {"ongoingContact": False}})
    path = f"receiverViews/mock-bank/cases/{c.case_id}/packets/{c.packet['packetId']}"
    assert c.repository.get(path)["packet"]["stale"] is True
    assert receiver_links.list(c.staff, "other")["items"] == []
    with pytest.raises(IntakeError) as stale:
        receiver_links.list(c.staff, c.case_id)
    assert stale.value.code == "stale_link"
    with pytest.raises(IntakeError) as error:
        receiver_links.validate(c.staff, old, "related", None, str(uuid4()))
    assert error.value.code == "stale_link"
