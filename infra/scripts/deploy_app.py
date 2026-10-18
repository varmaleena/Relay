"""Additive, hash-reviewed Relay development deployment; no calls in plan mode."""

import argparse
import json
import re
from pathlib import Path
from typing import Any

from infra.scripts.setup import PROJECT, REGION, execute, plan_hash


def account(name: str) -> str:
    return f"relay-dev-{name}@{PROJECT}.iam.gserviceaccount.com"


def plan(phase: str = "foundation", *, worker_url: str = "") -> dict[str, Any]:
    if phase not in {"foundation", "triggers"}:
        raise ValueError("only reviewed dev foundation/triggers phases supported")
    origins = [f"https://{PROJECT}.web.app", f"https://{PROJECT}.firebaseapp.com"]
    operations = []

    def add(
        name: str,
        command: list[str],
        probe: list[str] | None = None,
        expected: dict[str, Any] | None = None,
    ) -> None:
        operations.append(dict(id=name, command=command, probe=probe, expected=expected))

    def project_role(name: str, identity: str, role: str) -> None:
        add(
            name,
            [
                "projects",
                "add-iam-policy-binding",
                PROJECT,
                f"--member=serviceAccount:{identity}",
                f"--role={role}",
            ],
        )

    topic = f"projects/{PROJECT}/topics/relay-jobs"
    dlq = f"projects/{PROJECT}/topics/relay-jobs-dlq"
    if phase == "foundation":
        add(
            "enable-app-apis",
            [
                "services",
                "enable",
                "firestore.googleapis.com",
                "pubsub.googleapis.com",
                "cloudscheduler.googleapis.com",
                "identitytoolkit.googleapis.com",
                "firebase.googleapis.com",
                "firebaseappcheck.googleapis.com",
                f"--project={PROJECT}",
            ],
        )
        add(
            "verify-database",
            [],
            ["firestore", "databases", "describe", "--database=(default)", f"--project={PROJECT}"],
            {"locationId": REGION, "type": "FIRESTORE_NATIVE"},
        )
        for name in ("api", "worker", "job-invoker"):
            add(
                f"account-{name}",
                ["iam", "service-accounts", "create", f"relay-dev-{name}", f"--project={PROJECT}"],
                ["iam", "service-accounts", "describe", account(name), f"--project={PROJECT}"],
                {"email": account(name)},
            )
        for name in ("api", "worker"):
            for role in ("roles/datastore.user", "roles/aiplatform.user"):
                project_role(f"{name}-{role.rsplit('.', 1)[-1]}", account(name), role)
        project_role("api-auth-revocation-read", account("api"), "roles/firebaseauth.viewer")
        add(
            "api-self-signblob",
            [
                "iam",
                "service-accounts",
                "add-iam-policy-binding",
                account("api"),
                f"--member=serviceAccount:{account('api')}",
                "--role=roles/iam.serviceAccountTokenCreator",
                f"--project={PROJECT}",
            ],
        )
        for kind in ("evidence", "exports"):
            bucket = f"gs://{PROJECT}-relay-dev-{kind}"
            add(
                f"bucket-{kind}",
                [
                    "storage",
                    "buckets",
                    "create",
                    bucket,
                    f"--project={PROJECT}",
                    f"--location={REGION}",
                    "--uniform-bucket-level-access",
                    "--public-access-prevention",
                ],
                ["storage", "buckets", "describe", bucket],
                {
                    "location": REGION.upper(),
                    "uniform_bucket_level_access": True,
                    "public_access_prevention": "enforced",
                },
            )
            add(
                f"bucket-{kind}-policy",
                [
                    "storage",
                    "buckets",
                    "update",
                    bucket,
                    "--lifecycle-file=@lifecycle",
                    "--cors-file=@cors",
                ],
            )
            for name in ("api", "worker"):
                add(
                    f"bucket-{kind}-{name}",
                    [
                        "storage",
                        "buckets",
                        "add-iam-policy-binding",
                        bucket,
                        f"--member=serviceAccount:{account(name)}",
                        "--role=roles/storage.objectAdmin",
                    ],
                )
        for name in ("relay-jobs", "relay-jobs-dlq"):
            full = f"projects/{PROJECT}/topics/{name}"
            add(
                f"topic-{name}",
                ["pubsub", "topics", "create", full],
                ["pubsub", "topics", "describe", full],
                {"name": full},
            )
        for name in ("api", "worker"):
            add(
                f"topic-publisher-{name}",
                [
                    "pubsub",
                    "topics",
                    "add-iam-policy-binding",
                    topic,
                    f"--member=serviceAccount:{account(name)}",
                    "--role=roles/pubsub.publisher",
                ],
            )
    else:
        if not re.fullmatch(
            r"https://relay-dev-worker-(?:[a-z0-9-]+\.a|798642284156\.asia-south1)\.run\.app",
            worker_url,
        ):
            raise ValueError("explicit deployed relay-dev-worker run.app URL required")
        agent = "service-798642284156@gcp-sa-pubsub.iam.gserviceaccount.com"
        add(
            "verify-worker-private",
            [],
            [
                "run",
                "services",
                "get-iam-policy",
                "relay-dev-worker",
                f"--region={REGION}",
                f"--project={PROJECT}",
            ],
            {"forbidPublic": True},
        )
        add(
            "push-token-issuer",
            [
                "iam",
                "service-accounts",
                "add-iam-policy-binding",
                account("job-invoker"),
                f"--project={PROJECT}",
                f"--member=serviceAccount:{agent}",
                "--role=roles/iam.serviceAccountTokenCreator",
            ],
        )
        add(
            "dlq-publisher",
            [
                "pubsub",
                "topics",
                "add-iam-policy-binding",
                dlq,
                f"--member=serviceAccount:{agent}",
                "--role=roles/pubsub.publisher",
            ],
        )
        add(
            "private-worker-invoker",
            [
                "run",
                "services",
                "add-iam-policy-binding",
                "relay-dev-worker",
                f"--region={REGION}",
                f"--project={PROJECT}",
                f"--member=serviceAccount:{account('job-invoker')}",
                "--role=roles/run.invoker",
            ],
        )
        add(
            "job-subscription",
            [
                "pubsub",
                "subscriptions",
                "create",
                "relay-dev-worker-push",
                f"--project={PROJECT}",
                f"--topic={topic}",
                f"--push-endpoint={worker_url}/pubsub/push",
                f"--push-auth-service-account={account('job-invoker')}",
                f"--push-auth-token-audience={worker_url}",
                "--ack-deadline=600",
                f"--dead-letter-topic={dlq}",
                "--max-delivery-attempts=5",
                "--min-retry-delay=10s",
                "--max-retry-delay=300s",
                "--message-retention-duration=1d",
            ],
            [
                "pubsub",
                "subscriptions",
                "describe",
                "relay-dev-worker-push",
                f"--project={PROJECT}",
            ],
            {
                "topic": topic,
                "ackDeadlineSeconds": 600,
                "pushConfig": {
                    "pushEndpoint": f"{worker_url}/pubsub/push",
                    "oidcToken": {
                        "serviceAccountEmail": account("job-invoker"),
                        "audience": worker_url,
                    },
                },
                "deadLetterPolicy": {"deadLetterTopic": dlq, "maxDeliveryAttempts": 5},
            },
        )
        add(
            "sweep-schedule",
            [
                "scheduler",
                "jobs",
                "create",
                "http",
                "relay-dev-sweep",
                f"--project={PROJECT}",
                f"--location={REGION}",
                "--schedule=*/10 * * * *",
                "--time-zone=Etc/UTC",
                f"--uri={worker_url}/internal/sweep",
                "--http-method=POST",
                "--message-body={}",
                f"--oidc-service-account-email={account('job-invoker')}",
                f"--oidc-token-audience={worker_url}",
                "--attempt-deadline=600s",
                "--max-retry-attempts=0",
            ],
            [
                "scheduler",
                "jobs",
                "describe",
                "relay-dev-sweep",
                f"--project={PROJECT}",
                f"--location={REGION}",
            ],
            {
                "schedule": "*/10 * * * *",
                "httpTarget": {
                    "uri": f"{worker_url}/internal/sweep",
                    "httpMethod": "POST",
                    "oidcToken": {
                        "serviceAccountEmail": account("job-invoker"),
                        "audience": worker_url,
                    },
                },
            },
        )
        add(
            "dlq-forwarding-subscriber",
            [
                "pubsub",
                "subscriptions",
                "add-iam-policy-binding",
                "relay-dev-worker-push",
                f"--project={PROJECT}",
                f"--member=serviceAccount:{agent}",
                "--role=roles/pubsub.subscriber",
            ],
        )
        add(
            "retain-dead-letters",
            [
                "pubsub",
                "subscriptions",
                "create",
                "relay-dev-dead-letters",
                f"--project={PROJECT}",
                f"--topic={dlq}",
                "--message-retention-duration=7d",
            ],
            [
                "pubsub",
                "subscriptions",
                "describe",
                "relay-dev-dead-letters",
                f"--project={PROJECT}",
            ],
            {"topic": dlq},
        )
    return {
        "schemaVersion": 1,
        "project": PROJECT,
        "region": REGION,
        "environment": "dev",
        "phase": phase,
        "operations": operations,
        "files": {
            "lifecycle": {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 7}}]},
            "cors": [
                {
                    "origin": origins,
                    "method": ["GET", "PUT"],
                    "responseHeader": ["Content-Type", "Content-Length"],
                    "maxAgeSeconds": 3600,
                }
            ],
        },
        "runtime": {
            "api": {"memory": "1Gi", "concurrency": 4},
            "worker": {"memory": "2Gi", "concurrency": 1},
            "shared": {"minInstances": 0, "maxInstances": 1, "cpu": 1, "timeoutSeconds": 600},
        },
        "gates": [
            "INR1000 is an alert target, not a cap",
            "Firebase/Auth/AppCheck root-owned",
            "No database creation, build or Cloud Run deploy in this manifest",
            "Runtime deploy must use immutable digests, dedicated accounts and worker private IAM",
            "PubSub agent798642284156 uses scoped DLQ/subscribe and invoker token issuance",
            "Verify standard Scheduler service-agent role and deployer actAs before trigger apply",
            "No public worker binding; inspect existing service policy before triggers",
            "Retention lifecycle is asynchronous and does not prove72h cascade deletion",
        ],
    }


