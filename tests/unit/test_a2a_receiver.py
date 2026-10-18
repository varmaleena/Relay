"""Actual SDK JSON-RPC compatibility and durable addressed handoff semantics."""

import asyncio
from datetime import timedelta

import pytest
from a2a.server.context import ServerCallContext
from a2a.types import Message, Role
from a2a.utils.errors import InvalidParamsError, TaskNotFoundError
from fastapi.testclient import TestClient

from packages.intake.service import IntakeError
from services.a2a_receiver.app import create_a2a_app
from services.a2a_receiver.store import RepositoryTaskStore, cleanup_case, data_part
from tests.unit.test_receiver_service import setup, submitted  # noqa: F401


def reference():
    return {
        "orgId": "mock-bank",
        "caseId": "case_a",
        "packetId": "packet_a",
        "packetVersion": 1,
        "contentHash": submitted()["contentHash"],
    }


def store_for(context, *, orgs=None):
    return RepositoryTaskStore(
        context.repo, context.service, scope="victim-api", allowed_orgs=orgs or {"mock-bank"}
    )


def message(ref=None, message_id="message-a"):
    return Message(
        message_id=message_id, role=Role.ROLE_USER, parts=[data_part(ref or reference())]
    )


def test_durable_transport_receipt_replay_restart_no_human_ack(setup):  # noqa: F811
    store = store_for(setup)
    task = asyncio.run(store.send(message()))
    replay = asyncio.run(store_for(setup).send(message()))
    assert task == replay
    fetched = asyncio.run(store_for(setup).get(task.id, ServerCallContext()))
    assert fetched == task
    artifact = task.artifacts[0].parts[0].data.struct_value
    assert artifact["simulated"] is True
    assert artifact["humanAcknowledged"] is False
    assert artifact["transportStatus"] == "received"
    assert setup.service.queue(setup.actor)["items"][0]["status"] == "SENT"
    assert setup.adapter.calls == [] and setup.bridge == []


def test_message_id_conflict_scope_and_no_caller_case_data(setup):  # noqa: F811
    store = store_for(setup)
    asyncio.run(store.send(message()))
    altered = reference() | {"packetVersion": 2}
    setup.project(submitted(version=2))
    with pytest.raises(InvalidParamsError):
        asyncio.run(store.send(message(altered)))
    with pytest.raises(InvalidParamsError):
        asyncio.run(store.send(message(reference() | {"facts": {"victimName": "forbidden"}})))
    with pytest.raises(TaskNotFoundError):
        asyncio.run(store.send(message(reference() | {"orgId": "mock-cyber"})))


def test_expiry_changed_version_and_erasure_block_old_task(setup):  # noqa: F811
    store = store_for(setup)
    task = asyncio.run(store.send(message()))
    setup.project(submitted(version=2))
    with pytest.raises(TaskNotFoundError):
        asyncio.run(store.get(task.id, ServerCallContext()))
    setup.repo.atomic(lambda tx: cleanup_case(tx, "case_a", [{"taskId": task.id}]))
    assert not any(path.startswith(("a2aTasks/", "a2aMessages/")) for path in setup.repo.documents)
    task = asyncio.run(store.send(message(reference() | {"packetVersion": 2}, "message-b")))
    setup.clock[0] += timedelta(hours=3)
    with pytest.raises(TaskNotFoundError):
        asyncio.run(store.get(task.id, ServerCallContext()))


def test_sdk_agent_card_message_send_and_tasks_get(setup):  # noqa: F811
    app = create_a2a_app(
        setup.repo,
        setup.service,
        endpoint_url="http://127.0.0.1:8011/",
        runtime_mode="local",
        trusted_caller_scope="victim-api",
        allowed_orgs={"mock-bank"},
        private_iam=True,
    )
    with TestClient(app) as client:
        card = client.get("/.well-known/agent-card.json")
        assert card.status_code == 200, card.text
        assert card.json()["name"] == "Relay simulated receiver"
        payload = {
            "jsonrpc": "2.0",
            "id": "one",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": "sdk-a",
                    "role": "user",
                    "parts": [{"kind": "data", "data": reference()}],
                }
            },
        }
        response = client.post("/", json=payload)
        assert response.status_code == 200, response.text
        assert "result" in response.json(), response.text
        result = response.json()["result"]
        fetched = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": "two",
                "method": "tasks/get",
                "params": {"id": result["id"]},
            },
        )
        assert fetched.json()["result"]["id"] == result["id"], fetched.text
        assert fetched.json()["result"]["status"]["state"] == "completed"
        assert client.post("/", content=b"x" * 16385).status_code == 413


def test_concurrent_message_replay_only_one_brief_and_restart_recovers(setup):  # noqa: F811
    calls = []

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def brief(projection):
            calls.append(projection)
            entered.set()
            await release.wait()
            return setup.service._basic_brief(projection)

        setup.service.brief_maker = brief
        original = asyncio.create_task(store_for(setup).send(message()))
        await entered.wait()
        waiting = await store_for(setup).send(message())
        assert waiting.status.state == 2  # SDK TASK_STATE_WORKING
        release.set()
        completed = await original
        replay = await store_for(setup).send(message())
        assert completed == replay

    asyncio.run(scenario())
    assert len(calls) == 1


