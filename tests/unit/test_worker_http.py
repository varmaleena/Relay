"""Private request worker behavior; no cloud, emulator or live model calls."""

import asyncio
import base64
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from packages.common.settings import Settings
from packages.intake.repository import MemoryRepository
from services.worker.http import DurableSweep, create_worker_app, validate_cloud_worker

JOB = "job_" + "a" * 32


@pytest.fixture(autouse=True)
def isolate_retention_unit_boundary(monkeypatch):
    # Retention's real query/cascade has its own tests. These fakes implement
    # job/name pagination only and must never select a cloud cleanup client.
    cleanup = AsyncMock()
    monkeypatch.setattr(DurableSweep, "_retention", cleanup)
    return cleanup


def cloud_config(**updates):
    # Explicit injected configuration isolates factory checks from real ADC.
    values: dict[str, Any] = dict(
        environment="dev",
        service="worker",
        auth_mode="firebase",
        genai_mode="live",
        intake_storage_mode="gcs",
        intake_enabled=True,
        gcp_project_id="synthetic-project",
    )
    return Settings.model_construct(**(values | updates))


class Query:
    def __init__(self, repo, collection, after=None):
        self.repo, self.name, self.after = repo, collection, after

    def document(self, ident):
        return SimpleNamespace(id=ident)

    def where(self, **kwargs):
        return self

    def order_by(self, field):
        assert field == "__name__"
        return self

    def limit(self, limit):
        assert limit == 25
        return self

    def start_after(self, cursor):
        self.after = cursor["__name__"].id
        return self

    def stream(self):
        documents = []
        for path, record in sorted(self.repo.documents.items()):
            prefix, ident = path.split("/", 1)
            if prefix != self.name or "/" in ident or (self.after and ident <= self.after):
                continue
            if self.name == "jobs" and record.get("state") not in {"queued", "running"}:
                continue
            documents.append(SimpleNamespace(id=ident, to_dict=lambda record=record: record))
        self.repo.page_sizes.append(min(25, len(documents)))
        return iter(documents[:25])


class Repository(MemoryRepository):
    def __init__(self):
        super().__init__()
        self.page_sizes = []
        self.client = SimpleNamespace(collection=lambda name: Query(self, name))


class Service:
    def __init__(self):
        self.repository = Repository()
        self.now = datetime.now(UTC)
        self.calls = []
        self.planning = SimpleNamespace(process_case=self.case)
        self.packets = None
        self.exception = False
        self.deferred_result = False
        self.wait = False

    def clock(self):
        return self.now

    async def complete(self, kind, job_id):
        self.calls.append((kind, job_id))
        if self.exception:
            raise RuntimeError("synthetic-private-data")
        if self.wait:
            await asyncio.sleep(60)
        self.repository.set(
            f"jobs/{job_id}",
            {"type": kind, "state": "queued" if self.deferred_result else "succeeded"},
        )

    async def process_evidence(self, job_id):
        await self.complete("process_evidence", job_id)

    async def case(self, job_id):
        await self.complete("process_case", job_id)


def push(job_id=JOB, **attribute_changes):
    return {
        "subscription": "projects/synthetic-project/subscriptions/relay-jobs",
        "message": {
            "data": base64.b64encode(json.dumps({"jobId": job_id}).encode()).decode(),
            "attributes": {
                "type": "process_case",
                "schemaVersion": "1",
                "caseId": "ignored-case",
                "traceId": "synthetic-trace",
                "idempotencyKey": job_id,
                **attribute_changes,
            },
        },
    }


def test_push_dispatches_repository_type_not_untrusted_attributes_and_replays_terminal_jobs():
    service = Service()
    service.repository.set(f"jobs/{JOB}", {"type": "process_evidence", "state": "queued"})
    with TestClient(create_worker_app(cloud_config(), service)) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.post("/pubsub/push", json=push()).status_code == 204
        assert client.post("/pubsub/push", json=push()).status_code == 204
    assert service.calls == [("process_evidence", JOB)]


