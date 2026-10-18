"""Test-only emulator fixture through real domain services; never calls a provider.

Requires root to run the local API without its background worker while this helper
queues and processes jobs. It cannot publish packs, approve or deliver any message.
"""

import argparse
import asyncio
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from agents.packets import PacketBuildResult
from agents.packets.core import _metadata
from agents.workflows.planning import PlanningWorkflow
from packages.delivery import MockDeliveryService
from packages.delivery.adapter import LocalMCPDeliveryAdapter
from packages.intake.repository import FirestoreRepository
from packages.intake.service import IntakeService
from packages.intake.storage import LocalFileBlobStore
from packages.packets.service import PacketService
from packages.packs.registry import PackRegistry
from packages.planning.service import PlanningService
from packages.safety import Actor
from packages.schemas.models import Classification, PacketContent, Urgency, VerificationCheck

ROOT = Path(__file__).resolve().parents[1]


class SyntheticClassifier:
    async def classify(self, **kwargs: Any) -> Classification:
        return Classification(
            typology="bank_impersonation",
            authorization_type="authorized_manipulated",
            authorization_rationale="Synthetic classifier fixture; no live model.",
            urgency=Urgency(level="critical", reason="Synthetic fixture timing; not law."),
            confidence=0.95,
        )


class SyntheticPipeline:
    """Canonical metadata and explicitly labeled synthetic writer/verifier outputs."""

    def __init__(self) -> None:
        self.verifier = self

    async def verify(self, content: PacketContent, **context: Any) -> list[VerificationCheck]:
        return [
            VerificationCheck(
                id="fixture_verifier",
                type="deterministic",
                passed=True,
                detail="Fixture verifier - no live model",
                severity="blocker",
            )
        ]

    async def build(self, **context: Any) -> PacketBuildResult:
        metadata = _metadata(
            context["facts"],
            context["recipient"],
            context["pack"],
            context["plan_step"],
            context["source_passages"],
            context.get("attachments", []),
            context.get("available_provenance"),
            context.get("confirmed_fields"),
        )
        content = PacketContent(
            language="en",
            recipient_language=context.get("recipient_language", "en"),
            subject="Synthetic fixture report for review",
            summary="Fictional UPI payment of INR 45000 after a phone impersonation.",
            message="Please record this synthetic demonstration report about a victim-approved "
            "UPI payment of INR 45000 and provide a reference. No recovery is promised.",
            requested_actions=["Record this synthetic report"],
            victim_copy={
                "summary": "Synthetic writer fixture; no live model.",
                "message": "This fictional report asks the recipient to record your "
                "payment details. No real institution receives it.",
            },
            **metadata,
        )
        return PacketBuildResult(
            content=content,
            checks=await self.verify(content),
            attempts=1,
            status="VERIFIED",
            model="synthetic-fixture-no-provider",
        )


async def seed(case_id: str) -> dict[str, Any]:
    if (
        os.environ.get("FIRESTORE_EMULATOR_HOST") != "127.0.0.1:8095"
        or os.environ.get("GCP_PROJECT_ID") != "demo-relay-local"
    ):
        raise ValueError("Only the explicit loopback demo Firestore emulator is allowed")
    if not re.fullmatch(r"case_[A-Za-z0-9_-]{8,100}", case_id):
        raise ValueError("Expected a newly created synthetic case ID")
    client = firestore.Client(project="demo-relay-local", credentials=AnonymousCredentials())
    repository = FirestoreRepository(client)
    case = repository.get(f"cases/{case_id}")
    now = datetime.now(UTC)
    if (
        not case
        or case.get("status") != "INTAKE"
        or case.get("factsRevision") != 0
        or any(
            case.get(key) for key in ["transcript", "evidenceIds", "packetIds", "jobIds", "plan"]
        )
    ):
        raise ValueError("Fixture requires a new empty intake case; existing work is protected")
    created = datetime.fromisoformat(case["createdAt"].replace("Z", "+00:00"))
    if not timedelta(0) <= now - created <= timedelta(minutes=15) or not case.get("victimUid"):
        raise ValueError("Fixture requires a fresh anonymous-owned case")
    key = (ROOT / ".local/intake/intake-signing.key").read_bytes()
    if len(key) != 32:
        raise ValueError("Existing local runtime signing key is required")
    storage = LocalFileBlobStore(ROOT / ".local/intake/blobs", "http://127.0.0.1:8000", key)
    intake = IntakeService(repository, storage, None, None)
    actor = Actor(case["victimUid"], "victim")
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
    registry = PackRegistry(ROOT / "packs")
    planning = PlanningService(
        intake, PlanningWorkflow(SyntheticClassifier(), registry, allow_draft_preview=True)
    )
    intake.planning = planning
    planning_job = planning.enqueue(actor, case_id, {"previewDraft": True})
    await planning.process_case(planning_job["jobId"])
    completed_plan = repository.get(f"jobs/{planning_job['jobId']}")
    if completed_plan is None or completed_plan["state"] != "succeeded":
        raise ValueError("Synthetic planning fixture did not finish")
    mock = MockDeliveryService(
        repository, registry, allow_draft_preview=True, environment="local", demo_mode=True
    )
    packets = PacketService(intake, SyntheticPipeline(), LocalMCPDeliveryAdapter(mock))
    intake.packets = packets
    plan = planning.get_plan(actor, case_id)
    packet_job = packets.generate(actor, case_id, {"planId": plan["planId"]}, str(uuid4()))
    await packets.process(packet_job["jobId"])
    items = packets.list(actor, case_id)["items"]
    if len(items) != 3 or any(
        item["status"] != "VERIFIED" or item.get("delivery") for item in items
    ):
        raise ValueError("Synthetic packet fixture did not produce three unsent checked messages")
    return {
        "fixtureMode": "real-domain-transport-synthetic-classifier-writer-verifier",
        "providerCalls": 0,
        "packetIds": [item["packetId"] for item in items],
    }


