"""Namespace safety with actual intake domain and synthetic agents, no inference."""

from uuid import uuid4

import pytest

from packages.demo.service import DemoControl
from packages.intake.service import IntakeError
from packages.safety import Actor
from tests.unit.test_intake_service import setup as intake_fixture

ADMIN = Actor("synthetic-operator", "admin")
NS = "synthetic-rehearsal"


@pytest.fixture
def context(tmp_path):
    intake, repo, blobs, text, evidence, victim, unrelated, clock = intake_fixture.__wrapped__(
        tmp_path
    )
    control = DemoControl(
        intake,
        namespace=NS,
        victim=victim,
        demo_mode=True,
        configured={"model": True, "warehouse": False},
    )
    return control, intake, repo, victim, unrelated, text, evidence


def load(c, name="asha_in_hi_voice", key=None):
    return c.load(ADMIN, NS, name, key or str(uuid4()))


def test_load_is_fresh_synthetic_domain_state_idempotent_and_no_model(context):
    c, intake, repo, victim, unrelated, text, evidence = context
    key = str(uuid4())
    first = load(c, key=key)
    assert load(c, key=key) == first
    case = repo.get(f"cases/{first['caseId']}")
    assert case["victimUid"] == victim.uid and case["demoFixture"]["synthetic"] is True
    assert case["language"] == "hi" and case["demoInputMode"] == "voice"
    assert case["facts"]["payment"]["amount"]["value"] == "45000"
    assert case.get("plan") is None and case.get("classification") is None
    assert text.calls == evidence.calls == 0
    assert repo.get(f"cases/{unrelated}")
    with pytest.raises(IntakeError) as error:
        load(c, "daniel_uk_text", key)
    assert error.value.code == "idempotency_conflict"


@pytest.mark.parametrize("role", ["victim", "receiver", "agent"])
def test_only_admin_can_rehearse(context, role):
    c = context[0]
    with pytest.raises(IntakeError):
        c.load(Actor("other", role), NS, "generic_fragmented", str(uuid4()))


def test_off_mode_namespace_other_admin_and_invalid_scenario(context):
    c = context[0]
    c.demo_mode = False
    with pytest.raises(IntakeError) as error:
        load(c)
    assert error.value.status == 404
    c.demo_mode = True
    with pytest.raises(IntakeError):
        c.load(ADMIN, "synthetic-other", "generic_fragmented", str(uuid4()))
    load(c)
    with pytest.raises(IntakeError):
        c.load(Actor("other-admin", "admin"), NS, "generic_fragmented", str(uuid4()))
    with pytest.raises(IntakeError) as error:
        load(c, "unknown")
    assert error.value.status == 404


def test_reset_deletes_only_marked_namespace_and_reseeds_four(context):
    c, intake, repo, victim, unrelated, text, evidence = context
    original = load(c)["caseId"]
    key = str(uuid4())
    with pytest.raises(IntakeError):
        c.reset(ADMIN, NS, key, "wrong")
    assert c.reset(ADMIN, NS, key, NS) == {"seeded": True}
    assert c.reset(ADMIN, NS, key, NS) == {"seeded": True}
    assert repo.get(f"cases/{original}") is None
    assert repo.get(f"cases/{unrelated}") is not None
    ids = repo.get(c.path)["caseIds"]
    assert len(ids) == 4
    assert {repo.get(f"cases/{case_id}")["demoFixture"]["scenario"] for case_id in ids} == set(
        ["asha_in_hi_voice", "daniel_uk_text", "generic_fragmented", "injection_attempt"]
    )
    assert text.calls == evidence.calls == 0


def test_reset_rejects_tampered_crossowner_target_before_any_delete(context):
    c, _, repo, _, unrelated, _, _ = context
    owned = load(c)["caseId"]
    record = repo.get(c.path)
    record["caseIds"].append(unrelated)
    repo.set(c.path, record)
    with pytest.raises(IntakeError) as error:
        c.reset(ADMIN, NS, str(uuid4()), NS)
    assert error.value.code == "demo_target_not_owned"
    assert repo.get(f"cases/{owned}") and repo.get(f"cases/{unrelated}")


def test_stale_load_replay_and_forced_needs_info_fail_honestly(context):
    c, _, repo, _, _, _, _ = context
    key = str(uuid4())
    created = load(c, key=key)
    repo.delete(f"cases/{created['caseId']}")
    with pytest.raises(IntakeError) as error:
        load(c, key=key)
    assert error.value.code == "demo_scenario_stale"
    with pytest.raises(IntakeError) as error:
        c.behavior(ADMIN, NS, {"bankMode": "needs_info", "railMode": "success"}, str(uuid4()))
    assert error.value.status == 501


