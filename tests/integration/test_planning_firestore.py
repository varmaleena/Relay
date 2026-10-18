"""Local emulator durability with real ADK, without provider/cloud calls."""

import asyncio
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from agents.workflows.planning import PlanningWorkflow
from packages.intake.repository import FirestoreRepository
from packages.intake.service import IntakeError, IntakeService
from packages.intake.storage import LocalFileBlobStore
from packages.packs.registry import PackRegistry
from packages.planning.service import PlanningService
from packages.safety import Actor
from packages.schemas.models import Classification, Urgency

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.emulator


class SyntheticClassifier:
    def __init__(self):
        self.calls = 0
        self.before = None

    async def classify(self, **kwargs):
        self.calls += 1
        if self.before:
            self.before()
        return Classification(
            typology="bank_impersonation",
            authorization_type="authorized_manipulated",
            authorization_rationale="Synthetic victim statement records own approval.",
            urgency=Urgency(level="high", reason="Synthetic product heuristic."),
            confidence=0.95,
            needs_human_review=False,
        )


@pytest.fixture
def durable(tmp_path):
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    if not host:
        pytest.skip("FIRESTORE_EMULATOR_HOST required; no cloud fallback")
    if not host.startswith(("127.0.0.1:", "localhost:")):
        pytest.fail("Only the loopback Firestore emulator is permitted")
    client = firestore.Client(project="demo-relay-local", credentials=AnonymousCredentials())
    shutil.copytree(ROOT / "packs", tmp_path / "packs")
    shutil.copytree(ROOT / "docs/pack-sources", tmp_path / "docs/pack-sources")
    registry = PackRegistry(tmp_path / "packs")
    storage = LocalFileBlobStore(tmp_path / "blobs", "http://127.0.0.1:8000", b"t" * 32)
    classifier = SyntheticClassifier()
    clock = [datetime.now(UTC)]

    def restart():
        intake = IntakeService(
            FirestoreRepository(client), storage, None, None, clock=lambda: clock[0]
        )
        workflow = PlanningWorkflow(classifier, registry, allow_draft_preview=True)
        planning = PlanningService(intake, workflow)
        intake.planning = planning
        return intake, planning

    intake, planning = restart()
    actor = Actor("synthetic-plan-" + uuid4().hex, "victim")
    case_id = intake.create_case(actor, {"language": "en", "consentVersion": "1.0"}, str(uuid4()))[
        "caseId"
    ]
    intake.update_facts(
        actor,
        case_id,
        {
            "facts": {
                "country": {"value": "IN", "provenance": {"source": "confirmed"}},
                "payment": {
                    "method": "upi",
                    "amount": {"value": "45000", "currency": "INR"},
                    "timestamp": (clock[0] - timedelta(minutes=20)).isoformat(),
                    "authorizedByVictim": True,
                },
                "contact": {"channel": "phone", "claimedIdentity": "bank"},
                "ongoingContact": False,
            }
        },
    )
    try:
        yield intake, planning, actor, case_id, classifier, restart, registry, clock
    finally:
        if intake.repository.get(f"cases/{case_id}"):
            intake.delete_case(actor, case_id)
        client.close()


def test_atomic_enqueue_restart_owner_denial_and_complete_erasure(durable):
    intake, planning, owner, case_id, classifier, restart, _, _ = durable
    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = list(
            pool.map(lambda _: planning.enqueue(owner, case_id, {"previewDraft": True}), range(2))
        )
    assert accepted[0] == accepted[1]
    stored = intake.repository.get(f"cases/{case_id}")
    assert len(stored["jobIds"]) == len(stored["planningRequestIds"]) == 1
    other = Actor("synthetic-unrelated-owner", "victim")
    with pytest.raises(IntakeError) as denied:
        planning.enqueue(other, case_id, {"previewDraft": True})
    assert denied.value.status == 403
    restarted, worker = restart()
    assert worker.enqueue(owner, case_id, {"previewDraft": True}) == accepted[0]
    asyncio.run(worker.process_case(accepted[0]["jobId"]))
    assert classifier.calls == 1
    plan = worker.get_plan(owner, case_id)
    assert not plan["stale"] and plan["packId"] == "pack_in_cyber_rail"
    assert restarted.get_job(owner, accepted[0]["jobId"])["state"] == "succeeded"
    with pytest.raises(IntakeError) as denied:
        worker.get_plan(other, case_id)
    assert denied.value.status == 403
    stored = restarted.repository.get(f"cases/{case_id}")
    assert stored["planIds"] == [plan["planId"]]
    restarted.delete_case(owner, case_id)
    assert restarted.repository.get(f"cases/{case_id}") is None
    assert restarted.repository.get(f"jobs/{accepted[0]['jobId']}") is None
    for request_id in stored["planningRequestIds"]:
        assert restarted.repository.get(f"planningRequests/{request_id}") is None
    for plan_id in stored["planIds"]:
        assert restarted.repository.get(f"cases/{case_id}/plans/{plan_id}") is None
    assert not list(restarted.repository.client.collection(f"cases/{case_id}/plans").stream())


def test_new_victim_statement_during_adk_run_cannot_publish_old_plan(durable):
    intake, planning, owner, case_id, classifier, _, _, clock = durable
    job = planning.enqueue(owner, case_id, {"previewDraft": True})

    def new_statement():
        def append(tx):
            case = tx.get(f"cases/{case_id}")
            case["transcript"].append(
                {
                    "role": "user",
                    "turnId": "synthetic-correction",
                    "text": "Synthetic correction: someone else approved it.",
                    "ts": clock[0].isoformat(),
                }
            )
            tx.set(f"cases/{case_id}", case)

        intake.repository.atomic(append)

    classifier.before = new_statement
    asyncio.run(planning.process_case(job["jobId"]))
    saved = intake.get_job(owner, job["jobId"])
    assert saved["state"] == "failed" and saved["error"]["code"] == "version_conflict"
    assert intake.repository.get(f"cases/{case_id}").get("plan") is None
    assert not list(intake.repository.client.collection(f"cases/{case_id}/plans").stream())
    assert planning.enqueue(owner, case_id, {"previewDraft": True}) != job


def test_catalog_change_after_restart_marks_saved_plan_stale(durable):
    _, planning, owner, case_id, _, restart, registry, _ = durable
    job = planning.enqueue(owner, case_id, {"previewDraft": True})
    asyncio.run(planning.process_case(job["jobId"]))
    assert not planning.get_plan(owner, case_id)["stale"]
    path = registry.root / "india-cyber-rail.yaml"
    pack = yaml.safe_load(path.read_text(encoding="utf-8"))
    pack["disclaimers"].append("Synthetic reviewed-copy change for staleness test only.")
    path.write_text(yaml.safe_dump(pack, allow_unicode=True), encoding="utf-8")
    _, restarted = restart()
    assert restarted.get_plan(owner, case_id)["stale"]