def matches(data: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(
        key in data
        and (matches(data[key], value) if isinstance(value, dict) else data[key] == value)
        for key, value in expected.items()
    )


def apply(value: dict[str, Any], reviewed: str, directory: Path) -> None:
    if reviewed != plan_hash(value):
        raise ValueError("exact reviewed plan SHA required")
    directory.mkdir(parents=True, exist_ok=False)
    files = {}
    for name, content in value["files"].items():
        target = directory / f"{name}.json"
        target.write_text(json.dumps(content), "utf-8")
        files[name] = str(target.resolve())
    for operation in value["operations"]:
        if operation["probe"]:
            result = execute(operation["probe"])
            if result.returncode == 0:
                data = json.loads(result.stdout)
                expected = operation["expected"] or {}
                if expected.get("forbidPublic"):
                    if any(
                        member in {"allUsers", "allAuthenticatedUsers"}
                        for binding in data.get("bindings", [])
                        for member in binding.get("members", [])
                    ):
                        raise RuntimeError("worker policy permits public invocation")
                    continue
                if data.get("disabled") or not matches(data, expected):
                    raise RuntimeError(f"existing resource differs: {operation['id']}")
                continue
            if not re.search(r"\bNOT_FOUND\b|\b404\b|does not exist", result.stderr):
                raise RuntimeError(f"probe failed: {operation['id']}")
            if not operation["command"]:
                raise RuntimeError("required existing database absent")
        command = operation["command"]
        command = [
            argument.replace("@lifecycle", files["lifecycle"]).replace("@cors", files["cors"])
            for argument in command
        ]
        result = execute(command)
        if result.returncode:
            raise RuntimeError(f"apply failed: {operation['id']}")
        print(json.dumps({"operation": operation["id"], "status": "applied"}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["foundation", "triggers"], default="foundation")
    parser.add_argument("--worker-url", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewed-plan-sha", default="")
    parser.add_argument("--artifacts", type=Path, default=Path(".tmp/app-infra-apply"))
    args = parser.parse_args()
    value = plan(args.phase, worker_url=args.worker_url)
    if args.apply:
        apply(value, args.reviewed_plan_sha, args.artifacts)
    else:
        print(json.dumps({"planSha256": plan_hash(value), "plan": value}, indent=2))


if __name__ == "__main__":
    main()