def test_supported_behavior_is_typed_for_actual_mock_projection(context):
    c, _, repo, _, _, _, _ = context
    case_id = load(c)["caseId"]
    data = {"bankMode": "funds_moved", "railMode": "misrouted"}
    key = str(uuid4())
    assert c.behavior(ADMIN, NS, data, key) == {"status": "ok"}
    assert c.behavior(ADMIN, NS, data, key) == {"status": "ok"}
    simulation = repo.atomic(lambda tx: c.simulation_for(tx, repo.get(f"cases/{case_id}")))
    assert simulation.bank_mode == "funds_moved" and simulation.rail_mode == "misrouted"
    assert repo.atomic(lambda tx: c.simulation_for(tx, {"caseId": "other"})) is None


def test_overview_distinguishes_configured_measured_and_replay_unavailable(context):
    c = context[0]
    result = c.overview(ADMIN, NS)
    assert result["runLabel"] == "LIVE" and result["qualityGate"] == "not_measured"
    assert result["dependencies"]["model"] == {"configured": True, "measured": False}
    assert result["cachedOutputsAvailable"] is False and result["evaluationRunSeeded"] is False
    with pytest.raises(ValueError):
        DemoControl(c.intake, namespace=NS, victim=c.victim, demo_mode=True, genai_mode="replay")


def test_http_control_requires_namespace_uuid_and_reset_confirmation(context):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from services.api.demo.router import create_demo_router

    c = context[0]
    app = FastAPI()

    @app.middleware("http")
    async def auth(request: Request, call_next):
        request.state.actor = ADMIN
        return await call_next(request)

    @app.exception_handler(IntakeError)
    async def error(request, exc):
        return JSONResponse({"code": exc.code}, status_code=exc.status)

    app.include_router(create_demo_router(c))
    client = TestClient(app)
    url = "/api/v1/demo/scenarios/generic_fragmented/load"
    assert client.post(url, json={}).status_code == 422
    headers = {"X-Demo-Namespace": NS, "Idempotency-Key": str(uuid4())}
    loaded = client.post(url, json={}, headers=headers)
    assert loaded.status_code == 201 and loaded.json()["caseId"].startswith("case_")
    assert client.post("/api/v1/demo/reset", json={}, headers=headers).status_code == 422
    c.demo_mode = False
    headers["Idempotency-Key"] = str(uuid4())
    assert client.post(url, json={}, headers=headers).status_code == 404


def test_domain_configuration_reaches_actual_registered_mock_adapter(context, tmp_path):
    import asyncio

    from packages.delivery.adapter import LocalMCPDeliveryAdapter
    from tests.unit.test_mock_delivery import projection
    from tests.unit.test_mock_delivery import setup as mock_fixture

    c, _, repo, _, _, _, _ = context
    case_id = load(c)["caseId"]
    c.behavior(ADMIN, NS, {"bankMode": "funds_moved", "railMode": "misrouted"}, str(uuid4()))
    simulation = repo.atomic(lambda tx: c.simulation_for(tx, repo.get(f"cases/{case_id}")))
    mock, _, _ = mock_fixture.__wrapped__(tmp_path / "mock")
    adapter = LocalMCPDeliveryAdapter(mock)
    packet = projection(simulation=simulation.model_dump(mode="json", by_alias=True))
    receipt = asyncio.run(adapter.deliver(packet, "synthetic-demo-control"))
    hold = asyncio.run(
        adapter.place_hold(packet.owner_uid, packet.case_id, receipt.delivery_id, "synthetic-hold")
    )
    assert hold.status == "FUNDS_ALREADY_MOVED" and hold.simulated is True


def test_reset_marker_race_rejected_at_actual_deletion_transaction(context, monkeypatch):
    c, intake, repo, _, _, _, _ = context
    case_id = load(c)["caseId"]
    original = intake.delete_case

    def changed_before_mark(actor, target, *, expected_demo_marker=None):
        case = repo.get(f"cases/{target}")
        case["demoFixture"]["namespace"] = "synthetic-other"
        repo.set(f"cases/{target}", case)
        return original(actor, target, expected_demo_marker=expected_demo_marker)

    monkeypatch.setattr(intake, "delete_case", changed_before_mark)
    with pytest.raises(IntakeError):
        c.reset(ADMIN, NS, str(uuid4()), NS)
    case = repo.get(f"cases/{case_id}")
    assert case and not case.get("deleting")


def test_active_operation_and_capacity_fail_before_case_creation(context):
    c, _, repo, _, _, _, _ = context
    key = str(uuid4())
    c._reserve(ADMIN, NS, key, "load", "asha_in_hi_voice")
    with pytest.raises(IntakeError) as error:
        load(c)
    assert error.value.code == "demo_operation_running"
    record = repo.get(c.path)
    record["active"] = None
    record["caseIds"] = [f"synthetic_case_{i}" for i in range(20)]
    repo.set(c.path, record)
    before = len(repo.documents)
    with pytest.raises(IntakeError) as error:
        load(c)
    assert error.value.code == "demo_case_capacity_reached"
    assert len(repo.documents) == before
