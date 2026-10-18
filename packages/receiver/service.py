"""Receiver operations never read full victim case documents.

Only the trusted approved-delivery transaction creates the projection. Victim
tracker mutations are delegated to an injected, separately owned bridge.
"""

import asyncio
import math
import re
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import Field, ValidationError

from packages.common.identifiers import canonical_hash, new_id
from packages.intake.repository import Repository, Transaction
from packages.intake.service import IntakeError, stamp
from packages.safety import Actor, SafetyGuard, scrub_credentials
from packages.safety.policy import Action, ActionPolicy, Context, Decision
from packages.schemas.models import Model, PacketContent, PacketStatus, ReceiverBrief

SAFE_ID = r"^[A-Za-z0-9_-]{1,128}$"
URGENCY = {"critical": 0, "high": 1, "normal": 2}
PUBLIC_PACKET_KEYS = (
    "packetId",
    "recipientId",
    "recipientName",
    "version",
    "status",
    "content",
    "verification",
    "delivery",
    "deadlines",
    "planId",
    "stale",
    "factsRevision",
    "contentHash",
)


class ReceiverDecision(Model):
    action: Literal["acknowledge", "request_info", "place_hold_simulated", "reject", "escalate"]
    packet_version: int = Field(ge=1, le=10000)
    reason: str | None = Field(default=None, max_length=2000)
    message: str | None = Field(default=None, max_length=2000)
    requested_items: list[str] = Field(default_factory=list, max_length=20)


def identifier(value: Any) -> str:
    if type(value) is not str or not re.fullmatch(SAFE_ID, value):
        raise IntakeError(422, "validation_failed")
    return value


