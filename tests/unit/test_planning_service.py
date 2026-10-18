"""Real ADK orchestration with synthetic classification and durable mutation boundaries."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from agents.workflows.planning import PlanningWorkflow
from packages.intake.repository import MemoryRepository
from packages.intake.service import IntakeError, IntakeService
from packages.intake.storage import LocalFileBlobStore
from packages.packs.registry import PackRegistry
from packages.planning.service import PlanningService
from packages.safety import Actor
from packages.schemas.models import Classification, Urgency

ROOT = Path(__file__).resolve().parents[2]


class SyntheticClassifier:
    def __init__(self):
        self.calls = 0
        self.before = None
        self.degraded = False
        self.unclear = False

    async def classify(self, **kwargs):
        self.calls += 1
        if self.before:
            self.before()
        return Classification(
            typology="bank_impersonation",
            authorization_type="unclear" if self.unclear else "authorized_manipulated",
            authorization_rationale="Synthetic test: victim records own approval.",
            urgency=Urgency(level="critical", reason="Synthetic timing heuristic, not law."),
            confidence=0.4 if self.unclear else 0.95,
            needs_human_review=self.unclear,
            clarifying_question="Who approved the payment?" if self.unclear else None,
            degraded=self.degraded,
            failure_code="model_unavailable" if self.degraded else None,
        )


@pytest.fixture
def setup(tmp_path):
    repository = MemoryRepository()
    clock = [datetime(2026, 10, 14, 12, tzinfo=UTC)]
    intake = IntakeService(
        repository,
        LocalFileBlobStore(tmp_path, "http://local", b"s" * 32),
        None,
        None,
        clock=lambda: clock[0],
    )
    actor = Actor("synthetic-plan-owner", "victim")
    created = intake.create_case(actor, {"language": "en", "consentVersion": "1.0"}, str(uuid4()))
    case_id = created["caseId"]
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
    classifier = SyntheticClassifier()
    workflow = PlanningWorkflow(classifier, PackRegistry(ROOT / "packs"), allow_draft_preview=True)
    service = PlanningService(intake, workflow)
    intake.planning = service
    return service, intake, repository, actor, case_id, classifier, clock


def test_real_adk_sequence_idempotence_provenance_staleness_and_cleanup(setup):
    service, intake, repository, actor, case_id, classifier, _ = setup
    accepted = service.enqueue(actor, case_id, {"previewDraft": True})
    assert service.enqueue(actor, case_id, {"previewDraft": True}) == accepted
    asyncio.run(service.process_case(accepted["jobId"]))
    plan = service.get_plan(actor, case_id)
    assert classifier.calls == 1
    assert plan["classification"]["authorizationType"] == "authorized_manipulated"
    assert plan["packId"] == "pack_in_cyber_rail" and plan["packStatus"] == "draft"
    assert plan["sourceCitations"] and not plan["stale"]
    assert all(step["channel"]["verified"] is False for step in plan["steps"])
    assert all(not step["deadline"] or step["deadline"]["dueAt"] is None for step in plan["steps"])
    assert intake.get_job(actor, accepted["jobId"])["state"] == "succeeded"
    assert (
        intake.get_case(actor, case_id)["classification"]["authorizationType"]
        == "authorized_manipulated"
    )
    intake.update_facts(actor, case_id, {"facts": {"victimBank": "Another Test Bank"}})
    assert service.get_plan(actor, case_id)["stale"]
    assert intake.get_case(actor, case_id)["plan"]["stale"]
    intake.delete_case(actor, case_id)
    assert not any(path.startswith(f"cases/{case_id}") for path in repository.documents)
    assert not any(path.startswith("planningRequests/") for path in repository.documents)


def test_ownership_draft_opt_in_and_missing_facts_are_enforced(setup):
    service, intake, _, actor, case_id, _, _ = setup
    with pytest.raises(IntakeError) as denied:
        service.enqueue(Actor("outsider", "victim"), case_id, {"previewDraft": True})
    assert denied.value.status == 403
    with pytest.raises(IntakeError) as unpublished:
        service.enqueue(actor, case_id, {})
    assert unpublished.value.code == "pack_review_required"
    intake.update_facts(actor, case_id, {"facts": {"payment": {"amount": None}}})
    with pytest.raises(IntakeError) as missing:
        service.enqueue(actor, case_id, {"previewDraft": True})
    assert missing.value.code == "minimum_facts_missing"


def test_changed_sources_during_generation_cannot_publish_stale_analysis(setup):
    service, _, repository, actor, case_id, classifier, clock = setup
    accepted = service.enqueue(actor, case_id, {"previewDraft": True})

    def source_change():
        case = repository.get(f"cases/{case_id}")
        # An omitted facts delta must not make a new contradictory source invisible.
        case["transcript"].append(
            {
                "role": "user",
                "text": "Synthetic correction: I did not approve it.",
                "ts": clock[0].isoformat(),
                "turnId": "synthetic",
            }
        )
        repository.set(f"cases/{case_id}", case)

    classifier.before = source_change
    asyncio.run(service.process_case(accepted["jobId"]))
    job = repository.get(f"jobs/{accepted['jobId']}")
    assert job["state"] == "failed" and job["error"]["code"] == "version_conflict"
    assert repository.get(f"cases/{case_id}").get("plan") is None
    assert service.enqueue(actor, case_id, {"previewDraft": True}) != accepted


def test_transport_failure_retries_without_a_false_clarification(setup):
    service, _, repository, actor, case_id, classifier, clock = setup
    classifier.degraded = True
    accepted = service.enqueue(actor, case_id, {"previewDraft": True})
    for _attempt in range(3):
        asyncio.run(service.process_case(accepted["jobId"]))
        clock[0] += timedelta(seconds=10)
    job = repository.get(f"jobs/{accepted['jobId']}")
    assert job["state"] == "failed" and job["attempts"] == 3
    assert job["error"]["code"] == "model_unavailable"
    assert repository.get(f"cases/{case_id}").get("classification") is None


def test_real_ambiguity_and_unconfirmed_country_pause_without_a_plan(setup):
    service, _, repository, actor, case_id, classifier, _ = setup
    classifier.unclear = True
    accepted = service.enqueue(actor, case_id, {"previewDraft": True})
    asyncio.run(service.process_case(accepted["jobId"]))
    case = repository.get(f"cases/{case_id}")
    assert case["classification"]["needsHumanReview"] and case["plan"] is None
    assert case["status"] == "INTAKE"
    classifier.unclear = False
    case["facts"]["country"]["provenance"] = {"source": "victim_statement"}
    repository.set(f"cases/{case_id}", case)
    accepted = service.enqueue(actor, case_id, {"previewDraft": True})
    asyncio.run(service.process_case(accepted["jobId"]))
    case = repository.get(f"cases/{case_id}")
    assert "country" in case["classification"]["clarifyingQuestion"]
    assert case["plan"] is None


def test_duplicate_workers_and_rerun_retain_immutable_plan_history(setup):
    service, _, repository, actor, case_id, classifier, _ = setup
    accepted = service.enqueue(actor, case_id, {"previewDraft": True})
    asyncio.run(service.process_case(accepted["jobId"]))
    asyncio.run(service.process_case(accepted["jobId"]))
    assert classifier.calls == 1
    rerun = service.enqueue(actor, case_id, {"previewDraft": True}, rerun=True)
    asyncio.run(service.process_case(rerun["jobId"]))
    assert classifier.calls == 2
    case = repository.get(f"cases/{case_id}")
    assert len(case["planIds"]) == 2 and case["planIds"][0] != case["planIds"][1]


def test_active_third_attempt_lease_is_not_failed_by_stale_worker_poll(setup):
    service, _, repository, actor, case_id, classifier, clock = setup
    accepted = service.enqueue(actor, case_id, {"previewDraft": True})
    path = f"jobs/{accepted['jobId']}"
    job = repository.get(path)
    job.update(
        state="running",
        attempts=3,
        claimToken="synthetic-active-third-claim",
        leaseUntil=(clock[0] + timedelta(minutes=2)).isoformat(),
    )
    repository.set(path, job)
    asyncio.run(service.process_case(accepted["jobId"]))
    assert repository.get(path) == job
    assert classifier.calls == 0
    # After the lease expires, the cap prevents an unbounded fourth inference.
    clock[0] += timedelta(minutes=3)
    asyncio.run(service.process_case(accepted["jobId"]))
    saved = repository.get(path)
    assert saved["state"] == "failed" and saved["attempts"] == 3
    assert saved["error"]["code"] == "budget_exceeded" and classifier.calls == 0
