"""Guarded local M4 transport fixture. Synthetic model stages, never a provider."""

import argparse
import asyncio
import json
import os
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from agents.workflows.planning import PlanningWorkflow
from packages.common.identifiers import canonical_hash
from packages.delivery import MockDeliveryService
from packages.delivery.adapter import LocalMCPDeliveryAdapter
from packages.intake.repository import FirestoreRepository
from packages.intake.service import IntakeService, stamp
from packages.intake.storage import LocalFileBlobStore
from packages.packets.service import PacketService
from packages.packs.registry import PackRegistry
from packages.planning.service import PlanningService
from packages.receiver.service import ReceiverService
from packages.safety import Actor
from scripts.seed_m3_browser_fixture import ROOT, SyntheticClassifier, SyntheticPipeline, seed


def guard_environment() -> None:
    if (
        os.environ.get("FIRESTORE_EMULATOR_HOST") != "127.0.0.1:8095"
        or os.environ.get("GCP_PROJECT_ID") != "demo-relay-local"
        or os.environ.get("RELAY_WORKER_DISABLED") != "1"
    ):
        raise ValueError("Explicit demo emulator and paused worker required")


def fixture_case(case: dict | None) -> None:
    if (
        not case
        or case.get("classification", {}).get("authorizationRationale")
        != "Synthetic classifier fixture; no live model."
    ):
        raise ValueError("Not a marked synthetic fixture")
    if (
        case.get("facts", {}).get("victimBank") != "Fictional Test Bank"
        or case.get("facts", {}).get("contact", {}).get("identifier") != "synthetic-caller"
        or case.get("transcript")
        or case.get("evidenceIds")
    ):
        raise ValueError("Fixture identity or empty-evidence guard failed")
    age = datetime.now(UTC) - datetime.fromisoformat(case["createdAt"].replace("Z", "+00:00"))
    if not timedelta(0) <= age <= timedelta(minutes=30):
        raise ValueError("Fixture is not fresh")


def runtime():
    guard_environment()
    repository = FirestoreRepository(
        firestore.Client(project="demo-relay-local", credentials=AnonymousCredentials())
    )
    storage = LocalFileBlobStore(
        ROOT / ".local/intake/blobs",
        "http://127.0.0.1:8000",
        (ROOT / ".local/intake/intake-signing.key").read_bytes(),
    )
    intake = IntakeService(repository, storage, None, None)
    registry = PackRegistry(ROOT / "packs")
    intake.planning = PlanningService(
        intake, PlanningWorkflow(SyntheticClassifier(), registry, allow_draft_preview=True)
    )
    mock = MockDeliveryService(
        repository, registry, allow_draft_preview=True, environment="local", demo_mode=True
    )
    intake.packets = PacketService(intake, SyntheticPipeline(), LocalMCPDeliveryAdapter(mock))
    return intake


async def run(mode: str, case_id: str) -> dict:
    guard_environment()
    if not re.fullmatch(r"case_[A-Za-z0-9_-]{8,100}", case_id):
        raise ValueError("Invalid fixture case identifier")
    if mode == "seed":
        # Existing helper protects fresh empty, real anonymous-owned cases first.
        await seed(case_id)
    intake = runtime()
    repository = intake.repository
    case = repository.get(f"cases/{case_id}")
    fixture_case(case)
    actor = Actor(case["victimUid"], "victim")
    if mode == "seed":
        # Remove a fixture fact through the domain, then rebuild actual plan/packets.
        intake.update_facts(
            actor,
            case_id,
            {"ifRevision": case["factsRevision"], "facts": {"payment": {"transactionRef": None}}},
        )
        job = intake.planning.enqueue(actor, case_id, {"previewDraft": True})
        await intake.planning.process_case(job["jobId"])
        plan = intake.planning.get_plan(actor, case_id)
        job = intake.packets.generate(actor, case_id, {"planId": plan["planId"]}, str(uuid4()))
        await intake.packets.process(job["jobId"])
        items = intake.packets.list(actor, case_id)["items"]
        bank = next(item for item in items if item["recipientId"] == "bank")
        content = intake.packets.get(actor, case_id, bank["packetId"])["content"]
        reference = next(
            field for field in content["fields"] if field["key"] == "payment.transaction_ref"
        )
        if reference["value"] or bank["status"] != "VERIFIED":
            raise ValueError("Missing-reference synthetic fixture not established")
        return {
            "mode": "synthetic-classifier-writer-verifier",
            "providerCalls": 0,
            "bankPacketId": bank["packetId"],
            "planId": plan["planId"],
        }
    if mode == "prime-brief":
        primed = 0

        def prime(tx):
            nonlocal primed
            for packet_id in case.get("packetIds", []):
                public = tx.get(f"receiverViews/mock-bank/cases/{case_id}/packets/{packet_id}")
                path = f"receiverPrivate/mock-bank/cases/{case_id}/packets/{packet_id}"
                private = tx.get(path)
                if not public or not private:
                    continue
                # Public projection contains packet data; no full-case cache content.
                brief = ReceiverService._basic_brief(public)
                brief["riskSignals"] = [
                    {
                        "signal": "synthetic_fixture",
                        "detail": "Synthetic receiver brief fixture; no live model.",
                    }
                ]
                packet = public["packet"]
                private.update(
                    briefKey=canonical_hash(
                        {key: packet[key] for key in ("version", "contentHash", "status")}
                    ),
                    brief=brief,
                    briefStatus="generated",
                    briefRetryAfter=stamp(datetime.now(UTC) + timedelta(hours=1)),
                )
                tx.set(path, private)
                primed += 1

        repository.atomic(prime)
        if not primed:
            raise ValueError("No actually delivered fixture projection to prime")
        return {"providerCalls": 0, "primed": primed, "brief": "synthetic fixture plus cooldown"}
    if mode == "verify":
        processed = 0
        results = []
        for job_id in case.get("jobIds", []):
            job = repository.get(f"jobs/{job_id}")
            if job and job["type"] == "verify_packet" and job["state"] == "queued":
                await intake.packets.process(job_id)
                processed += 1
                completed = repository.get(f"jobs/{job_id}")
                packet = intake.packets.get(actor, case_id, job["packetId"])
                results.append(
                    {
                        "jobState": completed["state"],
                        "packetStatus": packet["status"],
                        "passed": packet["verification"]["passed"],
                        "errorCode": (completed.get("error") or {}).get("code"),
                    }
                )
        return {"providerCalls": 0, "processed": processed, "results": results}
    raise ValueError("Unknown fixture action")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["seed", "prime-brief", "verify"])
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.mode, args.case_id))))


if __name__ == "__main__":
    main()
