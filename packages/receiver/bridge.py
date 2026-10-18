"""Trusted victim-side mutations for a scoped, explicit receiver decision.

Receiver projections never contain the full victim case. This server-only bridge
checks the addressed organization and exact current version before mutating the
victim tracker in the same transaction as the receiver's audited decision.
"""

from typing import Any

from packages.intake.service import IntakeError, stamp
from packages.safety import Actor

DEMO_RECIPIENT_ORGS = {
    "bank": "mock-bank",
    "cyber": "mock-cyber",
    "payment-app": "mock-payment-app",
}


class ReceiverDecisionBridge:
    def __init__(self, intake: Any, recipient_orgs: dict[str, str]) -> None:
        self.intake, self.recipient_orgs = intake, dict(recipient_orgs)

    def validate(self, tx: Any, decision: dict[str, Any]) -> tuple[Any, Any]:
        actor = decision["actor"]
        if (
            not isinstance(actor, Actor)
            or actor.role != "receiver"
            or actor.org_id != decision["orgId"]
        ):
            raise IntakeError(403, "forbidden")
        case_id, packet_id = decision["caseId"], decision["packetId"]
        case = tx.get(f"cases/{case_id}")
        if not case:
            raise IntakeError(404, "not_found")
        case = self.intake._case(tx, case_id, Actor(case["victimUid"], "victim"))
        packet = tx.get(f"cases/{case_id}/packets/{packet_id}")
        if not packet or self.recipient_orgs.get(packet["recipientId"]) != actor.org_id:
            raise IntakeError(403, "forbidden")
        if (
            packet["version"] != decision["packetVersion"]
            or packet["contentHash"] != decision["contentHash"]
            or self.intake.packets._stale(case, packet)
            or not packet.get("delivery")
        ):
            raise IntakeError(409, "version_conflict")
        return case, packet

    def __call__(self, tx: Any, decision: dict[str, Any]) -> None:
        case, packet = self.validate(tx, decision)
        actor = decision["actor"]
        case_id, packet_id = decision["caseId"], decision["packetId"]
        if decision["action"] == "request_info":
            request_id = decision["requestId"]
            ids = case.setdefault("informationRequestIds", [])
            if len(ids) >= 40 and request_id not in ids:
                raise IntakeError(429, "rate_limited")
            if request_id not in ids:
                ids.append(request_id)
            tx.set(
                f"cases/{case_id}/informationRequests/{request_id}",
                {
                    "requestId": request_id,
                    "packetId": packet_id,
                    "packetVersion": packet["version"],
                    "contentHash": packet["contentHash"],
                    "orgId": actor.org_id,
                    "requestedItems": decision["requestedItems"],
                    "message": decision.get("message") or "",
                    "state": "open",
                    "createdAt": stamp(self.intake.clock()),
                    "receiverUid": actor.uid,
                },
            )
        packet["status"] = decision["status"]
        packet["receiverDecisionId"] = decision["decisionId"]
        self.intake.packets._save(tx, case_id, packet)
        event = decision["event"]
        if event["eventId"] not in case.setdefault("eventIds", []):
            case["eventIds"].append(event["eventId"])
        tx.set(f"cases/{case_id}/events/{event['eventId']}", event)
        case["updatedAt"] = stamp(self.intake.clock())
        tx.set(f"cases/{case_id}", case)
        text = (
            "डेमो संस्था ने आपकी रिपोर्ट की समीक्षा की है। डेमो अपडेट देखें।"
            if case["language"] == "hi"
            else "A simulated institution reviewed your report. Check your demo updates."
        )
        self.intake.packets._notify(tx, case, packet_id, "receiver." + decision["action"], text)
