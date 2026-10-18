"""Explicit one-case synthetic PDF transport fixture; zero provider calls.

All domain work stays private in a bounded memory transaction buffer. Only final
terminal records are committed to the fresh owner case in one Firestore transaction.
"""

import argparse
import asyncio
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from agents.workflows.planning import PlanningWorkflow
from packages.common.identifiers import canonical_hash
from packages.intake.repository import FirestoreRepository, MemoryRepository
from packages.intake.service import IntakeService
from packages.packets.service import PacketService
from packages.packs.registry import PackRegistry
from packages.planning.service import PlanningService
from packages.safety import Actor
from packages.schemas import CaseFacts
from scripts.seed_m3_browser_fixture import SyntheticClassifier, SyntheticPipeline

ROOT = Path(__file__).resolve().parents[1]


def environment_guard(project: str, *, apply: bool) -> None:
    if (
        project != "work-511514"
        or not apply
        or any(
            os.environ.get(name)
            for name in (
                "FIRESTORE_EMULATOR_HOST",
                "FIREBASE_AUTH_EMULATOR_HOST",
                "STORAGE_EMULATOR_HOST",
            )
        )
    ):
        raise ValueError("Explicit work-511514 --apply and no emulator environment required")


def fresh_case(case, case_id, owner_uid, now):
    if (
        not re.fullmatch(r"case_[a-f0-9]{32}", case_id)
        or not owner_uid
        or len(owner_uid) > 128
        or not case
        or case.get("caseId") != case_id
        or case.get("victimUid") != owner_uid
        or case.get("status") != "INTAKE"
        or case.get("factsRevision") != 0
        or case.get("deleted")
        or case.get("deleting")
        or case.get("syntheticPdfFixture")
        or case.get("facts") != CaseFacts().model_dump(mode="json", by_alias=True)
        or any(
            case.get(name)
            for name in (
                "transcript",
                "evidenceIds",
                "packetIds",
                "jobIds",
                "plan",
                "planningRequestIds",
                "classification",
                "approvalIds",
                "deliveryIds",
                "receiverProjectionRefs",
                "a2aTaskRefs",
                "pipelineIds",
                "messageRequestIds",
                "informationRequestIds",
                "liveSessionRefs",
                "liveResumeRefs",
            )
        )
    ):
        raise ValueError("Fixture requires the explicit owner of a fresh empty browser case")
    created = datetime.fromisoformat(case["createdAt"].replace("Z", "+00:00"))
    expiry = datetime.fromisoformat(case["ttlAt"].replace("Z", "+00:00"))
    if (
        not timedelta(0) <= now - created <= timedelta(minutes=10)
        or expiry <= now
        or type(case.get("accessExpiresAtMs")) is not int
        or case["accessExpiresAtMs"] <= int(now.timestamp() * 1000)
    ):
        raise ValueError("Fixture case must be fresh and unexpired")


class BoundedBuffer(MemoryRepository):
    def set(self, path, value):
        if path not in self.documents and len(self.documents) >= 200:
            raise ValueError("Synthetic fixture record bound exceeded")
        super().set(path, value)


class NoExternalEffects:
    def __getattr__(self, name):
        raise RuntimeError("PDF fixture cannot use storage, delivery or a provider")


class NoDelivery:
    async def deliver(self, *args, **kwargs):
        raise RuntimeError("PDF fixture cannot send or approve reports")


def catalog(registry):
    return canonical_hash(
        [
            pack.model_dump(mode="json")
            for pack in registry.available(
                allow_draft_preview=True, environment="local", demo_mode=True
            )
        ]
    )


async def prepare(initial, *, now, registry):
    buffer = BoundedBuffer()
    case_id, owner_uid = initial["caseId"], initial["victimUid"]
    fresh_case(initial, case_id, owner_uid, now)
    buffer.set("cases/" + case_id, initial)
    intake = IntakeService(buffer, NoExternalEffects(), None, None, clock=lambda: now)
    actor = Actor(owner_uid, "victim")
    intake.update_facts(
        actor,
        case_id,
        {
            "ifRevision": 0,
            "facts": {
                "country": {"value": "IN", "provenance": {"source": "confirmed"}},
                "payment": {
                    "method": "upi",
                    "amount": {"value": "45000", "currency": "INR"},
                    "timestamp": (now - timedelta(minutes=20)).isoformat(),
                    "authorizedByVictim": True,
                    "transactionRef": "TEST0000000001",
                    "recipientIdentifier": {"type": "upi_id", "value": "safe.verify@fakebank"},
                },
                "contact": {
                    "channel": "phone",
                    "identifier": "synthetic-caller",
                    "claimedIdentity": "bank",
                },
                "victimBank": "Fictional Test Bank",
                "ongoingContact": False,
            },
        },
    )
    proof = catalog(registry)
    planning = PlanningService(
        intake, PlanningWorkflow(SyntheticClassifier(), registry, allow_draft_preview=True)
    )
    intake.planning = planning
    job = planning.enqueue(actor, case_id, {"previewDraft": True})
    await planning.process_case(job["jobId"])
    packets = PacketService(intake, SyntheticPipeline(), NoDelivery())
    intake.packets = packets
    plan = planning.get_plan(actor, case_id)
    generated = packets.generate(actor, case_id, {"planId": plan["planId"]}, str(uuid4()))
    await packets.process(generated["jobId"])
    items = packets.list(actor, case_id)["items"]
    if len(items) != 3 or any(
        item["status"] != "VERIFIED" or item.get("delivery") for item in items
    ):
        raise ValueError("Synthetic fixture failed to create three unsent canonical reports")
    case = buffer.get("cases/" + case_id)
    if case is None:
        raise ValueError("Synthetic case disappeared")
    case["syntheticPdfFixture"] = {
        "mode": "synthetic-no-model-pdf-transport",
        "providerCalls": 0,
        "createdAt": now.isoformat(),
    }
    buffer.set("cases/" + case_id, case)
    if catalog(registry) != proof:
        raise ValueError("Source catalog changed during private fixture generation")
    return buffer.documents, proof