@pytest.mark.parametrize(
    "state,fields,expected",
    [
        ("failed", {}, 204),
        ("succeeded", {}, 204),
        ("queued", {"retryAfter": "future"}, 503),
        ("running", {"leaseUntil": "future"}, 204),
        ("queued", {"leaseUntil": "future"}, 503),
    ],
)
def test_terminal_and_deferred_states_follow_ack_contract(state, fields, expected):
    service = Service()
    fields = {key: (service.now + timedelta(minutes=2)).isoformat() for key in fields}
    service.repository.set(f"jobs/{JOB}", {"type": "process_case", "state": state, **fields})
    with TestClient(create_worker_app(cloud_config(), service)) as client:
        response = client.post("/pubsub/push", json=push())
        assert response.status_code == expected
        if expected == 503:
            assert response.headers["Retry-After"] == "10"
    assert service.calls == []


@pytest.mark.parametrize("mode", ["exception", "deferred_result", "wait"])
def test_pending_or_timed_out_work_is_not_acknowledged(mode, monkeypatch):
    service = Service()
    setattr(service, mode, True)
    service.repository.set(f"jobs/{JOB}", {"type": "process_case", "state": "queued"})
    monkeypatch.setattr("services.worker.http.MAX_DISPATCH_SECONDS", 0.05)
    with TestClient(create_worker_app(cloud_config(), service)) as client:
        response = client.post("/pubsub/push", json=push())
        assert response.status_code == 503 and "synthetic-private-data" not in response.text


@pytest.mark.parametrize(
    "change",
    [
        "base64",
        "case_payload",
        "missing_attributes",
        "extra",
        "mismatch",
        "traversal",
        "version",
        "resource",
    ],
)
def test_push_envelope_is_bounded_strict_and_never_trusts_case_payload(change):
    body = push()
    if change == "base64":
        body["message"]["data"] = "not base64!"
    elif change == "case_payload":
        body["message"]["data"] = base64.b64encode(
            json.dumps({"jobId": JOB, "facts": {"secret": "x"}}).encode()
        ).decode()
    elif change == "missing_attributes":
        del body["message"]["attributes"]["traceId"]
    elif change == "extra":
        body["untrusted"] = "synthetic-private-data"
    elif change == "mismatch":
        body["message"]["attributes"]["idempotencyKey"] = "job_" + "b" * 32
    elif change == "traversal":
        body = push("../../cases/private")
    elif change == "version":
        body["message"]["attributes"]["schemaVersion"] = "2"
    else:
        del body["message"]["attributes"]["caseId"]
    with TestClient(create_worker_app(cloud_config(), Service())) as client:
        response = client.post("/pubsub/push", json=body)
    assert response.status_code == 400 and "synthetic-private-data" not in response.text


def test_streamed_body_bound_is_enforced_before_json_parse():
    with TestClient(create_worker_app(cloud_config(), Service())) as client:
        response = client.post("/pubsub/push", content=iter([b"x" * 9000, b"x" * 9000]))
    assert response.status_code == 413


def test_sweep_cursor_survives_new_handler_and_reaches_beyond_deferred_page():
    service = Service()
    for index in range(28):
        job_id = f"job_{index:032x}"
        record = {"type": "process_case", "state": "queued"}
        if index < 25:
            record["retryAfter"] = (service.now + timedelta(minutes=2)).isoformat()
        service.repository.set(f"jobs/{job_id}", record)
    asyncio.run(DurableSweep(service).run())
    assert service.calls == []
    cursor = service.repository.get("workerSweepState/jobs")
    assert cursor is not None and cursor["lastId"] == "job_" + f"{24:032x}"
    asyncio.run(DurableSweep(service).run())
    assert service.calls == [("process_case", "job_" + f"{25:032x}")]
    asyncio.run(DurableSweep(service).run())
    assert service.calls[-1] == ("process_case", "job_" + f"{26:032x}")
    assert len(service.calls) == 2 and max(service.repository.page_sizes) == 25


