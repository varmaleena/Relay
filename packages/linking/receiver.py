"""Receiver-visible links are derived only from active addressed projections."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from packages.common.identifiers import canonical_hash
from packages.intake.repository import Transaction
from packages.intake.service import IntakeError
from packages.receiver.service import identifier
from packages.safety import Actor, scrub_credentials

from .service import INDEX, LinkingService


class ReceiverLinks:
    def __init__(self, linking: LinkingService, clock=None) -> None:
        self.linking = linking
        self.repository = linking.repository
        self.clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _org(actor: Actor) -> str:
        if actor.role != "receiver" or not actor.uid or not actor.org_id:
            raise IntakeError(403, "forbidden")
        return identifier(actor.org_id)

    def _active(self, document: dict[str, Any] | None) -> bool:
        return bool(
            document
            and type(document.get("accessExpiresAtMs")) is int
            and document["accessExpiresAtMs"] > int(self.clock().timestamp() * 1000)
            and not document.get("deleting")
            and not document.get("deleted")
        )

    def _projection(self, tx: Transaction, org: str, case_id: str) -> dict[str, Any]:
        identifier(case_id)
        parent = tx.get(f"receiverViews/{org}/cases/{case_id}")
        if not self._active(parent):
            raise IntakeError(404, "not_found")
        assert parent is not None
        packet_id = identifier(parent.get("latestPacketId"))
        if packet_id not in parent.get("packetIds", []):
            raise IntakeError(404, "not_found")
        projection = tx.get(f"receiverViews/{org}/cases/{case_id}/packets/{packet_id}")
        if not self._active(projection):
            raise IntakeError(404, "not_found")
        assert projection is not None
        packet = projection.get("packet", {})
        if packet.get("stale") or not packet.get("contentHash") or not packet.get("version"):
            raise IntakeError(409, "stale_link")
        if packet.get("status") not in {
            "SENT",
            "ACKNOWLEDGED",
            "NEEDS_INFO",
            "ACTIONED",
            "REJECTED",
        }:
            raise IntakeError(409, "stale_link")
        return projection

    def _current(
        self, tx: Transaction, record: dict[str, Any], link: dict[str, Any], org: str
    ) -> tuple[str, list[dict[str, Any]]]:
        projections = []
        for ref in link["case_refs"]:
            case = record["cases"].get(ref)
            if not case or org not in case["orgIds"]:
                raise IntakeError(404, "not_found")
            projection = self._projection(tx, org, case["caseId"])
            if projection.get("caseRef") != ref:
                raise IntakeError(409, "stale_link")
            projections.append(projection)
        proof = canonical_hash(
            [
                org,
                link,
                [
                    {
                        "caseRef": p["caseRef"],
                        "packetId": p["packet"]["packetId"],
                        "version": p["packet"]["version"],
                        "contentHash": p["packet"]["contentHash"],
                        "status": p["packet"]["status"],
                        "planId": p["packet"].get("planId"),
                        "factsRevision": p["packet"].get("factsRevision"),
                    }
                    for p in projections
                ],
            ]
        )
        return "lnk_" + proof[:40], projections

    def list(self, actor: Actor, case_id: str) -> dict[str, Any]:
        org = self._org(actor)

        def read(tx: Transaction) -> dict[str, Any]:
            anchor = self._projection(tx, org, case_id)
            ref = anchor["caseRef"]
            record = tx.get(INDEX) or {"cases": {}, "links": []}
            items = []
            for link in record.get("links", []):
                if ref not in link["case_refs"]:
                    continue
                try:
                    link_id, _ = self._current(tx, record, link, org)
                except IntakeError as error:
                    if error.status in {404, 409}:
                        continue
                    raise
                review = record.get("reviews", {}).get(org + ":" + link_id, {})
                items.append(
                    {
                        "linkId": link_id,
                        "caseRefs": link["case_refs"],
                        "sharedEntityTypes": link["shared_entity_types"],
                        "strength": link["strength"],
                        "explanation": {
                            "text": "A possible link shares confirmed identifier types "
                            "across these "
                            "reports within the recorded time window. This heuristic does not "
                            "identify a person or establish wrongdoing. A person must confirm.",
                            "confidenceBand": link["confidence_band"],
                            "evidencePointers": [
                                {"caseRef": r, "entityType": kind}
                                for r in link["case_refs"]
                                for kind in link["shared_entity_types"]
                            ],
                        },
                        "validation": {
                            "decision": review.get("decision"),
                            "by": review.get("by"),
                            "at": review.get("at"),
                        },
                    }
                )
            return {"items": items, "nextCursor": None}

        return self.repository.atomic(read)

    def validate(
        self, actor: Actor, link_id: str, decision: str, note: str | None, idempotency_key: str
    ) -> dict[str, Any]:
        org = self._org(actor)
        identifier(link_id)
        try:
            UUID(idempotency_key)
        except (ValueError, TypeError):
            raise IntakeError(422, "invalid_idempotency_key") from None
        if decision not in {"related", "not_related"} or (note and len(note) > 1000):
            raise IntakeError(422, "invalid_decision")
        if note and scrub_credentials(note) != note:
            raise IntakeError(422, "forbidden_secret")
        request_hash = canonical_hash([link_id, decision, note])
        key = canonical_hash([org, actor.uid, idempotency_key])

        def save(tx: Transaction) -> dict[str, Any]:
            record = tx.get(INDEX) or {"cases": {}, "links": []}
            # Validate both projections before replay; deleted/expired data never resurrects.
            matched = None
            for link in record.get("links", []):
                try:
                    current_id, _ = self._current(tx, record, link, org)
                except IntakeError:
                    continue
                if current_id == link_id:
                    matched = link
                    break
            if matched is None:
                raise IntakeError(409, "stale_link")
            requests = record.setdefault("reviewRequests", {})
            existing = requests.get(key)
            if existing:
                if existing["requestHash"] != request_hash:
                    raise IntakeError(409, "idempotency_conflict")
                return existing["result"]
            if len(requests) >= 300:
                raise IntakeError(409, "review_capacity_reached")
            now = self.clock().isoformat().replace("+00:00", "Z")
            result = {"linkId": link_id, "decision": decision}
            review = {
                "decision": decision,
                "by": actor.uid,
                "at": now,
                "orgId": org,
                "caseRefs": matched["case_refs"],
                "linkId": link_id,
                "noteHash": canonical_hash(note) if note else None,
                "requestHash": request_hash,
                "result": result,
            }
            record.setdefault("reviews", {})[org + ":" + link_id] = review
            requests[key] = review
            tx.set(INDEX, record)
            return result

        return self.repository.atomic(save)
