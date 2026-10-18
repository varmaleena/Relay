"""Verify cloud review boundaries and fail-closed idempotent existence probes."""

import json
import subprocess
import sys

import pytest

from infra.scripts import setup


def test_smoke_plan_has_only_dev_resources_and_bounded_data_roles() -> None:
    result = setup.plan("work-511514", "asia-south1", "dev")
    joined = "\n".join(" ".join(op["command"]) for op in result["operations"])
    assert "--public-access-prevention" in joined
    assert "roles/owner" not in joined
    assert "roles/editor" not in joined
    assert "roles/datastore" not in joined
    assert "roles/bigquery" not in joined
    assert "roles/storage.objectAdmin" not in joined
    assert "roles/iam.serviceAccountTokenCreator" not in joined
    assert "relay-dev-smoke" in joined
    assert "relay-dev-build" in joined
    assert "--execute-now" not in joined
    assert "firestore" not in joined
    assert result["costControls"]["hardCap"] is False
    assert result["costControls"]["maxSmokeExecutions"] == 1


@pytest.mark.parametrize(
    "project,region,env",
    [
        ("work-511514;delete", "asia-south1", "dev"),
        ("other-project", "asia-south1", "dev"),
        ("work-511514", "us-central1", "dev"),
        ("work-511514", "asia-south1", "prod"),
    ],
)
def test_reject_scope_changes(project: str, region: str, env: str) -> None:
    with pytest.raises(ValueError):
        setup.plan(project, region, env)


def test_apply_requires_exact_review_hash() -> None:
    completed = subprocess.run(
        [sys.executable, "infra/scripts/setup.py", "--apply", "--reviewed-plan-sha", "wrong"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "no resources changed" in completed.stderr


def test_apply_requires_discovered_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object) -> None:
        raise AssertionError("No CLI invocation allowed")

    monkeypatch.setattr(setup, "execute", forbidden)
    with pytest.raises(ValueError, match="Model discovery"):
        setup.apply(setup.plan("work-511514", "asia-south1", "dev"))


@pytest.mark.parametrize("error", ["SERVICE_DISABLED", "PERMISSION_DENIED", "DNS failed"])
def test_probe_failure_does_not_create_resource(
    error: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(setup, "execute", lambda _: subprocess.CompletedProcess([], 1, "", error))
    with pytest.raises(RuntimeError, match="probe failed"):
        setup.resource_exists(["describe", "synthetic"])


def test_not_found_means_create_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        setup, "execute", lambda _: subprocess.CompletedProcess([], 1, "", "NOT_FOUND")
    )
    assert not setup.resource_exists(["describe", "synthetic"])


def test_existing_resource_wrong_location_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        setup,
        "execute",
        lambda _: subprocess.CompletedProcess([], 0, json.dumps({"location": "US"}), ""),
    )
    with pytest.raises(RuntimeError, match="differs"):
        setup.resource_exists(["describe", "synthetic"], {"location": "ASIA-SOUTH1"})


def test_existing_resource_skips_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        setup,
        "execute",
        lambda _: subprocess.CompletedProcess([], 0, json.dumps({"location": "ASIA-SOUTH1"}), ""),
    )
    assert setup.resource_exists(["describe", "synthetic"], {"location": "ASIA-SOUTH1"})


def test_plan_hash_changes_when_model_changes() -> None:
    first = setup.plan("work-511514", "asia-south1", "dev", "gemini-3-fixture-a")
    second = setup.plan("work-511514", "asia-south1", "dev", "gemini-3-fixture-b")
    assert setup.plan_hash(first) != setup.plan_hash(second)


def test_exact_missing_image_response_is_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    error = "ERROR: (gcloud.artifacts.docker.images.describe) Image not found.\n"
    monkeypatch.setattr(setup, "execute", lambda _: subprocess.CompletedProcess([], 1, "", error))
    assert not setup.resource_exists(["artifacts", "docker", "images", "describe", "fixture"])
    with pytest.raises(RuntimeError, match="probe failed"):
        setup.resource_exists(["storage", "buckets", "describe", "fixture"])


def test_ambiguous_image_error_still_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    error = "ERROR: Image not found. Authentication failed."
    monkeypatch.setattr(setup, "execute", lambda _: subprocess.CompletedProcess([], 1, "", error))
    with pytest.raises(RuntimeError, match="probe failed"):
        setup.resource_exists(["artifacts", "docker", "images", "describe", "fixture"])


def test_bucket_existing_public_access_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    result = setup.plan("work-511514", "asia-south1", "dev")
    bucket = next(op for op in result["operations"] if op["id"] == "build-source-bucket")
    bad = {
        "location": "ASIA-SOUTH1",
        "uniform_bucket_level_access": True,
        "public_access_prevention": "inherited",
    }
    monkeypatch.setattr(
        setup, "execute", lambda _: subprocess.CompletedProcess([], 0, json.dumps(bad), "")
    )
    with pytest.raises(RuntimeError, match="public_access_prevention"):
        setup.resource_exists(bucket["probe"], bucket["expected"])


def test_bucket_existing_nonuniform_access_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    result = setup.plan("work-511514", "asia-south1", "dev")
    bucket = next(op for op in result["operations"] if op["id"] == "build-source-bucket")
    bad = {
        "location": "ASIA-SOUTH1",
        "uniform_bucket_level_access": False,
        "public_access_prevention": "enforced",
    }
    monkeypatch.setattr(
        setup, "execute", lambda _: subprocess.CompletedProcess([], 0, json.dumps(bad), "")
    )
    with pytest.raises(RuntimeError, match="uniform_bucket_level_access"):
        setup.resource_exists(bucket["probe"], bucket["expected"])


def test_missing_image_with_exact_cli_usage_help(monkeypatch: pytest.MonkeyPatch) -> None:
    error = (
        "ERROR: (gcloud.artifacts.docker.images.describe) Image not found.\n\n"
        "A valid container image can be referenced by tag or digest, has the format of\n"
        "  LOCATION-docker.pkg.dev/PROJECT-ID/REPOSITORY-ID/IMAGE:tag\n"
        "  LOCATION-docker.pkg.dev/PROJECT-ID/REPOSITORY-ID/IMAGE@sha256:digest.\n"
    )
    monkeypatch.setattr(setup, "execute", lambda _: subprocess.CompletedProcess([], 1, "", error))
    assert not setup.resource_exists(["artifacts", "docker", "images", "describe", "fixture"])


def test_missing_image_with_unexpected_tail_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    error = (
        "ERROR: (gcloud.artifacts.docker.images.describe) Image not found.\n\n"
        "Authentication failed or service disabled.\n"
    )
    monkeypatch.setattr(setup, "execute", lambda _: subprocess.CompletedProcess([], 1, "", error))
    with pytest.raises(RuntimeError, match="probe failed"):
        setup.resource_exists(["artifacts", "docker", "images", "describe", "fixture"])
