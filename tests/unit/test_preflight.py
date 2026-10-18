import json

import pytest

from scripts.preflight import LIMIT, NoRedirect, origin, output_path, run


def transport(url, timeout):
    assert 0 < timeout <= 30
    if url.endswith("/healthz"):
        data = {"status": "ok"}
    elif url.endswith("/readyz"):
        data = {
            "status": "ready",
            "scope": "serving_dependencies",
            "deps": {
                "firestore": "verified",
                "evidence_storage": "verified",
                "export_storage": "verified",
                "pubsub": "configured",
                "genai": "configured",
            },
        }
    elif url.endswith("/version"):
        data = {"gitSha": "synthetic-stage", "builtAt": "2026-10-18T00:00:00Z"}
    elif url.endswith("/public"):
        data = {
            "demoMode": True,
            "planningEnabled": True,
            "packetsEnabled": True,
            "liveEnabled": False,
            "sourcesEnabled": False,
            "packstudioEnabled": False,
            "ignoredSecret": "not-copied",
        }
    else:
        return 200, b"<html><script src='/asset.js'></script></html>"
    return 200, json.dumps(data).encode()


def test_serving_checks_do_not_imply_inference_or_full_acceptance():
    calls = []

    def observed(url, timeout):
        calls.append(url)
        return transport(url, timeout)

    report = run(
        "http://127.0.0.1:8000", "http://localhost:5173", transport=observed, checks=lambda _: []
    )
    assert report["servingChecksPassed"] and report["fullSpecGate"] == "unknown"
    assert report["modelProbed"] is False and len(calls) == 5
    statuses = {item["id"]: item["status"] for item in report["checks"]}
    assert statuses["model_inference"] == statuses["private_worker"] == "not_checked"
    assert statuses["liveEnabled"] == "disabled"
    assert statuses["planningEnabled"] == "enabled_not_exercised"
    assert "ignoredSecret" not in str(report) and "not-copied" not in str(report)


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com",
        "https://evil.run.app",
        "https://work-511514.web.app.evil.org",
        "https://user:password@work-511514.web.app",
        "http://169.254.169.254",
        "http://127.0.0.1:8000/private",
        "http://127.0.0.1:8000?token=secret",
        "http://127.0.0.1:8000#secret",
        "https://work-511514.web.app:8080",
        "http://2130706433",
        "file:///etc/passwd",
        "http://localhost:0",
    ],
)
def test_fail_closed_origins_before_any_request(value):
    with pytest.raises(ValueError, match="origin_not_allowed"):
        run(value, value, transport=lambda *_: pytest.fail("must not fetch"), checks=lambda _: [])


def test_exact_project_origins_and_private_services_excluded():
    assert origin("https://relay-dev-api-798642284156.asia-south1.run.app", "api")
    assert origin("https://work-511514--relay-review-example.web.app", "web")
    with pytest.raises(ValueError):
        origin("https://relay-dev-worker-asi34ncotq-el.a.run.app", "api")
    assert NoRedirect().redirect_request(None, None, None, None, None, "https://evil.test") is None


@pytest.mark.parametrize(
    "behavior", ["unready", "unknown_version", "oversize", "exception", "redirect"]
)
def test_critical_failure_returns_false_and_redacts_raw_errors(behavior):
    def failed(url, timeout):
        if url.endswith("/readyz"):
            if behavior == "unready":
                return 503, b'{"status":"not_ready"}'
            if behavior == "unknown_version":
                return 200, b'{"status":"ready","scope":"serving_dependencies","deps":{}}'
            if behavior == "oversize":
                return 200, b"x" * (LIMIT + 1)
            if behavior == "exception":
                raise RuntimeError("private token and signed URL must not leak")
            return 302, b"{}"
        return transport(url, timeout)

    report = run(
        "http://localhost:8000", "http://localhost:5173", transport=failed, checks=lambda _: []
    )
    assert report["servingChecksPassed"] is False
    assert "private token" not in str(report) and "signed URL" not in str(report)


def test_safe_output_and_no_unbounded_timeout(tmp_path):
    with pytest.raises(ValueError):
        output_path(tmp_path, tmp_path / "private.json")
    assert output_path(tmp_path, tmp_path / ".tmp/report.json")
    with pytest.raises(ValueError):
        run("http://localhost", "http://localhost", timeout=31, checks=lambda _: [])


def test_cli_writes_machine_report_and_returns_nonzero_on_critical_failure(tmp_path, monkeypatch):
    from scripts import preflight

    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setattr(
        preflight,
        "run",
        lambda *args, **kwargs: {
            "servingChecksPassed": False,
            "fullSpecGate": "unknown",
            "checks": [],
        },
    )
    destination = tmp_path / ".tmp/preflight.json"
    assert (
        preflight.main(
            [
                "--api",
                "http://localhost:8000",
                "--web",
                "http://localhost:5173",
                "--output",
                str(destination),
            ]
        )
        == 1
    )
    assert json.loads(destination.read_text())["fullSpecGate"] == "unknown"


def test_missing_deployed_flags_are_diagnosed_without_assuming_disabled():
    def older_config(url, timeout):
        status, data = transport(url, timeout)
        if url.endswith("/public"):
            config = json.loads(data)
            del config["sourcesEnabled"]
            del config["packstudioEnabled"]
            return status, json.dumps(config).encode()
        return status, data

    report = run(
        "http://localhost", "http://localhost", transport=older_config, checks=lambda _: []
    )
    check = next(item for item in report["checks"] if item["id"] == "public_config")
    assert check["code"] == "deployed_schema_missing_feature_flags"
    assert check["status"] == "fail" and report["servingChecksPassed"] is False
    status = next(item for item in report["checks"] if item["id"] == "sourcesEnabled")["status"]
    assert status == "not_checked"
