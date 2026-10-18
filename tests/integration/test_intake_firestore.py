"""Opt-in real Firestore emulator durability test; no live project writes."""

import os
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from packages.intake.repository import FirestoreRepository
from packages.intake.service import IntakeError, IntakeService
from packages.intake.storage import LocalFileBlobStore
from packages.safety import Actor


@pytest.mark.emulator
def test_firestore_atomic_intake_replay_and_delete_survives_new_repository(tmp_path):
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    if not host:
        pytest.skip("FIRESTORE_EMULATOR_HOST required; no cloud fallback")
    if not host.startswith(("127.0.0.1:", "localhost:")):
        pytest.fail("This test only permits the loopback emulator")
    client = firestore.Client(project="demo-relay-local", credentials=AnonymousCredentials())
    repo = FirestoreRepository(client)
    storage = LocalFileBlobStore(tmp_path, "http://127.0.0.1:8000", b"f" * 32)
    service = IntakeService(repo, storage, None, None)
    actor = Actor("synthetic-test-" + uuid4().hex, "victim")
    key = str(uuid4())
    body = {"language": "en", "consentVersion": "1.0"}
    case = service.create_case(actor, body, key)
    case_id = case["caseId"]
    try:
        restarted = IntakeService(FirestoreRepository(client), storage, None, None)
        assert restarted.get_case(actor, case_id)["caseId"] == case_id
        assert restarted.create_case(actor, body, key) == case
        restarted.update_facts(
            actor,
            case_id,
            {"facts": {"payment": {"method": "upi"}}, "source": "confirmed", "ifRevision": 0},
        )
        assert service.get_case(actor, case_id)["factsRevision"] == 1
        with pytest.raises(IntakeError) as stale:
            service.update_facts(
                actor,
                case_id,
                {"facts": {"payment": {"method": "card"}}, "source": "confirmed", "ifRevision": 0},
            )
        assert stale.value.code == "version_conflict"
    finally:
        service.delete_case(actor, case_id)
        client.close()