def cleanup_aborted(receipt_reference: str) -> dict[str, Any]:
    """Delete only the recorded aborted fixture through the actual domain cascade."""
    if (
        os.environ.get("FIRESTORE_EMULATOR_HOST") != "127.0.0.1:8095"
        or os.environ.get("GCP_PROJECT_ID") != "demo-relay-local"
    ):
        raise ValueError("Only the explicit loopback demo Firestore emulator is allowed")
    if receipt_reference != "SIM-IN-012817":
        raise ValueError("Only the recorded clipboard-aborted receipt is eligible")
    client = firestore.Client(project="demo-relay-local", credentials=AnonymousCredentials())
    repository = FirestoreRepository(client)
    matches = list(
        client.collection("mockDeliveries")
        .where(filter=FieldFilter("receipt.ticketRef", "==", receipt_reference))
        .limit(2)
        .stream()
    )
    if len(matches) != 1:
        raise ValueError("Expected exactly one recorded aborted fixture receipt")
    record = matches[0].to_dict()
    if record is None or record.get("receipt", {}).get("simulated") is not True:
        raise ValueError("Expected an actual simulated receipt record")
    case_id = record["caseId"]
    case = repository.get(f"cases/{case_id}")
    if (
        not case
        or case["victimUid"] != record["ownerUid"]
        or case.get("transcript")
        or case.get("evidenceIds")
    ):
        raise ValueError("Fixture owner/empty-evidence guard failed")
    if (
        case.get("classification", {}).get("authorizationRationale")
        != "Synthetic classifier fixture; no live model."
        or case["facts"].get("contact", {}).get("identifier") != "synthetic-caller"
        or case["facts"].get("victimBank") != "Fictional Test Bank"
    ):
        raise ValueError("Exact synthetic fixture markers are required")
    packets = [
        repository.get(f"cases/{case_id}/packets/{packet_id}")
        for packet_id in case.get("packetIds", [])
    ]
    if len(packets) != 3 or any(
        not packet
        or not packet["verification"]["checks"]
        or any(
            check.get("id") != "fixture_verifier"
            or check.get("detail") != "Fixture verifier - no live model"
            for check in packet["verification"]["checks"]
        )
        for packet in packets
    ):
        raise ValueError("Every packet must carry the exact synthetic verifier marker")
    key = (ROOT / ".local/intake/intake-signing.key").read_bytes()
    intake = IntakeService(
        repository,
        LocalFileBlobStore(ROOT / ".local/intake/blobs", "http://127.0.0.1:8000", key),
        None,
        None,
    )
    registry = PackRegistry(ROOT / "packs")
    mock = MockDeliveryService(
        repository, registry, allow_draft_preview=True, environment="local", demo_mode=True
    )
    intake.packets = PacketService(intake, SyntheticPipeline(), LocalMCPDeliveryAdapter(mock))
    artifact = {
        "mode": "aborted-real-transport-synthetic-model-stages",
        "receipt": record["receipt"],
        "failure": "headless clipboard permission absent",
        "providerCalls": 0,
    }
    (ROOT / ".tmp/ui-review/m3-aborted-clipboard-receipt.json").write_text(
        json.dumps(artifact, indent=2), encoding="utf-8"
    )
    job_ids = case.get("jobIds", [])
    intake.delete_case(Actor(case["victimUid"], "victim"), case_id)
    if (
        repository.get(f"cases/{case_id}") is not None
        or repository.get(matches[0].reference.path) is not None
        or any(repository.get(f"jobs/{job_id}") for job_id in job_ids)
    ):
        raise ValueError("Domain deletion did not remove the exact fixture cascade")
    pending_fixture_jobs = 0
    for snapshot in (
        client.collection("jobs")
        .where(filter=FieldFilter("state", "in", ["queued", "running"]))
        .stream()
    ):
        job = snapshot.to_dict()
        if not job or not job.get("caseId"):
            continue
        owner_case = repository.get(f"cases/{job.get('caseId', '')}")
        if (
            owner_case
            and (owner_case.get("classification") or {}).get("authorizationRationale")
            == "Synthetic classifier fixture; no live model."
        ):
            pending_fixture_jobs += 1
    result = {
        "deletedCaseIds": [case_id],
        "pendingFixtureJobs": pending_fixture_jobs,
        "receiptPreserved": True,
        "providerCalls": 0,
    }
    (ROOT / ".tmp/m3-fixture-cleanup.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return {
        "deletedFixtureCount": 1,
        "pendingFixtureJobs": pending_fixture_jobs,
        "providerCalls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--case-id")
    target.add_argument("--cleanup-aborted-receipt")
    parser.add_argument("--confirm-new-synthetic-case", action="store_true")
    parser.add_argument("--worker-disabled", action="store_true", required=True)
    args = parser.parse_args()
    if args.cleanup_aborted_receipt:
        result = cleanup_aborted(args.cleanup_aborted_receipt)
    elif args.confirm_new_synthetic_case:
        result = asyncio.run(seed(args.case_id))
    else:
        parser.error("Seeding requires --confirm-new-synthetic-case")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