class ReceiverService:
    def __init__(
        self,
        repository: Repository,
        *,
        recipient_orgs: dict[str, str],
        hold_adapter: Any = None,
        decision_bridge: Callable[..., Any] | None = None,
        brief_maker: Any = None,
        clock: Callable[[], datetime] | None = None,
    ):
        if not recipient_orgs:
            raise ValueError("Explicit recipient organization mapping required")
        self.recipient_orgs = {
            identifier(key): identifier(value) for key, value in recipient_orgs.items()
        }
        self.repository, self.hold_adapter = repository, hold_adapter
        self.decision_bridge, self.brief_maker = decision_bridge, brief_maker
        self.clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _org(actor: Actor) -> str:
        if actor.role != "receiver" or not actor.uid or not actor.org_id:
            raise IntakeError(403, "forbidden")
        return identifier(actor.org_id)

    def _active(self, value: dict[str, Any] | None) -> bool:
        return bool(
            value
            and type(value.get("accessExpiresAtMs")) is int
            and value["accessExpiresAtMs"] > int(self.clock().timestamp() * 1000)
            and not value.get("deleting")
            and not value.get("deleted")
        )

    @staticmethod
    def _paths(org: str, case_id: str, packet_id: str) -> tuple[str, str, str]:
        identifier(case_id)
        identifier(packet_id)
        return (
            f"receiverViews/{org}/cases/{case_id}/packets/{packet_id}",
            f"receiverPrivate/{org}/cases/{case_id}/packets/{packet_id}",
            f"receiverQueues/{org}/items/{case_id}_{packet_id}",
        )

    def project_delivery(
        self,
        tx: Transaction,
        *,
        owner_uid: str,
        case_id: str,
        case_ref: str,
        packet: dict[str, Any],
        plan: dict[str, Any],
        receipt: dict[str, Any],
        access_expires_at_ms: int,
        minutes_since_payment: int | None = None,
    ) -> dict[str, str]:
        recipient = packet["recipientId"]
        org = self.recipient_orgs.get(recipient)
        if not org or packet["status"] != "SENT" or receipt.get("simulated") is not True:
            raise IntakeError(422, "validation_failed")
        if not str(receipt.get("ticketRef", "")).startswith("SIM-"):
            raise IntakeError(422, "validation_failed")
        packet_id = identifier(packet["packetId"])
        public_path, private_path, queue_path = self._paths(org, case_id, packet_id)
        previous = tx.get(public_path)
        if previous and previous["packet"]["version"] > packet["version"]:
            raise IntakeError(409, "version_conflict")
        if previous and previous["packet"]["version"] == packet["version"]:
            if previous["packet"]["contentHash"] != packet["contentHash"]:
                raise IntakeError(409, "version_conflict")
            return {"orgId": org, "packetId": packet_id, "queueId": queue_path.rsplit("/", 1)[1]}
        content = PacketContent.model_validate(packet["content"])
        classification = plan["classification"]
        urgency = classification["urgency"]["level"]
        if urgency not in URGENCY:
            raise IntakeError(422, "validation_failed")
        projected_packet = {key: deepcopy(packet[key]) for key in PUBLIC_PACKET_KEYS}
        # URLs/attachments are not automatically shared with recipient staff.
        projected_packet["content"]["attachments"] = []
        now = stamp(self.clock())
        projection = {
            "caseRef": case_ref,
            "jurisdiction": plan.get("countryCode") or "UNKNOWN",
            "urgency": urgency,
            "typology": classification["typology"],
            "authorizationType": classification["authorizationType"],
            "minutesSincePayment": minutes_since_payment,
            "keyFacts": [
                {
                    "key": item.key,
                    "label": item.label,
                    "value": item.value,
                    "provenance": item.provenance.source,
                }
                for item in content.fields
                if item.value
            ],
            "packet": projected_packet,
            "evidence": [],
            "timeline": [],
            "links": [],
            "accessExpiresAtMs": access_expires_at_ms,
            "updatedAt": now,
            "createdAt": now,
        }
        private = tx.get(private_path) or {"decisionIds": [], "requestIds": []}
        private.update(
            ownerUid=owner_uid,
            deliveryId=receipt["deliveryId"],
            accessExpiresAtMs=access_expires_at_ms,
        )
        queue = {
            "caseId": case_id,
            "packetId": packet_id,
            "caseRef": case_ref,
            "recipientName": packet["recipientName"],
            "urgency": urgency,
            "urgencyRank": URGENCY[urgency],
            "typology": classification["typology"],
            "status": "SENT",
            "updatedAt": now,
            "createdAt": previous["createdAt"] if previous else now,
            "accessExpiresAtMs": access_expires_at_ms,
        }
        tx.set(public_path, projection)
        tx.set(private_path, private)
        tx.set(queue_path, queue)
        parent_path = f"receiverViews/{org}/cases/{case_id}"
        parent = tx.get(parent_path) or {"caseRef": case_ref, "packetIds": []}
        if packet_id not in parent["packetIds"]:
            parent["packetIds"].append(packet_id)
        parent.update(latestPacketId=packet_id, accessExpiresAtMs=access_expires_at_ms)
        tx.set(parent_path, parent)
        return {"orgId": org, "packetId": packet_id, "queueId": queue_path.rsplit("/", 1)[1]}

    def queue(
        self,
        actor: Actor,
        *,
        status: str | None = None,
        urgency: str | None = None,
        typology: str | None = None,
        limit: int = 25,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        org = self._org(actor)
        if status and status not in {item.value for item in PacketStatus}:
            raise IntakeError(422, "validation_failed")
        if urgency and urgency not in URGENCY:
            raise IntakeError(422, "validation_failed")
        if typology is not None and (not re.fullmatch(r"[a-z_]{1,80}", typology)):
            raise IntakeError(422, "validation_failed")
        limit = max(1, min(limit, 100))
        prefix = f"receiverQueues/{org}/items/"
        filters = {
            key: value
            for key, value in (("status", status), ("urgency", urgency), ("typology", typology))
            if value
        }
        client = getattr(self.repository, "client", None)
        if client is None:
            rows = [
                deepcopy(value) | {"_id": path[len(prefix) :]}
                for path, value in self.repository.documents.items()  # type: ignore[attr-defined]
                if path.startswith(prefix) and all(value.get(k) == v for k, v in filters.items())
            ]
            rows.sort(key=lambda item: (item["urgencyRank"], item["createdAt"], item["_id"]))
            if cursor:
                index = next((i for i, item in enumerate(rows) if item["_id"] == cursor), None)
                if index is None:
                    raise IntakeError(400, "bad_request")
                rows = rows[index + 1 :]
            rows = rows[: limit + 1]
        else:
            query = client.collection(prefix.rstrip("/"))
            for key, value in filters.items():
                query = query.where(filter=FieldFilter(key, "==", value))
            query = query.order_by("urgencyRank").order_by("createdAt").order_by("__name__")
            if cursor:
                identifier(cursor)
                snapshot = client.document(prefix + cursor).get()
                if not snapshot.exists:
                    raise IntakeError(400, "bad_request")
                query = query.start_after(snapshot)
            rows = [
                snapshot.to_dict() | {"_id": snapshot.id}
                for snapshot in query.limit(limit + 1).stream()
            ]
        page = rows[:limit]
        keys = (
            "caseId",
            "caseRef",
            "packetId",
            "recipientName",
            "urgency",
            "typology",
            "status",
            "updatedAt",
        )
        return {
            "items": [{key: item[key] for key in keys} for item in page if self._active(item)],
            "nextCursor": page[-1]["_id"] if len(rows) > limit else None,
        }

    def _load(self, tx: Any, actor: Actor, case_id: str, packet_id: str | None = None):
        org = self._org(actor)
        identifier(case_id)
        parent = tx.get(f"receiverViews/{org}/cases/{case_id}")
        if not self._active(parent):
            raise IntakeError(404, "not_found")
        packet_id = packet_id or parent["latestPacketId"]
        if packet_id not in parent["packetIds"]:
            raise IntakeError(404, "not_found")
        public_path, private_path, queue_path = self._paths(org, case_id, packet_id)
        projected = tx.get(public_path)
        if not self._active(projected):
            raise IntakeError(404, "not_found")
        return projected, public_path, private_path, queue_path

    @staticmethod
    def _basic_brief(projected: dict[str, Any]) -> dict[str, Any]:
        content = projected["packet"]["content"]
        missing = [
            {"key": item["key"], "label": item["label"]}
            for item in content["fields"]
            if item["required"] and (not item["value"] or item["availability"] != "available")
        ]
        required = [item for item in content["fields"] if item["required"]]
        score = (len(required) - len(missing)) / len(required) if required else 1.0
        supplied = content.get("completeness", {}).get("score")
        if type(supplied) in {int, float} and math.isfinite(supplied) and 0 <= supplied <= 1:
            score = supplied
        return {
            "completenessScore": score,
            "missingItems": missing,
            "keyFacts": projected["keyFacts"][:5],
            "riskSignals": [
                {
                    "signal": "deterministic_summary",
                    "detail": "No AI brief is available; inspect the submitted message.",
                }
            ],
            "suggestedActions": [
                {
                    "action": "request_info" if missing else "acknowledge",
                    "why": "Human review is required; this is a deterministic suggestion.",
                }
            ],
            "draftReplyToVictim": {"lang": content["language"], "text": ""},
        }

    async def get_case(
        self, actor: Actor, case_id: str, packet_id: str | None = None
    ) -> dict[str, Any]:
        projected, _, _, _ = self._load(self.repository, actor, case_id, packet_id)
        keys = (
            "caseRef",
            "jurisdiction",
            "urgency",
            "typology",
            "authorizationType",
            "minutesSincePayment",
            "keyFacts",
            "packet",
            "evidence",
            "timeline",
            "links",
        )
        result = {key: deepcopy(projected[key]) for key in keys}
        result["brief"] = self._basic_brief(projected)
        result["briefStatus"] = "unavailable"
        brief_key = canonical_hash(
            {key: projected["packet"][key] for key in ("version", "contentHash", "status")}
        )
        claim_token = new_id("brief")

        def reserve_brief(tx: Transaction):
            latest, _, path, _ = self._load(tx, actor, case_id, result["packet"]["packetId"])
            ledger = tx.get(path)
            if ledger is None or not self._active(ledger):
                raise IntakeError(404, "not_found")
            key = canonical_hash(
                {field: latest["packet"][field] for field in ("version", "contentHash", "status")}
            )
            if key != brief_key:
                raise IntakeError(409, "version_conflict")
            if ledger.get("briefKey") == key and ledger.get("briefStatus") == "generated":
                return ReceiverBrief.model_validate(ledger["brief"]).model_dump(
                    mode="json", by_alias=True
                )
            if any(
                ledger.get(field, "") > stamp(self.clock())
                for field in ("briefLeaseUntil", "briefRetryAfter")
            ):
                return False
            ledger.update(
                briefClaimToken=claim_token,
                briefLeaseUntil=stamp(self.clock() + timedelta(seconds=30)),
            )
            tx.set(path, ledger)
            return True

        if self.brief_maker is not None:
            reservation = self.repository.atomic(reserve_brief)
            try:
                if reservation is False:
                    return result
                if isinstance(reservation, dict):
                    result["brief"] = reservation
                    result["briefStatus"] = "generated"
                    return result
                brief_input = {
                    key: value
                    for key, value in result.items()
                    if key not in {"brief", "briefStatus"}
                }
                brief = await asyncio.wait_for(self.brief_maker(deepcopy(brief_input)), timeout=22)
                parsed = ReceiverBrief.model_validate(brief)
                if parsed.completeness_score != result["brief"]["completenessScore"]:
                    raise ValueError("brief completeness mismatch")
                rendered = parsed.model_dump(mode="json", by_alias=True)
                if not SafetyGuard().inspect_output(str(rendered)).allow:
                    raise ValueError("unsafe brief")
                result["brief"] = rendered
                result["briefStatus"] = "generated"
            except Exception:
                result["brief"]["riskSignals"].append(
                    {
                        "signal": "brief_unavailable",
                        "detail": "AI summary unavailable; review the submitted message.",
                    }
                )

            def save_brief(tx: Transaction):
                current, _, path, _ = self._load(tx, actor, case_id, result["packet"]["packetId"])
                ledger = tx.get(path)
                if ledger is None or not self._active(ledger):
                    raise IntakeError(404, "not_found")
                key = canonical_hash(
                    {
                        field: current["packet"][field]
                        for field in ("version", "contentHash", "status")
                    }
                )
                if key != brief_key or ledger.get("briefClaimToken") != claim_token:
                    raise IntakeError(409, "version_conflict")
                ledger.update(
                    briefLeaseUntil="",
                    briefRetryAfter=stamp(self.clock() + timedelta(minutes=2))
                    if result["briefStatus"] == "unavailable"
                    else "",
                )
                if result["briefStatus"] == "generated":
                    ledger.update(
                        briefKey=brief_key, brief=result["brief"], briefStatus="generated"
                    )
                else:
                    for field in ("briefKey", "brief", "briefStatus"):
                        ledger.pop(field, None)
                tx.set(path, ledger)

            self.repository.atomic(save_brief)
        latest, _, _, _ = self._load(self.repository, actor, case_id, result["packet"]["packetId"])
        if (latest["packet"]["version"], latest["packet"]["contentHash"]) != (
            result["packet"]["version"],
            result["packet"]["contentHash"],
        ):
            raise IntakeError(409, "version_conflict")
        return result

    def _apply(
        self,
        tx: Transaction,
        actor: Actor,
        case_id: str,
        projected: dict[str, Any],
        private: dict[str, Any],
        decision_path: str,
        decision: dict[str, Any],
        paths: tuple[str, str, str],
        adapter_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        public_path, private_path, queue_path = paths
        action = decision["action"]
        status = projected["packet"]["status"]
        if action == "acknowledge":
            status = "ACKNOWLEDGED"
        elif action == "request_info":
            status = "NEEDS_INFO"
            request_id = decision.setdefault("requestId", new_id("request"))
            if request_id not in private["requestIds"]:
                private["requestIds"].append(request_id)
            tx.set(
                f"receiverPrivate/{actor.org_id}/cases/{case_id}/requests/{request_id}",
                {
                    "requestId": request_id,
                    "packetId": projected["packet"]["packetId"],
                    "packetVersion": decision["packetVersion"],
                    "requestedItems": decision["requestedItems"],
                    "message": decision.get("message") or "",
                    "status": "open",
                    "createdAt": stamp(self.clock()),
                    "simulated": True,
                },
            )
        elif action == "reject":
            status = "REJECTED"
        elif (
            action == "place_hold_simulated"
            and adapter_result
            and adapter_result["status"] != "REJECTED"
        ):
            status = "ACTIONED"
        event_id = new_id("event")
        event = {
            "eventId": event_id,
            "ts": stamp(self.clock()),
            "actorType": "receiver",
            "actorId": actor.uid,
            "action": "receiver." + action,
            "targetType": "packet",
            "targetId": projected["packet"]["packetId"],
            "payloadHash": canonical_hash(decision),
            "traceId": decision["decisionId"],
            "details": {
                "packetVersion": str(decision["packetVersion"]),
                "simulated": "true",
                "reason": decision.get("reason") or "",
            },
        }
        if len(projected["timeline"]) >= 40:
            raise IntakeError(429, "budget_exceeded")
        projected["timeline"].append(event)
        projected["packet"]["status"] = status
        projected["updatedAt"] = stamp(self.clock())
        queue = tx.get(queue_path)
        if queue is None:
            raise IntakeError(404, "not_found")
        queue.update(status=status, updatedAt=projected["updatedAt"])
        result: dict[str, Any] = {"packetId": projected["packet"]["packetId"], "status": status}
        if adapter_result:
            result["adapterResult"] = adapter_result
        decision.update(state="done", result=result, leaseUntil=None)
        tx.set(public_path, projected)
        tx.set(private_path, private)
        tx.set(queue_path, queue)
        tx.set(decision_path, decision)
        if self.decision_bridge:
            self.decision_bridge(
                tx,
                {
                    "actor": actor,
                    "caseId": case_id,
                    "packetId": projected["packet"]["packetId"],
                    "packetVersion": decision["packetVersion"],
                    "contentHash": projected["packet"]["contentHash"],
                    "orgId": actor.org_id,
                    "status": status,
                    "action": action,
                    "decisionId": decision["decisionId"],
                    "requestedItems": decision["requestedItems"],
                    "message": decision.get("message"),
                    "reason": decision.get("reason"),
                    "event": event,
                    "adapterResult": adapter_result,
                    "requestId": decision.get("requestId"),
                },
            )
        return result

    async def decide(
        self,
        actor: Actor,
        case_id: str,
        packet_id: str,
        body: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        org = self._org(actor)
        try:
            data = ReceiverDecision.model_validate(body).model_dump(mode="json", by_alias=True)
        except ValidationError:
            raise IntakeError(422, "validation_failed") from None
        action = data["action"]
        if action in {"reject", "escalate"} and not (data["reason"] or "").strip():
            raise IntakeError(422, "validation_failed", "A reason is required.")
        for value in (data["reason"], data["message"]):
            if value and (
                scrub_credentials(value) != value or not SafetyGuard().inspect_output(value).allow
            ):
                raise IntakeError(422, "unsafe_content_blocked")
        request_items = data["requestedItems"]
        if len(set(request_items)) != len(request_items) or any(
            not re.fullmatch(r"[a-zA-Z0-9_.-]{1,120}", key) for key in request_items
        ):
            raise IntakeError(422, "validation_failed")
        request_hash = canonical_hash(data)
        if idempotency_key is not None:
            from uuid import UUID

            try:
                idempotency_key = str(UUID(idempotency_key))
            except (ValueError, TypeError, AttributeError):
                raise IntakeError(422, "validation_failed") from None
        decision_id = "decision_" + canonical_hash(
            {
                "org": org,
                "actor": actor.uid,
                "case": case_id,
                "packet": packet_id,
                "key": idempotency_key or request_hash,
            }
        )
        decision_path = f"receiverPrivate/{org}/cases/{identifier(case_id)}/decisions/{decision_id}"

        def reserve(tx: Transaction):
            projected, public_path, private_path, queue_path = self._load(
                tx, actor, case_id, packet_id
            )
            private = tx.get(private_path)
            if (
                private is None
                or not self._active(private)
                or projected["packet"]["version"] != data["packetVersion"]
            ):
                raise IntakeError(409, "version_conflict")
            previous = tx.get(decision_path)
            if (
                previous
                and previous.get(
                    "requestHash", canonical_hash({key: previous.get(key) for key in data})
                )
                != request_hash
            ):
                raise IntakeError(409, "idempotency_conflict")
            if previous and previous["contentHash"] != projected["packet"]["contentHash"]:
                raise IntakeError(409, "version_conflict")
            if previous and previous["state"] == "done":
                return previous["result"], None
            status = projected["packet"]["status"]
            if status in {"DRAFT", "NEEDS_HUMAN_REVIEW", "VERIFIED", "REJECTED", "CLOSED"}:
                raise IntakeError(409, "invalid_state_transition")
            if action == "request_info":
                missing = {
                    item["key"]
                    for item in projected["packet"]["content"]["fields"]
                    if not item.get("value") and item.get("availability") != "not_available"
                }
                if not request_items or not set(request_items).issubset(missing):
                    raise IntakeError(
                        422,
                        "validation_failed",
                        "Choose missing fields from the submitted message.",
                    )
            elif request_items:
                raise IntakeError(422, "validation_failed")
            if action == "place_hold_simulated":
                if self.hold_adapter is None or projected["packet"]["recipientId"] != "bank":
                    raise IntakeError(
                        409,
                        "invalid_state_transition",
                        "No simulated bank hold adapter is available.",
                    )
                context = Context(
                    packet_id,
                    data["packetVersion"],
                    projected["packet"]["contentHash"],
                    recipient_org_id=org,
                    recipient_id="bank",
                    simulated=True,
                )
                if ActionPolicy.check(actor, Action.HOLD, context) != Decision.REQUIRE_APPROVAL:
                    raise IntakeError(403, "forbidden")
                if (
                    previous
                    and previous.get("leaseUntil")
                    and previous["leaseUntil"] > stamp(self.clock())
                ):
                    raise IntakeError(503, "adapter_unavailable")
                if previous and previous.get("attempts", 0) >= 3:
                    raise IntakeError(409, "budget_exceeded")
            validator = getattr(self.decision_bridge, "validate", None)
            if validator is not None:
                validator(
                    tx,
                    {
                        "actor": actor,
                        "caseId": case_id,
                        "packetId": packet_id,
                        "packetVersion": data["packetVersion"],
                        "contentHash": projected["packet"]["contentHash"],
                        "orgId": org,
                    },
                )
            if not previous and len(private["decisionIds"]) >= 20:
                raise IntakeError(429, "budget_exceeded")
            decision = previous or {
                **data,
                "decisionId": decision_id,
                "requestHash": request_hash,
                "actorUid": actor.uid,
                "orgId": org,
                "approvedAt": stamp(self.clock()),
                "contentHash": projected["packet"]["contentHash"],
                "state": "pending",
                "attempts": 0,
            }
            if decision_id not in private["decisionIds"]:
                private["decisionIds"].append(decision_id)
            if action != "place_hold_simulated":
                return self._apply(
                    tx,
                    actor,
                    case_id,
                    projected,
                    private,
                    decision_path,
                    decision,
                    (public_path, private_path, queue_path),
                ), None
            decision.update(
                attempts=decision["attempts"] + 1,
                claimToken=new_id("claim"),
                leaseUntil=stamp(self.clock() + timedelta(seconds=20)),
            )
            tx.set(decision_path, decision)
            tx.set(private_path, private)
            return None, {"decision": decision, "private": private}

        completed, pending = self.repository.atomic(reserve)
        if completed is not None:
            return completed
        try:
            private = pending["private"]
            receipt = await asyncio.wait_for(
                self.hold_adapter(private["ownerUid"], case_id, private["deliveryId"], decision_id),
                timeout=10,
            )
            result = (
                receipt.model_dump(mode="json", by_alias=True)
                if hasattr(receipt, "model_dump")
                else receipt
            )
            if result.get("simulated") is not True or not str(result.get("holdRef", "")).startswith(
                "SIM-HOLD-"
            ):
                raise ValueError("invalid simulated hold result")
            text = {
                "HOLD_RECORDED": "Simulated hold recorded. No real money is held.",
                "FUNDS_ALREADY_MOVED": (
                    "Simulation: funds have already moved. No real funds were checked."
                ),
                "REJECTED": "Simulated hold rejected. No real money is held.",
            }[result["status"]]
            adapter_result = {
                "ref": result["holdRef"],
                "status": result["status"],
                "simulated": True,
                "text": text,
            }
        except Exception:
            raise IntakeError(503, "adapter_unavailable") from None

        def finish(tx: Transaction):
            projected, public_path, private_path, queue_path = self._load(
                tx, actor, case_id, packet_id
            )
            record = tx.get(decision_path)
            private = tx.get(private_path)
            if (
                private is None
                or not record
                or record.get("claimToken") != pending["decision"]["claimToken"]
            ):
                raise IntakeError(409, "version_conflict")
            if (
                projected["packet"]["version"] != data["packetVersion"]
                or projected["packet"]["contentHash"] != record["contentHash"]
            ):
                raise IntakeError(409, "version_conflict")
            return self._apply(
                tx,
                actor,
                case_id,
                projected,
                private,
                decision_path,
                record,
                (public_path, private_path, queue_path),
                adapter_result,
            )

        return self.repository.atomic(finish)

    def cleanup_case(
        self, tx: Transaction, case_id: str, projection_refs: list[dict[str, str]]
    ) -> None:
        organizations = set()
        for ref in projection_refs:
            org, packet_id = identifier(ref["orgId"]), identifier(ref["packetId"])
            public_path, private_path, queue_path = self._paths(org, case_id, packet_id)
            private = tx.get(private_path)
            if private:
                for decision_id in private["decisionIds"]:
                    tx.delete(f"receiverPrivate/{org}/cases/{case_id}/decisions/{decision_id}")
                for request_id in private["requestIds"]:
                    tx.delete(f"receiverPrivate/{org}/cases/{case_id}/requests/{request_id}")
            tx.delete(public_path)
            tx.delete(private_path)
            tx.delete(queue_path)
            organizations.add(org)
        for org in organizations:
            tx.delete(f"receiverViews/{org}/cases/{case_id}")
