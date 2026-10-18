"""Repository-backed deterministic mocks. No institution calls or model decisions."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from packages.common.identifiers import canonical_hash
from packages.intake.repository import Repository, Transaction
from packages.packs.registry import PackRegistry

from .models import DeliveryError, DeliveryLookup, DeliveryProjection, DeliveryReceipt, HoldReceipt


class MockDeliveryService:
    def __init__(
        self,
        repository: Repository,
        registry: PackRegistry,
        *,
        allow_draft_preview: bool = False,
        environment: str = "production",
        demo_mode: bool = False,
        clock: Callable[[], datetime] | None = None,
        require_case_record: bool = True,
    ):
        self.repository, self.registry = repository, registry
        self.allow_draft_preview = allow_draft_preview
        self.environment, self.demo_mode = environment, demo_mode
        self.clock = clock or (lambda: datetime.now(UTC))
        self.require_case_record = require_case_record

    def _recipient(self, projection: DeliveryProjection):
        packs = self.registry.available(
            allow_draft_preview=self.allow_draft_preview,
            environment=self.environment,
            demo_mode=self.demo_mode,
        )
        pack = next(
            (
                p
                for p in packs
                if p.pack_id == projection.pack_id and p.version == projection.pack_version
            ),
            None,
        )
        if not pack:
            raise DeliveryError("pack_unavailable")
        recipient = next((r for r in pack.recipients if r.id == projection.recipient_id), None)
        if not recipient:
            raise DeliveryError("recipient_unavailable")
        return pack, recipient

    def _submit(self, projection: DeliveryProjection, key: str, *, rail: bool) -> DeliveryReceipt:
        if not key or len(key) > 200 or any(ord(char) < 32 for char in key):
            raise DeliveryError("invalid_idempotency_key")
        pack, recipient = self._recipient(projection)
        if recipient.type not in (
            {"national_cyber_authority"} if rail else {"bank", "payment_app"}
        ):
            raise DeliveryError("wrong_adapter")
        identity = {
            "owner": projection.owner_uid,
            "case": projection.case_id,
            "packet": projection.packet_id,
            "version": projection.packet_version,
            "recipient": projection.recipient_id,
            "key": key,
        }
        delivery_id = "delivery_" + canonical_hash(identity)
        path = f"mockDeliveries/{delivery_id}"
        request_hash = canonical_hash(projection.model_dump(mode="json"))
        missing = [
            name for name in recipient.required_fields if projection.fields.get(name) in (None, "")
        ]
        status: Literal["RECEIVED", "NEEDS_INFO", "ROUTED", "MISROUTED_SIMULATED"] = (
            "NEEDS_INFO" if missing else "RECEIVED"
        )
        if rail and not missing:
            expected = recipient.typology_categories.get(projection.typology)
            if expected is None:
                status = "NEEDS_INFO"
                missing.append("pack.typology_categories." + projection.typology)
            else:
                status = (
                    "MISROUTED_SIMULATED"
                    if (
                        projection.simulation.rail_mode == "misrouted"
                        or projection.category != expected
                    )
                    else "ROUTED"
                )
        ticket = (
            f"SIM-{pack.jurisdiction.code}-{int(canonical_hash(identity)[:12], 16) % 1_000_000:06d}"
        )
        receipt = DeliveryReceipt(
            delivery_id=delivery_id,
            adapter="mcp-rail-mock" if rail else "mcp-bank-mock",
            ticket_ref=ticket,
            status=status,
            sent_at=self.clock(),
            missing_items=missing,
            routed_to=[recipient.id] if status == "ROUTED" else [],
        )

        def write(tx: Transaction) -> DeliveryReceipt:
            if self.require_case_record:
                case = tx.get(f"cases/{projection.case_id}")
                if (
                    not case
                    or case.get("victimUid") != projection.owner_uid
                    or case.get("deleting")
                    or case.get("deleted")
                ):
                    raise DeliveryError("case_unavailable")
                try:
                    expires = datetime.fromisoformat(case["ttlAt"].replace("Z", "+00:00"))
                    if expires.tzinfo is None or expires <= self.clock():
                        raise ValueError("case expired")
                except (ValueError, KeyError, TypeError):
                    raise DeliveryError("case_unavailable") from None
            previous = tx.get(path)
            if previous:
                if previous["requestHash"] != request_hash:
                    raise DeliveryError("idempotency_conflict")
                return DeliveryReceipt.model_validate(previous["receipt"])
            # Keep hashes, routing, and receipt only; field values never enter
            # the mock ledger. The approved packet remains owned by the API.
            tx.set(
                path,
                {
                    "ownerUid": projection.owner_uid,
                    "caseId": projection.case_id,
                    "requestHash": request_hash,
                    "receipt": receipt.model_dump(mode="json", by_alias=True),
                    "bankMode": projection.simulation.bank_mode,
                    "minutesSincePayment": projection.simulation.minutes_since_payment,
                    "holds": {},
                },
            )
            return receipt

        return self.repository.atomic(write)

    async def submit_dispute(
        self, projection: DeliveryProjection, idempotency_key: str
    ) -> DeliveryReceipt:
        return self._submit(projection, idempotency_key, rail=False)

    async def file_report(
        self, projection: DeliveryProjection, idempotency_key: str
    ) -> DeliveryReceipt:
        return self._submit(projection, idempotency_key, rail=True)

    def get_status(
        self, owner_uid: str, case_id: str, delivery_id: str, *, adapter: str | None = None
    ) -> dict[str, Any]:
        DeliveryLookup(owner_uid=owner_uid, case_id=case_id, delivery_id=delivery_id)
        record = self.repository.get(f"mockDeliveries/{delivery_id}")
        if not record or record["ownerUid"] != owner_uid or record["caseId"] != case_id:
            raise DeliveryError("delivery_not_found")
        if adapter is not None and record["receipt"]["adapter"] != adapter:
            raise DeliveryError("wrong_adapter")
        return {**record["receipt"], "history": list(record["holds"].values())}

    async def place_hold(
        self, owner_uid: str, case_id: str, delivery_id: str, idempotency_key: str
    ) -> HoldReceipt:
        DeliveryLookup(owner_uid=owner_uid, case_id=case_id, delivery_id=delivery_id)
        if not idempotency_key or len(idempotency_key) > 200:
            raise DeliveryError("invalid_idempotency_key")
        key = canonical_hash(idempotency_key)

        def hold(tx: Transaction) -> HoldReceipt:
            record = tx.get(f"mockDeliveries/{delivery_id}")
            if not record or record["ownerUid"] != owner_uid or record["caseId"] != case_id:
                raise DeliveryError("delivery_not_found")
            if record["receipt"]["adapter"] != "mcp-bank-mock":
                raise DeliveryError("wrong_adapter")
            if key in record["holds"]:
                return HoldReceipt.model_validate(record["holds"][key])
            minutes, mode = record["minutesSincePayment"], record["bankMode"]
            status: Literal["HOLD_RECORDED", "FUNDS_ALREADY_MOVED", "REJECTED"] = "REJECTED"
            if record["receipt"]["status"] == "RECEIVED":
                if mode == "success" or (mode == "auto" and minutes is not None and minutes <= 90):
                    status = "HOLD_RECORDED"
                elif mode == "funds_moved" or (mode == "auto" and minutes is not None):
                    status = "FUNDS_ALREADY_MOVED"
            result = HoldReceipt(
                hold_ref=f"SIM-HOLD-{int(key[:12], 16) % 1_000_000:06d}",
                ticket_ref=record["receipt"]["ticketRef"],
                status=status,
            )
            if len(record["holds"]) >= 20:
                raise DeliveryError("hold_budget_exceeded")
            record["holds"][key] = result.model_dump(mode="json", by_alias=True)
            tx.set(f"mockDeliveries/{delivery_id}", record)
            return result

        return self.repository.atomic(hold)

    @staticmethod
    def cleanup_case(
        tx: Transaction, owner_uid: str, case_id: str, delivery_ids: list[str]
    ) -> None:
        for delivery_id in delivery_ids:
            path = f"mockDeliveries/{delivery_id}"
            record = tx.get(path)
            if record and record["ownerUid"] == owner_uid and record["caseId"] == case_id:
                tx.delete(path)
