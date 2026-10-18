"""No-provider PDF helper keeps every queued state private until terminal commit."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from packages.intake.repository import MemoryRepository
from packages.intake.service import IntakeService
from packages.packs.registry import PackRegistry
from packages.safety import Actor
from scripts.cloud_pdf_fixture import (
    ROOT,
    NoExternalEffects,
    commit,
    environment_guard,
    fresh_case,
    prepare,
    seed,
)


class ObservedRepository(MemoryRepository):
    def __init__(self):
        super().__init__()
        self.visible_job_states = []

    def set(self, path, value):
        if path.startswith("jobs/"):
            self.visible_job_states.append(value.get("state"))
        super().set(path, value)


@pytest.fixture
def fixture():
    now = datetime.now(UTC)
    repo = ObservedRepository()
    intake = IntakeService(repo, NoExternalEffects(), None, None, clock=lambda: now)
    actor = Actor("synthetic-browser-owner", "victim")
    case_id = intake.create_case(actor, {"language": "en", "consentVersion": "1.0"}, str(uuid4()))[
        "caseId"
    ]
    return repo, actor, case_id, now, PackRegistry(ROOT / "packs")


def test_actual_domain_fixture_commits_only_terminal_jobs_no_send_or_provider(fixture):
    repo, actor, case_id, now, registry = fixture
    result = asyncio.run(
        seed(repo, case_id=case_id, owner_uid=actor.uid, registry=registry, now=now)
    )
    assert result["providerCalls"] == 0 and len(result["packetIds"]) == 3
    assert repo.visible_job_states and set(repo.visible_job_states) == {"succeeded"}
    case = repo.get("cases/" + case_id)
    assert case["syntheticPdfFixture"]["mode"] == "synthetic-no-model-pdf-transport"
    assert not any(
        path.startswith(("mockDeliveries/", "receiverViews/", "a2aTasks/")) or "/approvals/" in path
        for path in repo.documents
    )
    for packet_id in result["packetIds"]:
        packet = repo.get(f"cases/{case_id}/packets/{packet_id}")
        assert packet["status"] == "VERIFIED" and not packet.get("delivery")
        assert "Synthetic" in packet["content"]["subject"]
        assert "no live model" in packet["verification"]["checks"][0]["detail"]
    with pytest.raises(ValueError):
        asyncio.run(seed(repo, case_id=case_id, owner_uid=actor.uid, registry=registry, now=now))


def test_private_prepare_never_exposes_queued_state_and_owner_cas_rechecks(fixture):
    repo, actor, case_id, now, registry = fixture
    initial = repo.get("cases/" + case_id)
    records, proof = asyncio.run(prepare(initial, now=now, registry=registry))
    assert not repo.visible_job_states
    assert repo.get("cases/" + case_id) == initial
    changed = deepcopy(initial)
    changed["factsRevision"] = 1
    repo.set("cases/" + case_id, changed)
    with pytest.raises(ValueError):
        commit(repo, initial, records, owner_uid=actor.uid, now=now, registry=registry, proof=proof)
    assert not repo.visible_job_states and repo.get("cases/" + case_id) == changed


def test_queued_job_or_foreign_write_can_never_escape_buffer(fixture):
    repo, actor, case_id, now, registry = fixture
    initial = repo.get("cases/" + case_id)
    records, proof = asyncio.run(prepare(initial, now=now, registry=registry))
    unsafe = deepcopy(records)
    job = next(value for key, value in unsafe.items() if key.startswith("jobs/"))
    job["state"] = "queued"
    with pytest.raises(ValueError):
        commit(repo, initial, unsafe, owner_uid=actor.uid, now=now, registry=registry, proof=proof)
    unsafe = deepcopy(records)
    unsafe["cases/foreign-case"] = {"victimUid": actor.uid}
    with pytest.raises(ValueError):
        commit(repo, initial, unsafe, owner_uid=actor.uid, now=now, registry=registry, proof=proof)
    assert repo.visible_job_states == []


@pytest.mark.parametrize(
    "change",
    [
        {"victimUid": "someone-else"},
        {"factsRevision": 1},
        {"evidenceIds": ["evidence-existing"]},
        {"deleting": True},
    ],
)
def test_owner_nonempty_deleting_guard(fixture, change):
    repo, actor, case_id, now, _ = fixture
    with pytest.raises(ValueError):
        fresh_case(repo.get("cases/" + case_id) | change, case_id, actor.uid, now)


def test_explicit_project_and_no_emulator_guard(monkeypatch):
    for name in ("FIRESTORE_EMULATOR_HOST", "FIREBASE_AUTH_EMULATOR_HOST", "STORAGE_EMULATOR_HOST"):
        monkeypatch.delenv(name, raising=False)
    environment_guard("work-511514", apply=True)
    for project, apply in [
        ("demo-relay-local", True),
        ("unrelated-project", True),
        ("work-511514", False),
    ]:
        with pytest.raises(ValueError):
            environment_guard(project, apply=apply)
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8095")
    with pytest.raises(ValueError):
        environment_guard("work-511514", apply=True)