def test_projection_change_during_brief_does_not_commit_stale_task(setup):  # noqa: F811
    async def brief(projection):
        setup.project(submitted(version=2))
        return setup.service._basic_brief(projection)

    setup.service.brief_maker = brief
    with pytest.raises(IntakeError):
        asyncio.run(store_for(setup).send(message()))
    task_records = [
        value for path, value in setup.repo.documents.items() if path.startswith("a2aTasks/")
    ]
    assert len(task_records) == 1 and task_records[0]["state"] == "working"
    assert task_records[0]["task"]["status"]["state"] == "TASK_STATE_WORKING"


def test_missing_fields_transport_needsinfo_is_not_human_request(setup):  # noqa: F811
    setup.project(submitted(version=2, missing=True))
    ref = reference() | {"packetVersion": 2, "contentHash": submitted(missing=True)["contentHash"]}
    task = asyncio.run(store_for(setup).send(message(ref)))
    value = task.artifacts[0].parts[0].data.struct_value
    assert value["transportStatus"] == "needs_info"
    assert value["humanAcknowledged"] is False
    assert not any("/requests/" in path for path in setup.repo.documents)
    assert setup.service.queue(setup.actor)["items"][0]["status"] == "SENT"


@pytest.mark.parametrize(
    "private,runtime,url",
    [
        (False, "cloud", "https://receiver.example.invalid/"),
        (True, "cloud", "http://127.0.0.1/"),
        (True, "cloud", "https://receiver.example.invalid/"),
        (True, "local", "https://receiver.example.invalid/"),
    ],
)
def test_factory_cannot_fake_private_cloud_durable_runtime(setup, private, runtime, url):  # noqa: F811
    with pytest.raises(ValueError):
        create_a2a_app(
            setup.repo,
            setup.service,
            endpoint_url=url,
            runtime_mode=runtime,
            trusted_caller_scope="victim-api",
            allowed_orgs={"mock-bank"},
            private_iam=private,
        )


def test_current_protocol_sdk_send_get_and_errors_do_not_log_payload(setup, caplog):  # noqa: F811
    app = create_a2a_app(
        setup.repo,
        setup.service,
        endpoint_url="http://127.0.0.1:8011/",
        runtime_mode="local",
        trusted_caller_scope="victim-api",
        allowed_orgs={"mock-bank"},
        private_iam=True,
    )
    with TestClient(app) as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "current",
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "current-a",
                    "role": "ROLE_USER",
                    "parts": [{"data": reference(), "mediaType": "application/json"}],
                }
            },
        }
        reply = client.post("/", headers={"A2A-Version": "1.0"}, json=payload)
        assert "result" in reply.json(), reply.text
        task_id = reply.json()["result"]["task"]["id"]
        task = client.post(
            "/",
            headers={"A2A-Version": "1.0"},
            json={"jsonrpc": "2.0", "id": "get", "method": "GetTask", "params": {"id": task_id}},
        )
        assert task.json()["result"]["id"] == task_id, task.text
        bad = client.post(
            "/", json={"jsonrpc": "2.0", "id": "SYNTHETIC-PRIVATE-ID", "method": "unavailable"}
        )
        assert "error" in bad.json()
        assert "SYNTHETIC-PRIVATE-ID" not in caplog.text


def test_interrupted_task_lease_recovers_after_restart_with_attempt_bound(setup):  # noqa: F811
    store = store_for(setup)
    completed = asyncio.run(store.send(message()))
    path = "a2aTasks/" + completed.id
    record = setup.repo.get(path)
    record.update(state="working", attempts=1, leaseUntil="2099-01-01T00:00:00Z")
    setup.repo.atomic(lambda tx: tx.set(path, record))
    replay = asyncio.run(store_for(setup).send(message()))
    assert setup.repo.get(path)["attempts"] == 1
    assert replay.id == completed.id
    record["leaseUntil"] = "2000-01-01T00:00:00Z"
    setup.repo.atomic(lambda tx: tx.set(path, record))
    recovered = asyncio.run(store_for(setup).send(message()))
    assert recovered.id == completed.id
    assert setup.repo.get(path)["attempts"] == 2
    record.update(attempts=3)
    setup.repo.atomic(lambda tx: tx.set(path, record))
    with pytest.raises(InvalidParamsError):
        asyncio.run(store_for(setup).send(message()))


@pytest.mark.parametrize("task_id", ["a2a_" + "a/" * 32, "a2a_" + "G" * 64, "a2a_" + "a" * 63])
def test_noncanonical_task_identifier_never_reaches_repository(setup, task_id):  # noqa: F811
    class RejectReads:
        def get(self, path):
            pytest.fail("Invalid task identifier reached repository")

    store = store_for(setup)
    with pytest.raises(TaskNotFoundError):
        store._record(RejectReads(), task_id)
    with pytest.raises(ValueError):
        cleanup_case(RejectReads(), "case_a", [{"taskId": task_id}])