def commit(repository, initial, records, *, owner_uid, now, registry, proof):
    case_id = initial["caseId"]
    if not 1 <= len(records) <= 200 or catalog(registry) != proof:
        raise ValueError("Fixture source proof or record limit changed")
    final_case = records.get("cases/" + case_id)
    if (
        not final_case
        or final_case.get("victimUid") != owner_uid
        or final_case.get("syntheticPdfFixture", {}).get("providerCalls") != 0
        or final_case.get("syntheticPdfFixture", {}).get("mode")
        != "synthetic-no-model-pdf-transport"
        or len(final_case.get("packetIds", [])) != 3
        or any(
            final_case.get(key)
            for key in (
                "transcript",
                "evidenceIds",
                "approvalIds",
                "deliveryIds",
                "receiverProjectionRefs",
                "a2aTaskRefs",
            )
        )
    ):
        raise ValueError("Synthetic final fixture state is invalid or includes external actions")
    for path, value in records.items():
        if path.startswith("jobs/"):
            if (
                value.get("caseId") != case_id
                or value.get("uid") != owner_uid
                or value.get("state") != "succeeded"
                or value.get("type") not in {"process_case", "rebuild_packets"}
            ):
                raise ValueError("Only terminal synthetic planning/packet jobs may be committed")
        elif path.startswith("planningRequests/"):
            target_job = records.get("jobs/" + str(value.get("jobId")), {})
            if (
                value.get("caseId") != case_id
                or target_job.get("caseId") != case_id
                or target_job.get("uid") != owner_uid
                or target_job.get("state") != "succeeded"
            ):
                raise ValueError("Fixture planning request escaped its terminal owner job")
        elif path.startswith("idempotency/"):
            if value.get("uid") != owner_uid:
                raise ValueError("Fixture idempotency owner mismatch")
        elif path != "cases/" + case_id and not path.startswith("cases/" + case_id + "/"):
            raise ValueError("Fixture write escaped its explicit case")
        if any(
            part in path.split("/") for part in ("approvals", "receiverViews", "mockDeliveries")
        ):
            raise ValueError("Fixture cannot approve, deliver or create receiver state")

    def write(tx):
        current = tx.get("cases/" + case_id)
        fresh_case(current, case_id, owner_uid, now)
        if canonical_hash(current) != canonical_hash(initial) or catalog(registry) != proof:
            raise ValueError("Fresh owner case or source catalog changed; no fixture committed")
        for path in records:
            if path != "cases/" + case_id and tx.get(path) is not None:
                raise ValueError("Fixture record already exists")
        for path, value in records.items():
            tx.set(path, value)

    repository.atomic(write)
    return {
        "fixtureMode": "synthetic-no-model-pdf-transport",
        "providerCalls": 0,
        "packetIds": records["cases/" + case_id]["packetIds"],
        "terminalRecords": len(records),
        "catalogHash": proof,
    }


async def seed(repository, *, case_id, owner_uid, registry, now=None):
    current_time = now or datetime.now(UTC)
    initial = repository.get("cases/" + case_id)
    fresh_case(initial, case_id, owner_uid, current_time)
    records, proof = await prepare(initial, now=current_time, registry=registry)
    return commit(
        repository,
        initial,
        records,
        owner_uid=owner_uid,
        now=datetime.now(UTC) if now is None else now,
        registry=registry,
        proof=proof,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--owner-uid", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        environment_guard(args.project, apply=args.apply)
        from google.cloud import firestore

        client = firestore.Client(project=args.project)
        try:
            result = asyncio.run(
                seed(
                    FirestoreRepository(client),
                    case_id=args.case_id,
                    owner_uid=args.owner_uid,
                    registry=PackRegistry(ROOT / "packs"),
                )
            )
        finally:
            client.close()
        print(json.dumps(result))
    except Exception:
        parser.exit(1, "Synthetic PDF fixture refused or failed; no raw case data printed.\n")


if __name__ == "__main__":
    main()
