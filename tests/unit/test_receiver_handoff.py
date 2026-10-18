"""Durable victim-side outbox with actual SDK private receiver ASGI transport."""

import asyncio
import re
from datetime import timedelta

import httpx
import pytest

from packages.receiver.handoff import ReceiverHandoffService
from services.a2a_receiver.app import create_a2a_app
from services.a2a_receiver.client import A2AHandoffClient, HandoffUnavailable
from services.a2a_receiver.store import cleanup_case
from tests.unit.test_delivery_receiver_integration import flow, send  # noqa: F401


def enqueue(context, service):
    def write(tx):
        case = tx.get("cases/" + context.case_id)
        packet = tx.get(f"cases/{context.case_id}/packets/{context.packet['packetId']}")
        return service.enqueue(
            tx, case=case, packet=packet, projection_ref=case["receiverProjectionRefs"][0]
        )

    return context.repository.atomic(write)


def actual(context):
    app = create_a2a_app(
        context.repository,
        context.receiver,
        endpoint_url="http://127.0.0.1:8011/",
        runtime_mode="local",
        trusted_caller_scope="victim-api",
        allowed_orgs={"mock-bank"},
        private_iam=True,
    )
    client = A2AHandoffClient(
        "http://127.0.0.1:8011/",
        scope="victim-api",
        runtime_mode="local",
        transport=httpx.ASGITransport(app),
    )
    return ReceiverHandoffService(context.intake, client)


def test_approved_delivery_automatically_queues_worker_handoff_and_cascade_cleans(flow):  # noqa: F811
    from services.worker.http import dispatch_job

    c = flow
    c.intake.receiver_handoff = actual(c)
    send(c)
    case = c.repository.get("cases/" + c.case_id)
    jobs = [
        c.repository.get("jobs/" + ident)
        for ident in case["jobIds"]
        if c.repository.get("jobs/" + ident).get("type") == "handoff_receiver"
    ]
    assert len(jobs) == 1 and jobs[0]["state"] == "queued"
    assert asyncio.run(dispatch_job(c.intake, jobs[0]["jobId"])) is True
    assert c.repository.get("jobs/" + jobs[0]["jobId"])["state"] == "succeeded"
    assert c.packets.get(c.actor, c.case_id, c.packet["packetId"])["status"] == "SENT"
    assert any(path.startswith("a2aTasks/") for path in c.repository.documents)
    c.intake.delete_case(c.actor, c.case_id)
    assert c.repository.get("jobs/" + jobs[0]["jobId"]) is None
    assert not any(
        path.startswith(("a2aTasks/", "a2aMessages/")) for path in c.repository.documents
    )


def test_enqueue_before_rpc_real_sdk_restart_replay_and_cleanup(flow):  # noqa: F811
    c = flow
    send(c)
    service = actual(c)
    job_id = enqueue(c, service)
    assert re.fullmatch(r"job_[a-f0-9]{32}", job_id)
    case = c.repository.get("cases/" + c.case_id)
    assert len(case["a2aTaskRefs"]) == 1
    assert case["a2aTaskRefs"][0]["taskId"] == c.repository.get("jobs/" + job_id)["taskId"]
    assert not any(path.startswith("a2aTasks/") for path in c.repository.documents)
    assert enqueue(c, actual(c)) == job_id
    asyncio.run(actual(c).process(job_id))
    job = c.repository.get("jobs/" + job_id)
    assert job["state"] == "succeeded", job
    assert job["receipt"]["humanAcknowledged"] is False
    assert c.packets.get(c.actor, c.case_id, c.packet["packetId"])["status"] == "SENT"
    events = c.packets.events(c.actor, c.case_id)["items"]
    assert sum(event["action"] == "receiver.handoff_simulated" for event in events) == 1
    asyncio.run(actual(c).process(job_id))
    assert c.repository.get("jobs/" + job_id)["attempts"] == 1
    c.repository.atomic(lambda tx: cleanup_case(tx, c.case_id, case["a2aTaskRefs"]))
    c.intake.delete_case(c.actor, c.case_id)
    assert not any(
        path.startswith(("a2aTasks/", "a2aMessages/")) for path in c.repository.documents
    )


class BrokenClient:
    def __init__(self):
        self.calls = 0
        self.before = None

    async def send(self, reference, message_id):
        self.calls += 1
        if self.before:
            self.before()
        raise HandoffUnavailable("synthetic failure")


