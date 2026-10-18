import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from packages.evaluation import EvaluationService
from packages.evaluation.service import PRODUCT_SYSTEMS, REPORT_PATH, RUN_ID
from packages.intake.service import IntakeError
from packages.safety import Actor
from services.api.evaluation.router import create_evaluation_router

ROOT = Path(__file__).resolve().parents[2]
REVIEWER = Actor("synthetic-reviewer", "reviewer", "review-org")
ADMIN = Actor("synthetic-admin", "admin", "review-org")


@pytest.fixture
def service(tmp_path):
    target = tmp_path / REPORT_PATH
    target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / REPORT_PATH, target)
    return EvaluationService(tmp_path)


def test_exact_report_metrics_and_unknowns_are_preserved_without_product_claims(service):
    report = service.report(REVIEWER, RUN_ID)
    raw = json.loads((ROOT / REPORT_PATH).read_text("utf-8"))
    fixture = raw["systems"][-1]
    assert report["n"] == fixture["n"] == 20 and report["executionMode"] == "offline_fixture"
    public = report["captureReport"]
    assert public["synthetic"] is True and public["executionMode"] == "offline_fixture"
    assert {
        s["system"] for s in public["systems"] if s["status"] == "not_measured"
    } == PRODUCT_SYSTEMS
    assert public["systems"][-1]["modelId"] == "none-canned-evaluator-fixture"
    for actual, expected in zip(public["systems"][-1]["metrics"], fixture["metrics"], strict=True):
        assert all(
            actual[key] == expected[key]
            for key in ("metric", "value", "ciLow", "ciHigh", "n", "status")
        )
    assert report["latency"]["status"] == report["costPerCase"]["status"] == "not_measured"
    assert "failureGallery" not in str(public) and "prediction" not in str(public)


@pytest.mark.parametrize(
    "actor,status",
    [
        (None, 401),
        (Actor("synthetic", "victim"), 403),
        (Actor("synthetic", "receiver", "mock-bank"), 403),
    ],
)
def test_roles_and_public_opt_in_are_separate(service, actor, status):
    for operation in (
        lambda: service.report(actor, RUN_ID),
        lambda: service.runs(actor),
        lambda: service.failures(actor, RUN_ID),
    ):
        with pytest.raises(IntakeError) as error:
            operation()
        assert error.value.status == status
    service.public_eval = True
    assert service.report(None, RUN_ID)["runId"] == RUN_ID
    with pytest.raises(IntakeError):
        service.runs(None)
    with pytest.raises(IntakeError):
        service.failures(None, RUN_ID)


@pytest.mark.parametrize("change", ["raw_content", "oversize", "missing", "product_claim"])
def test_unreviewed_artifact_changes_fail_closed_without_leaking(service, change):
    path = service.root / REPORT_PATH
    if change == "missing":
        path.unlink()
    elif change == "oversize":
        path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    else:
        raw = json.loads(path.read_text("utf-8"))
        if change == "raw_content":
            raw["privateToken"] = "must-not-leak"
        else:
            raw["systems"][0]["status"] = "measured_captures"
        path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(IntakeError) as error:
        service.report(REVIEWER, RUN_ID)
    assert error.value.status == 503 and "must-not-leak" not in str(error.value)


def test_no_user_path_and_cursor_filter_injection(service):
    for name in ("../private", "other-run", "offline-fixture-v1/report.json"):
        with pytest.raises(IntakeError) as error:
            service.report(REVIEWER, name)
        assert error.value.status == 404
    for kwargs in (
        {"cursor": "../../private"},
        {"limit": 0},
        {"limit": 101},
        {"slice": "country:IN"},
        {"system": "unknown"},
        {"metric": "secret"},
    ):
        with pytest.raises(IntakeError) as error:
            service.failures(REVIEWER, RUN_ID, **kwargs)
        assert error.value.status == 422


def test_sanitized_failure_gallery_pagination_and_product_empty(service):
    first = service.failures(REVIEWER, RUN_ID, limit=1)
    second = service.failures(REVIEWER, RUN_ID, limit=1, cursor=first["nextCursor"])
    assert first["items"][0]["caseId"] != second["items"][0]["caseId"]
    for item in first["items"] + second["items"]:
        assert item["expected"] is item["actual"] is None
        assert item["inputRef"] == "synthetic_fixture_input_withheld"
        assert item["note"].startswith("Offline evaluator fixture;")
    assert service.failures(REVIEWER, RUN_ID, system="relay")["items"] == []
    assert service.runs(REVIEWER, cursor="100")["items"] == []


def client(service, actor):
    app = FastAPI()

    @app.middleware("http")
    async def fixture_identity(request: Request, call_next):
        request.state.actor = actor
        return await call_next(request)

    @app.exception_handler(IntakeError)
    async def error(request, error):
        return JSONResponse({"code": error.code}, status_code=error.status)

    app.include_router(create_evaluation_router(service))
    return TestClient(app)


def test_actual_read_only_router_response_and_explicit_unimplemented_executor(service):
    authenticated = client(service, REVIEWER)
    assert authenticated.get("/api/v1/eval/runs").status_code == 200
    response = authenticated.get("/api/v1/eval/runs/" + RUN_ID)
    assert response.status_code == 200
    assert response.json()["captureReport"]["executionMode"] == "offline_fixture"
    assert authenticated.get(f"/api/v1/eval/runs/{RUN_ID}/failures?limit=1").status_code == 200
    body = {"kind": "smoke", "datasetVersion": "synthetic-templates.v1", "systems": ["relay"]}
    assert authenticated.post("/api/v1/eval/runs", json=body).status_code == 403
    assert client(service, ADMIN).post("/api/v1/eval/runs", json=body).status_code == 501
    assert client(service, None).get("/api/v1/eval/runs/" + RUN_ID).status_code == 401
    service.public_eval = True
    assert client(service, None).get("/api/v1/eval/runs/" + RUN_ID).status_code == 200
    assert client(service, None).get("/api/v1/eval/runs").status_code == 401


def test_public_opt_in_requires_boolean(tmp_path):
    with pytest.raises(ValueError):
        EvaluationService(tmp_path, public_eval="false")