def test_failed_sweep_does_not_checkpoint_past_interrupted_job():
    service = Service()
    service.repository.set(f"jobs/{JOB}", {"type": "process_case", "state": "queued"})
    service.exception = True
    with TestClient(create_worker_app(cloud_config(), service)) as client:
        assert client.post("/internal/sweep", json={}).status_code == 503
        assert service.repository.get("workerSweepState/jobs") is None
        service.exception = False
        assert client.post("/internal/sweep", json={}).status_code == 204
        assert client.post("/internal/sweep", json={"caseId": "untrusted"}).status_code == 400
    assert len(service.calls) == 2


def test_factory_rejects_local_and_emulator_configuration_before_runtime(monkeypatch):
    with pytest.raises(ValueError, match="cloud worker"):
        create_worker_app(Settings(), Service())
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8095")
    with pytest.raises(ValueError, match="emulator"):
        validate_cloud_worker(cloud_config())


def test_expired_running_lease_is_reclaimed_instead_of_acknowledged_without_work():
    service = Service()
    service.repository.set(
        f"jobs/{JOB}",
        {
            "type": "process_case",
            "state": "running",
            "leaseUntil": (service.now - timedelta(seconds=1)).isoformat(),
        },
    )
    with TestClient(create_worker_app(cloud_config(), service)) as client:
        assert client.post("/pubsub/push", json=push()).status_code == 204
    assert service.calls == [("process_case", JOB)]


def test_deadline_sweep_is_bounded_and_has_durable_cold_start_continuation(monkeypatch):
    service = Service()
    service.packets = SimpleNamespace()
    checked = []
    monkeypatch.setattr(
        "packages.packets.deadlines.check_case_deadlines",
        lambda packets, case_id: checked.append(case_id),
    )
    for index in range(26):
        service.repository.set(f"cases/case_{index:032x}", {"synthetic": True})
    asyncio.run(DurableSweep(service).run())
    assert len(checked) == 25
    asyncio.run(DurableSweep(service).run())
    assert len(checked) == len(set(checked)) == 26
    assert max(service.repository.page_sizes) == 25


def test_sweep_request_time_bound_preserves_cursor_and_retries(monkeypatch):
    service = Service()
    service.wait = True
    service.repository.set(f"jobs/{JOB}", {"type": "process_case", "state": "queued"})
    monkeypatch.setattr("services.worker.http.MAX_SWEEP_SECONDS", 0.05)
    with TestClient(create_worker_app(cloud_config(), service)) as client:
        assert client.post("/internal/sweep").status_code == 503
    assert service.repository.get("workerSweepState/jobs") is None


def test_sweep_calls_one_retention_check_after_work(isolate_retention_unit_boundary):
    service = Service()
    asyncio.run(DurableSweep(service).run())
    isolate_retention_unit_boundary.assert_awaited_once()


def test_sweep_leaves_retention_for_next_request_if_time_budget_is_low(
    monkeypatch, isolate_retention_unit_boundary
):
    service = Service()
    monkeypatch.setattr("services.worker.http.time.monotonic", lambda: 0)
    monkeypatch.setattr("services.worker.http.MAX_SWEEP_SECONDS", 20)
    asyncio.run(DurableSweep(service).run())
    isolate_retention_unit_boundary.assert_not_awaited()


@pytest.mark.parametrize(
    "kind,method",
    [
        ("rebuild_packets", "process"),
        ("verify_packet", "process"),
        ("send_packet", "process_delivery"),
    ],
)
def test_push_dispatches_packet_job_variants_by_stored_kind(kind, method):
    service = Service()

    async def finish(job_id):
        await service.complete(kind, job_id)

    service.packets = SimpleNamespace(**{method: finish})
    service.repository.set(f"jobs/{JOB}", {"type": kind, "state": "queued"})
    with TestClient(create_worker_app(cloud_config(), service)) as client:
        assert client.post("/pubsub/push", json=push()).status_code == 204
    assert service.calls == [(kind, JOB)]


