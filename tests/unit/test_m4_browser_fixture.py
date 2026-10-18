"""M4 fixture may never target cloud, existing user work or unmarked cases."""

from datetime import UTC, datetime, timedelta

import pytest

from scripts.m4_browser_fixture import fixture_case, guard_environment


def test_fixture_environment_requires_exact_local_workerless_mode(monkeypatch):
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8095")
    monkeypatch.setenv("GCP_PROJECT_ID", "demo-relay-local")
    monkeypatch.setenv("RELAY_WORKER_DISABLED", "1")
    guard_environment()
    for key, value in (
        ("FIRESTORE_EMULATOR_HOST", "remote.example:8095"),
        ("GCP_PROJECT_ID", "work-511514"),
        ("RELAY_WORKER_DISABLED", "0"),
    ):
        with monkeypatch.context() as context:
            context.setenv(key, value)
            with pytest.raises(ValueError, match="emulator"):
                guard_environment()


def test_only_fresh_marked_empty_synthetic_case_is_eligible():
    case = {
        "classification": {
            "authorizationRationale": "Synthetic classifier fixture; no live model."
        },
        "facts": {
            "victimBank": "Fictional Test Bank",
            "contact": {"identifier": "synthetic-caller"},
        },
        "createdAt": datetime.now(UTC).isoformat(),
        "transcript": [],
        "evidenceIds": [],
    }
    fixture_case(case)
    for changes in (
        {"classification": {}},
        {"evidenceIds": ["existing"]},
        {"transcript": ["user work"]},
        {"createdAt": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
    ):
        with pytest.raises(ValueError):
            fixture_case(case | changes)
