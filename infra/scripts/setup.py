"""Hash-reviewed, additive M0 smoke infrastructure for the single approved dev project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "work-511514"
REGION = "asia-south1"
APIS = (
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "aiplatform.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "storage.googleapis.com",
)


def build_fingerprint() -> str:
    digest = hashlib.sha256()
    for relative in (
        "requirements.lock",
        ".dockerignore",
        ".gcloudignore",
        "services/platform_smoke/Dockerfile",
        "services/platform_smoke/main.py",
        "infra/cloudbuild.smoke.yaml",
    ):
        path = ROOT / relative
        digest.update(relative.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def plan(project: str, region: str, environment: str, model: str | None = None) -> dict[str, Any]:
    if (project, region, environment) != (PROJECT, REGION, "dev"):
        raise ValueError("M0 smoke is restricted to work-511514 / asia-south1 / dev")
    if model is not None and not re.fullmatch(r"gemini-3[\w.-]*", model):
        raise ValueError("Provide an actually discovered Gemini 3 model ID")
    repository = "relay-dev"
    bucket = f"gs://{project}-relay-dev-build-source"
    runtime = f"relay-dev-smoke@{project}.iam.gserviceaccount.com"
    builder = f"relay-dev-build@{project}.iam.gserviceaccount.com"
    image = (
        f"{region}-docker.pkg.dev/{project}/{repository}/platform-smoke:m0-{build_fingerprint()}"
    )
    operations: list[dict[str, Any]] = []

    def add(
        name: str,
        command: list[str],
        probe: list[str] | None = None,
        expected: dict[str, Any] | None = None,
    ) -> None:
        operations.append({"id": name, "command": command, "probe": probe, "expected": expected})

    add("enable-smoke-apis", ["services", "enable", *APIS, f"--project={project}"])
    for name in ("relay-dev-smoke", "relay-dev-build"):
        account = f"{name}@{project}.iam.gserviceaccount.com"
        add(
            name,
            [
                "iam",
                "service-accounts",
                "create",
                name,
                f"--display-name={name}",
                f"--project={project}",
            ],
            ["iam", "service-accounts", "describe", account, f"--project={project}"],
        )
    add(
        "image-repository",
        [
            "artifacts",
            "repositories",
            "create",
            repository,
            "--repository-format=docker",
            f"--location={region}",
            f"--project={project}",
        ],
        [
            "artifacts",
            "repositories",
            "describe",
            repository,
            f"--location={region}",
            f"--project={project}",
        ],
        {"format": "DOCKER"},
    )
    add(
        "build-source-bucket",
        [
            "storage",
            "buckets",
            "create",
            bucket,
            f"--location={region}",
            "--uniform-bucket-level-access",
            "--public-access-prevention",
            f"--project={project}",
        ],
        ["storage", "buckets", "describe", bucket],
        {
            "location": region.upper(),
            "uniform_bucket_level_access": True,
            "public_access_prevention": "enforced",
        },
    )
    add(
        "runtime-model-permission",
        [
            "projects",
            "add-iam-policy-binding",
            project,
            f"--member=serviceAccount:{runtime}",
            "--role=roles/aiplatform.user",
            "--condition=None",
        ],
    )
    add(
        "build-repository-writer",
        [
            "artifacts",
            "repositories",
            "add-iam-policy-binding",
            repository,
            f"--location={region}",
            f"--project={project}",
            f"--member=serviceAccount:{builder}",
            "--role=roles/artifactregistry.writer",
        ],
    )
    add(
        "build-source-reader",
        [
            "storage",
            "buckets",
            "add-iam-policy-binding",
            bucket,
            f"--member=serviceAccount:{builder}",
            "--role=roles/storage.objectViewer",
        ],
    )
    add(
        "build-log-writer",
        [
            "projects",
            "add-iam-policy-binding",
            project,
            f"--member=serviceAccount:{builder}",
            "--role=roles/logging.logWriter",
            "--condition=None",
        ],
    )
    add(
        "build-smoke-image",
        [
            "builds",
            "submit",
            ".",
            "--config=infra/cloudbuild.smoke.yaml",
            f"--substitutions=_IMAGE={image}",
            f"--service-account=projects/{project}/serviceAccounts/{builder}",
            f"--gcs-source-staging-dir={bucket}/source",
            f"--region={region}",
            f"--project={project}",
        ],
        ["artifacts", "docker", "images", "describe", image, f"--project={project}"],
    )
    add(
        "deploy-private-smoke-job",
        [
            "run",
            "jobs",
            "deploy",
            "relay-dev-platform-smoke",
            f"--image={image}",
            f"--service-account={runtime}",
            f"--region={region}",
            f"--project={project}",
            "--cpu=1",
            "--memory=512Mi",
            "--tasks=1",
            "--parallelism=1",
            "--max-retries=0",
            "--task-timeout=120s",
            "--labels=app=relay,environment=dev,milestone=m0",
            "--set-env-vars="
            + f"GOOGLE_CLOUD_PROJECT={project},GENAI_LOCATION=global,"
            + f"MODEL_FAST={model or '<DISCOVERED_MODEL>'}",
        ],
    )
    return {
        "project": project,
        "region": region,
        "environment": environment,
        "model": model,
        "image": image,
        "operations": operations,
        "execution": [
            "run",
            "jobs",
            "execute",
            "relay-dev-platform-smoke",
            f"--region={region}",
            f"--project={project}",
            "--wait",
        ],
        "costControls": {
            "targetInr": 1000,
            "hardCap": False,
            "budgetThresholds": [0.5, 0.8, 1],
            "maxSmokeExecutions": 1,
            "maxRetries": 0,
            "taskSeconds": 120,
            "tasks": 1,
            "parallelism": 1,
            "requestOutputTokens": 256,
            "idleCloudRunCompute": 0,
            "automaticTriggers": False,
        },
        "manualGates": [
            "Root review must bind exact plan SHA and discovered model before apply.",
            "Private job deployment does not execute; run one synthetic call separately.",
            "INR1000 alerts are not a ceiling; activate filtered billing alerts separately.",
            "No Firestore creation: API disabled and existing database location unverified.",
            "No prod, Firebase, app data, BigQuery, Pub/Sub, Tasks or Search provisioning.",
            "No deletion, cleanup policies, public invoker, keys or default build identity grants.",
            "Build/deploy user needs serviceAccountUser on both identities and deployment access.",
        ],
    }


def plan_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def cli_command() -> list[str]:
    if os.name == "nt":
        return ["powershell", "-NoProfile", "-File", str(ROOT / "scripts/gcloud.ps1")]
    found = shutil.which("gcloud")
    if not found:
        raise RuntimeError("gcloud CLI required to apply; planning needs no cloud access")
    return [found]


def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cli_command() + arguments + ["--quiet", "--format=json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )


def resource_exists(probe: list[str], expected: dict[str, Any] | None = None) -> bool:
    result = execute(probe)
    if result.returncode == 0:
        data = json.loads(result.stdout)
        if data.get("disabled"):
            raise RuntimeError("Existing service account is disabled; refusing changes")
        for key, value in (expected or {}).items():
            if data.get(key) != value:
                raise RuntimeError(f"Existing resource {key} differs from reviewed plan")
        return True
    # Fail closed on disabled APIs, permission, network, quota or ambiguous errors.
    if re.search(r"\bNOT_FOUND\b|\b404\b|does not exist", result.stderr):
        return False
    if probe[:4] == ["artifacts", "docker", "images", "describe"]:
        lines = result.stderr.strip().splitlines()
        expected_first = "ERROR: (gcloud.artifacts.docker.images.describe) Image not found."
        expected_help = (
            "A valid container image can be referenced by tag or digest, has the format of\n"
            "  LOCATION-docker.pkg.dev/PROJECT-ID/REPOSITORY-ID/IMAGE:tag\n"
            "  LOCATION-docker.pkg.dev/PROJECT-ID/REPOSITORY-ID/IMAGE@sha256:digest."
        )
        if lines and lines[0] == expected_first:
            remaining = "\n".join(lines[1:]).strip()
            if remaining in {"", expected_help}:
                return False
    raise RuntimeError(f"Read-only existence probe failed: {result.stderr.strip()}")


def apply(value: dict[str, Any]) -> None:
    if value["model"] is None:
        raise ValueError("Model discovery is unresolved; no mutations permitted")
    for operation in value["operations"]:
        if operation["probe"] and resource_exists(operation["probe"], operation["expected"]):
            print(json.dumps({"operation": operation["id"], "status": "already_exists"}))
            continue
        print(json.dumps({"operation": operation["id"], "status": "starting"}), flush=True)
        result = execute(operation["command"])
        if result.returncode:
            raise RuntimeError(f"Operation {operation['id']} failed: {result.stderr.strip()}")
        print(json.dumps({"operation": operation["id"], "status": "applied"}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--environment", default="dev")
    parser.add_argument("--model")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewed-plan-sha")
    args = parser.parse_args()
    value = plan(args.project, args.region, args.environment, args.model)
    fingerprint = plan_hash(value)
    if not args.apply:
        print(json.dumps({"planSha256": fingerprint, "plan": value}, indent=2))
        return
    if args.reviewed_plan_sha != fingerprint:
        parser.error("Exact reviewed plan SHA required; no resources changed")
    if value["model"] is None:
        parser.error("Discovered model required; no resources changed")
    apply(value)


if __name__ == "__main__":
    main()