def test_retry_backoff_attempt_cap_and_no_duplicate_while_lease_active(flow):  # noqa: F811
    c = flow
    send(c)
    client = BrokenClient()
    service = ReceiverHandoffService(c.intake, client)
    job_id = enqueue(c, service)
    for attempt in range(3):
        asyncio.run(service.process(job_id))
        assert client.calls == attempt + 1
        asyncio.run(service.process(job_id))
        assert client.calls == attempt + 1
        c.clock[0] += timedelta(seconds=11)
    assert c.repository.get("jobs/" + job_id)["state"] == "failed"
    assert c.packets.get(c.actor, c.case_id, c.packet["packetId"])["status"] == "SENT"


@pytest.mark.parametrize("change", ["facts", "expiry", "deleting", "owner"])
def test_current_case_changes_prevent_dispatch(flow, change):  # noqa: F811
    c = flow
    send(c)
    client = BrokenClient()
    service = ReceiverHandoffService(c.intake, client)
    job_id = enqueue(c, service)
    case = c.repository.get("cases/" + c.case_id)
    if change == "facts":
        case["factsRevision"] += 1
        case["facts"]["ongoingContact"] = True
    elif change == "expiry":
        c.clock[0] += timedelta(hours=73)
    elif change == "deleting":
        case["deleting"] = True
    else:
        case["victimUid"] = "unrelated-owner"
    c.repository.set("cases/" + c.case_id, case)
    asyncio.run(service.process(job_id))
    assert client.calls == 0
    assert c.repository.get("jobs/" + job_id)["state"] == "failed"


def test_deletion_during_rpc_never_recreates_case_or_job(flow):  # noqa: F811
    c = flow
    send(c)
    client = BrokenClient()
    service = ReceiverHandoffService(c.intake, client)
    job_id = enqueue(c, service)
    client.before = lambda: c.intake.delete_case(c.actor, c.case_id)
    asyncio.run(service.process(job_id))
    assert c.repository.get("cases/" + c.case_id) is None
    assert c.repository.get("jobs/" + job_id) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid/",
        "http://127.0.0.1/",
        "https://x.run.app/?target=other",
        "https://u:p@x.run.app/",
    ],
)
def test_cloud_client_accepts_only_fixed_private_run_endpoint(url):
    with pytest.raises(ValueError):
        A2AHandoffClient(url, scope="victim-api")


def test_remote_receipt_survives_lost_response_and_retries_same_task(flow):  # noqa: F811
    c = flow
    send(c)
    sdk_client = actual(c).client

    class LostResponse:
        calls = 0

        async def send(self, reference, message_id):
            receipt = await sdk_client.send(reference, message_id)
            self.calls += 1
            if self.calls == 1:
                raise HandoffUnavailable("Synthetic process crash after durable receiver receipt")
            return receipt

    observed = LostResponse()
    service = ReceiverHandoffService(c.intake, observed)
    job_id = enqueue(c, service)
    asyncio.run(service.process(job_id))
    assert c.repository.get("jobs/" + job_id)["state"] == "queued"
    assert sum(path.startswith("a2aTasks/") for path in c.repository.documents) == 1
    c.clock[0] += timedelta(seconds=11)
    asyncio.run(ReceiverHandoffService(c.intake, observed).process(job_id))
    assert c.repository.get("jobs/" + job_id)["state"] == "succeeded"
    assert sum(path.startswith("a2aTasks/") for path in c.repository.documents) == 1
    assert (
        sum(
            event["action"] == "receiver.handoff_simulated"
            for event in c.packets.events(c.actor, c.case_id)["items"]
        )
        == 1
    )


def test_live_lease_then_expired_lease_only_dispatches_after_expiry(flow):  # noqa: F811
    c = flow
    send(c)
    client = BrokenClient()
    service = ReceiverHandoffService(c.intake, client)
    job_id = enqueue(c, service)
    record = c.repository.get("jobs/" + job_id)
    record.update(
        state="running", attempts=2, leaseUntil=(c.clock[0] + timedelta(seconds=30)).isoformat()
    )
    c.repository.set("jobs/" + job_id, record)
    asyncio.run(service.process(job_id))
    assert client.calls == 0
    c.clock[0] += timedelta(seconds=31)
    asyncio.run(service.process(job_id))
    assert client.calls == 1
    assert c.repository.get("jobs/" + job_id)["attempts"] == 3
    assert c.repository.get("jobs/" + job_id)["state"] == "failed"