@pytest.mark.parametrize(
    "update",
    [
        {"service": "api"},
        {"genai_mode": "fake"},
        {"auth_mode": "emulator"},
        {"intake_storage_mode": "local"},
        {"gcp_project_id": "demo-synthetic"},
    ],
)
def test_cloud_worker_rejects_incorrect_runtime_modes(update):
    with pytest.raises(ValueError, match="cloud worker"):
        validate_cloud_worker(cloud_config(**update))


# Google Cloud push documentation, checked 17 October 2026:
# https://docs.cloud.google.com/pubsub/docs/push
# Keep the actual documented transport shapes. Relay intentionally requires
# its own strict job data/attributes instead of accepting arbitrary Hello data.
OFFICIAL_MINIMUM: dict[str, Any] = {
    "message": {
        "data": "SGVsbG8gQ2xvdWQgUHViL1N1YiEgSGVyZSBpcyBteSBtZXNzYWdlIQ==",
        "messageId": "2070443601311540",
        "message_id": "2070443601311540",
        "publishTime": "2021-02-26T19:13:55.749Z",
        "publish_time": "2021-02-26T19:13:55.749Z",
    },
    "subscription": "projects/myproject/subscriptions/mysubscription",
}
OFFICIAL_MAXIMUM: dict[str, Any] = {
    "deliveryAttempt": 5,
    "message": {
        "attributes": {"key": "value"},
        "data": "SGVsbG8gQ2xvdWQgUHViL1N1YiEgSGVyZSBpcyBteSBtZXNzYWdlIQ==",
        "messageId": "2070443601311540",
        "message_id": "2070443601311540",
        "orderingKey": "key",
        "publishTime": "2021-02-26T19:13:55.749Z",
        "publish_time": "2021-02-26T19:13:55.749Z",
    },
    "subscription": "projects/myproject/subscriptions/mysubscription",
}


@pytest.mark.parametrize("sample", [OFFICIAL_MINIMUM, OFFICIAL_MAXIMUM])
def test_documented_wrapped_push_shapes_dispatch_when_relay_payload_is_supplied(sample):
    service = Service()
    service.repository.set(f"jobs/{JOB}", {"type": "process_case", "state": "queued"})
    body = deepcopy(sample)
    relay = push()["message"]
    body["message"].update(data=relay["data"], attributes=relay["attributes"])
    with TestClient(create_worker_app(cloud_config(), service)) as client:
        assert client.get("/api/v1/healthz").json() == {"status": "ok"}
        assert client.post("/pubsub/push", json=body).status_code == 204
    assert service.calls == [("process_case", JOB)]


@pytest.mark.parametrize("sample", [OFFICIAL_MINIMUM, OFFICIAL_MAXIMUM])
def test_generic_documentation_payload_does_not_bypass_relay_job_contract(sample):
    service = Service()
    with TestClient(create_worker_app(cloud_config(), service)) as client:
        assert client.post("/pubsub/push", json=sample).status_code == 400
    assert service.calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("message_id", "different"),
        ("publish_time", "2021-02-26T19:13:56.749Z"),
        ("message_id", "x" * 129),
        ("publish_time", "x" * 81),
        ("ordering_key", "undocumented"),
    ],
)
def test_conflicting_oversized_or_undocumented_metadata_is_rejected(field, value):
    service = Service()
    body = deepcopy(OFFICIAL_MAXIMUM)
    body["message"].update(push()["message"])
    body["message"][field] = value
    with TestClient(create_worker_app(cloud_config(), service)) as client:
        assert client.post("/pubsub/push", json=body).status_code == 400
    assert service.calls == []
