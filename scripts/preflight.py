"""Cheap read-only serving checks. Full demo acceptance is deliberately separate."""

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 262144
API_HOSTS = {
    "relay-dev-api-798642284156.asia-south1.run.app",
    "relay-dev-api-asi34ncotq-el.a.run.app",
}
ARTIFACTS = (
    "docs/planning/CHECKPOINT.md",
    "docs/planning/DEV_DEPLOYMENT_EXECUTION.md",
    "docs/planning/M4_PHASE_REPORT.md",
    "docs/planning/M6_REGISTRY_HANDOFF.md",
    "eval/datasets/v1/cases.json",
    "eval/datasets/v1/manifest.json",
    "eval/reports/offline-fixture-v1/report.json",
    "eval/reports/offline-fixture-v1/report.md",
)


def origin(value, kind):
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        if (
            not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or "\\" in value
            or any(ord(char) <= 32 for char in value)
        ):
            raise ValueError()
        if host in {"localhost", "127.0.0.1", "::1"}:
            if parsed.scheme not in {"http", "https"} or port == 0:
                raise ValueError()
        else:
            web = host in {"work-511514.web.app", "work-511514.firebaseapp.com"} or bool(
                re.fullmatch(r"work-511514--relay-review-[a-z0-9-]{1,60}\.web\.app", host)
            )
            if (
                parsed.scheme != "https"
                or port not in {None, 443}
                or not (host in API_HOSTS if kind == "api" else web)
            ):
                raise ValueError()
        return value.rstrip("/")
    except (ValueError, TypeError):
        raise ValueError("origin_not_allowed") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, timeout):
    # Ignore proxy environment variables; do not forward credentials or follow redirects.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(
            Request(url, headers={"Accept": "application/json, text/html"}), timeout=timeout
        )
    except HTTPError as error:
        response = error
    with response:
        body = response.read(LIMIT + 1)
        if len(body) > LIMIT:
            raise ValueError("response_size_limit")
        return response.status, body


def local_checks(root):
    from packages.packs.registry import PackRegistry
    from scripts.export_contracts import outputs

    results: list[dict[str, Any]] = []
    try:
        generated = outputs()
        drift = any(
            not (root / path.relative_to(ROOT)).is_file()
            or (root / path.relative_to(ROOT)).read_text("utf-8") != content
            for path, content in generated.items()
        )
        results.append(
            {
                "id": "contracts",
                "status": "fail" if drift else "pass",
                "critical": True,
                "code": "contract_drift" if drift else "matched",
            }
        )
    except Exception:
        results.append(
            {"id": "contracts", "status": "fail", "critical": True, "code": "contract_check_failed"}
        )
    try:
        registry = PackRegistry(root / "packs").register_known("uk")
        options: dict[str, Any] = {
            "allow_draft_preview": True,
            "environment": "local",
            "demo_mode": True,
        }
        packs = registry.available(**options)
        results.append(
            {
                "id": "source_catalog",
                "status": "pass",
                "critical": True,
                "count": len(packs),
                "catalogHash": registry.catalog_hash(**options),
                "code": "integrity_checked_not_human_reviewed",
            }
        )
    except Exception:
        results.append(
            {
                "id": "source_catalog",
                "status": "fail",
                "critical": True,
                "code": "source_catalog_integrity_failure",
            }
        )
    for name in ARTIFACTS:
        results.append(
            {
                "id": name,
                "status": "artifact_present_not_validated"
                if (root / name).is_file()
                else "not_checked",
                "critical": False,
            }
        )
    return results


