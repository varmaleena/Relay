"""Reviewable deployment commands, strict probes, no cloud calls."""

import subprocess
from unittest.mock import Mock

import pytest

from infra.scripts.deploy_app import apply, matches, plan
from infra.scripts.setup import plan_hash


def test_foundation_is_deterministic_scoped_and_private():
    value = plan()
    assert plan_hash(value) == plan_hash(plan())
    text = str(value)
    for forbidden in ("roles/owner", "roles/editor", "allUsers", "databases', 'create"):
        assert forbidden not in text
    assert value["project"] == "work-511514" and value["region"] == "asia-south1"
    assert value["runtime"]["shared"] == {
        "minInstances": 0,
        "maxInstances": 1,
        "cpu": 1,
        "timeoutSeconds": 600,
    }
    assert value["files"]["lifecycle"]["rule"][0]["condition"] == {"age": 7}
    assert len(value["files"]["cors"][0]["origin"]) == 2


def test_review_hash_required_before_any_call_or_file(tmp_path, monkeypatch):
    execute = Mock()
    monkeypatch.setattr("infra.scripts.deploy_app.execute", execute)
    with pytest.raises(ValueError, match="SHA"):
        apply(plan(), "wrong", tmp_path / "artifacts")
    execute.assert_not_called()
    assert not (tmp_path / "artifacts").exists()


def test_unexpected_probe_error_never_creates_resource(tmp_path, monkeypatch):
    value = plan()
    value["operations"] = [value["operations"][1]]
    execute = Mock(return_value=subprocess.CompletedProcess([], 1, "", "PERMISSION_DENIED"))
    monkeypatch.setattr("infra.scripts.deploy_app.execute", execute)
    with pytest.raises(RuntimeError, match="probe failed"):
        apply(value, plan_hash(value), tmp_path / "artifacts")
    execute.assert_called_once()


def test_existing_wrong_database_location_fails_closed(tmp_path, monkeypatch):
    value = plan()
    value["operations"] = [value["operations"][1]]
    execute = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, '{"locationId":"us-central1","type":"FIRESTORE_NATIVE"}', ""
        )
    )
    monkeypatch.setattr("infra.scripts.deploy_app.execute", execute)
    with pytest.raises(RuntimeError, match="differs"):
        apply(value, plan_hash(value), tmp_path / "artifacts")
    execute.assert_called_once()


def test_trigger_plan_binds_exact_url_and_versioned_oidc():
    with pytest.raises(ValueError, match="URL"):
        plan("triggers", worker_url="https://attacker.example")
    value = plan("triggers", worker_url="https://relay-dev-worker-synthetic.a.run.app")
    command = next(o["command"] for o in value["operations"] if o["id"] == "job-subscription")
    assert "--ack-deadline=600" in command and "--max-delivery-attempts=5" in command
    assert "--push-auth-token-audience=https://relay-dev-worker-synthetic.a.run.app" in command
    assert matches({"oidc": {"aud": "correct", "extra": True}}, {"oidc": {"aud": "correct"}})
    assert not matches({"oidc": {"aud": "wrong"}}, {"oidc": {"aud": "correct"}})


def test_trigger_rejects_existing_public_worker_before_mutations(tmp_path, monkeypatch):
    value = plan("triggers", worker_url="https://relay-dev-worker-synthetic.a.run.app")
    execute = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, '{"bindings":[{"members":["allUsers"],"role":"roles/run.invoker"}]}', ""
        )
    )
    monkeypatch.setattr("infra.scripts.deploy_app.execute", execute)
    with pytest.raises(RuntimeError, match="public invocation"):
        apply(value, plan_hash(value), tmp_path / "artifacts")
    execute.assert_called_once()


def test_matching_existing_resource_is_skipped(tmp_path, monkeypatch):
    value = plan()
    value["operations"] = [value["operations"][1]]
    execute = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, '{"locationId":"asia-south1","type":"FIRESTORE_NATIVE"}', ""
        )
    )
    monkeypatch.setattr("infra.scripts.deploy_app.execute", execute)
    apply(value, plan_hash(value), tmp_path / "artifacts")
    execute.assert_called_once()