def run(api, web, *, root=ROOT, transport=fetch, checks=local_checks, timeout=5):
    api, web = origin(api, "api"), origin(web, "web")
    if not 0 < timeout <= 10:
        raise ValueError("timeout_out_of_bounds")
    results = checks(root)
    config = {}
    for name, base, path in (
        ("api_health", api, "/api/v1/healthz"),
        ("serving_readiness", api, "/api/v1/readyz"),
        ("version", api, "/api/v1/version"),
        ("public_config", api, "/api/v1/config/public"),
        ("hosting", web, "/"),
    ):
        result = {"id": name, "critical": True, "status": "fail"}
        try:
            status, raw = transport(base + path, timeout)
            if len(raw) > LIMIT:
                raise ValueError()
            data: Any = json.loads(raw) if name != "hosting" else {}
            valid = status == 200
            if name == "api_health":
                valid = valid and isinstance(data, dict) and data.get("status") == "ok"
            elif name == "serving_readiness":
                valid = valid and isinstance(data, dict) and data.get("status") == "ready"
                valid = valid and data.get("scope") == "serving_dependencies"
                deps = data.get("deps", {}) if isinstance(data, dict) else {}
                valid = valid and all(
                    deps.get(key) == "verified"
                    for key in ("firestore", "evidence_storage", "export_storage")
                )
                valid = valid and all(deps.get(key) == "configured" for key in ("pubsub", "genai"))
            elif name == "version":
                valid = (
                    valid
                    and isinstance(data, dict)
                    and all(
                        isinstance(data.get(key), str) and 0 < len(data[key]) <= 200
                        for key in ("gitSha", "builtAt")
                    )
                )
                valid = valid and data.get("gitSha") != "unknown"
            elif name == "public_config":
                keys = (
                    "demoMode",
                    "planningEnabled",
                    "packetsEnabled",
                    "liveEnabled",
                    "sourcesEnabled",
                    "packstudioEnabled",
                )
                valid = (
                    valid
                    and isinstance(data, dict)
                    and all(type(data.get(key)) is bool for key in keys)
                )
                if isinstance(data, dict) and any(key not in data for key in keys):
                    result["code"] = "deployed_schema_missing_feature_flags"
                if valid:
                    config = {key: data[key] for key in keys}
            elif name == "hosting":
                valid = valid and b"<html" in raw.lower() and b"<script" in raw.lower()
            result.update(status="pass" if valid else "fail", httpStatus=status)
            result.setdefault("code", "verified" if valid else "unexpected_response")
        except Exception:
            result["code"] = "probe_failed"
        results.append(result)
    for key in (
        "planningEnabled",
        "packetsEnabled",
        "liveEnabled",
        "sourcesEnabled",
        "packstudioEnabled",
    ):
        results.append(
            {
                "id": key,
                "critical": False,
                "status": "enabled_not_exercised"
                if config.get(key) is True
                else "disabled"
                if config.get(key) is False
                else "not_checked",
            }
        )
    for name in (
        "model_inference",
        "queue_delivery",
        "private_worker",
        "private_a2a",
        "seeded_data",
        "mock_adapters",
        "live_reply",
        "evaluation_report_loaded",
        "human_language_review",
        "submission_artifacts",
    ):
        results.append({"id": name, "status": "not_checked", "critical": False})
    return {
        "reportVersion": "read_only_preflight.v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "servingChecksPassed": not any(
            item["critical"] and item["status"] != "pass" for item in results
        ),
        "fullSpecGate": "unknown",
        "modelProbed": False,
        "checks": results,
    }


def output_path(root, value):
    root = root.resolve()
    path = Path(value).absolute()
    if not path.resolve().is_relative_to(root / ".tmp") or path.suffix != ".json":
        raise ValueError("output_must_be_json_within_tmp")
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("linked_output_forbidden")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--web", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args(argv)
    try:
        destination = output_path(ROOT, args.output)
        report = run(args.api, args.web, timeout=args.timeout)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "servingChecksPassed": report["servingChecksPassed"],
                    "fullSpecGate": report["fullSpecGate"],
                }
            )
        )
        return 0 if report["servingChecksPassed"] else 1
    except ValueError:
        print(json.dumps({"code": "invalid_preflight_arguments"}))
        return 2
    except Exception:
        print(json.dumps({"code": "preflight_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
