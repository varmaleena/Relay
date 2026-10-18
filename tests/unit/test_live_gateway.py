"""Synthetic WebSocket/SDK transport tests; never invokes a model."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agents.intake.live import LiveIntakeTools
from packages.common.auth import AuthenticationError
from packages.intake.repository import MemoryRepository
from packages.intake.service import IntakeError, IntakeService
from packages.intake.storage import LocalFileBlobStore
from packages.safety import Actor
from services.live_gateway import (
    GatewayConfig,
    GoogleLiveProvider,
    LiveSessionRegistry,
    create_live_gateway,
)


class Verifier:
    def __init__(self, actor):
        self.actor, self.calls = actor, []

    async def verify(self, id_token, app_check_token):
        self.calls.append((id_token, app_check_token))
        if id_token != "synthetic-id" or app_check_token != "synthetic-appcheck":
            raise AuthenticationError("unauthenticated")
        return self.actor


class Connection:
    def __init__(self, events):
        self.queue = asyncio.Queue()
        for event in events:
            self.queue.put_nowait(event)
        self.audio, self.text, self.responses, self.muted = [], [], [], []

    async def send_audio(self, audio):
        self.audio.append(audio)

    async def send_text(self, text):
        self.text.append(text)
        self.queue.put_nowait({"type": "output_text", "text": "How did you pay?"})
        self.queue.put_nowait({"type": "audio", "audio": b"\x00\x00" * 320})
        self.queue.put_nowait({"type": "turn_complete"})

    async def mute(self, muted):
        self.muted.append(muted)

    async def tool_response(self, call_id, name, result):
        self.responses.append((call_id, name, result))

    async def events(self):
        while True:
            yield await self.queue.get()


class Provider:
    def __init__(self, events=()):
        self.initial = events
        self.calls, self.closed = [], False
        self.connection = None

    @asynccontextmanager
    async def connect(self, **kwargs):
        self.calls.append(kwargs)
        self.connection = Connection(self.initial)
        try:
            yield self.connection
        finally:
            self.closed = True


@pytest.fixture
def context(tmp_path):
    repo = MemoryRepository()
    clock = [datetime.now(UTC)]
    intake = IntakeService(
        repo,
        LocalFileBlobStore(tmp_path, "http://127.0.0.1", b"x" * 32),
        None,
        None,
        clock=lambda: clock[0],
    )
    actor = Actor("synthetic-live-victim", "victim")
    case_id = intake.create_case(actor, {"language": "en", "consentVersion": "1.0"}, str(uuid4()))[
        "caseId"
    ]
    verifier = Verifier(actor)
    return SimpleNamespace(
        intake=intake, repo=repo, actor=actor, case_id=case_id, clock=clock, verifier=verifier
    )


def app(c, *, provider=None, **options):
    c.provider = provider or Provider()
    c.registry = LiveSessionRegistry(c.intake)
    return create_live_gateway(
        intake=c.intake,
        verifier=c.verifier,
        provider=c.provider,
        registry=c.registry,
        config=GatewayConfig(allowed_origins=("https://relay.test",), **options),
    )


def start(ws, c, **options):
    ws.send_json({"type": "auth", "idToken": "synthetic-id", "appCheckToken": "synthetic-appcheck"})
    ws.send_json(
        {
            "type": "start",
            "caseId": c.case_id,
            "language": "en",
            "audio": {"encoding": "pcm_s16le", "sampleRateHz": 16000, "channels": 1},
            **options,
        }
    )
    assert ws.receive_json()["type"] == "ready"
    script = ws.receive_json()
    assert script["type"] == "caption" and "Stop contact" in script["text"]


def close_reason(ws, code):
    result = ws.receive_json()
    assert result["type"] == "closed"
    with pytest.raises(WebSocketDisconnect) as error:
        ws.receive_json()
    assert error.value.code == code
    return result["reason"]


def test_safe_text_and_buffered_audio_use_auth_and_release_lease(context):
    c = context
    with TestClient(app(c)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            ws.send_json({"type": "text", "text": "I paid by UPI."})
            assert ws.receive_json()["role"] == "user"
            assert ws.receive_json()["text"] == "How did you pay?"
            assert ws.receive_bytes() == b"\0\0" * 320
            ws.send_json({"type": "end"})
            assert close_reason(ws, 1000) == "ended"
    assert c.verifier.calls == [("synthetic-id", "synthetic-appcheck")]
    assert c.provider.closed
    assert not any(path.startswith("liveSessions/") for path in c.repo.documents)
    assert c.provider.connection.text == ["I paid by UPI."]


@pytest.mark.parametrize(
    "kind", ["missing_appcheck", "wrong_id", "first_not_auth", "timeout", "origin", "role", "owner"]
)
def test_auth_first_origin_role_and_owner_fail_closed(context, kind):
    c = context
    if kind == "role":
        c.verifier.actor = Actor("synthetic-officer", "receiver", "mock-bank")
    if kind == "owner":
        c.verifier.actor = Actor("someone-else", "victim")
    with TestClient(app(c, auth_timeout=0.08)) as client:
        if kind == "origin":
            with pytest.raises(WebSocketDisconnect) as error:
                with client.websocket_connect(
                    "/live/v1/session", headers={"origin": "https://evil.test"}
                ):
                    pass
            assert error.value.code == 4403
        else:
            with client.websocket_connect(
                "/live/v1/session", headers={"origin": "https://relay.test"}
            ) as ws:
                if kind not in {"timeout", "role", "owner"}:
                    auth = {
                        "type": "auth",
                        "idToken": "synthetic-id",
                        "appCheckToken": "synthetic-appcheck",
                    }
                    if kind == "missing_appcheck":
                        auth["appCheckToken"] = ""
                    elif kind == "wrong_id":
                        auth["idToken"] = "wrong"
                    elif kind == "first_not_auth":
                        auth = {"type": "start"}
                    ws.send_json(auth)
                elif kind in {"role", "owner"}:
                    ws.send_json(
                        {
                            "type": "auth",
                            "idToken": "synthetic-id",
                            "appCheckToken": "synthetic-appcheck",
                        }
                    )
                    if kind == "owner":
                        ws.send_json(
                            {
                                "type": "start",
                                "caseId": c.case_id,
                                "language": "en",
                                "audio": {
                                    "encoding": "pcm_s16le",
                                    "sampleRateHz": 16000,
                                    "channels": 1,
                                },
                            }
                        )
                close_reason(ws, 4403 if kind in {"role", "owner"} else 4401)
    assert c.provider.calls == []


@pytest.mark.parametrize(
    "message",
    [
        {"type": "auth"},
        {"type": "send"},
        {"type": "text", "text": "ok", "caseId": "other"},
        {"type": "mute", "muted": "false"},
        ["not-object"],
    ],
)
def test_unknown_or_malformed_control_cannot_escalate(context, message):
    c = context
    with TestClient(app(c)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            ws.send_json(message)
            close_reason(ws, 4001)
    assert c.provider.connection.responses == []


def test_bad_audio_and_control_size_are_rejected(context):
    c = context
    with TestClient(app(c)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            ws.send_bytes(b"too-small")
            close_reason(ws, 4001)
    assert c.provider.connection.audio == []


def test_heartbeat_two_missed_pongs_and_duration_are_bounded(context):
    c = context
    with TestClient(app(c, heartbeat_seconds=0.03)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            assert ws.receive_json()["type"] == "ping"
            ws.send_json({"type": "pong"})
            assert ws.receive_json()["type"] == "ping"
            assert ws.receive_json()["type"] == "ping"
            close_reason(ws, 4008)
    with TestClient(app(c, max_session_seconds=0.04)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            close_reason(ws, 4408)


def test_secret_text_never_reaches_upstream_or_durable_storage(context):
    c = context
    with TestClient(app(c)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            ws.send_json({"type": "text", "text": "My OTP is 123456"})
            assert ws.receive_json()["code"] == "unsafe_content_blocked"
    assert c.provider.connection.text == []
    assert "123456" not in str(c.repo.documents)


@pytest.mark.parametrize(
    "text", ["Send me your OTP.", "Your money will be recovered.", "My password is secret-value"]
)
def test_unsafe_output_never_plays_audio_or_leaks_text(context, text):
    c = context
    provider = Provider(
        [
            {"type": "audio", "audio": b"\0\0" * 320},
            {"type": "output_text", "text": text},
            {"type": "turn_complete"},
        ]
    )
    with TestClient(app(c, provider=provider)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            assert close_reason(ws, 4500) == "unsafe_content_blocked"
    assert text not in str(c.repo.documents)


def test_interrupted_output_discards_pending_audio(context):
    c = context
    provider = Provider(
        [
            {"type": "audio", "audio": b"\0\0" * 320},
            {"type": "output_text", "text": "Old sentence."},
            {"type": "interrupted"},
            {"type": "output_text", "text": "How did you pay?"},
            {"type": "turn_complete"},
        ]
    )
    with TestClient(app(c, provider=provider)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            assert ws.receive_json() == {"type": "interrupted"}
            assert ws.receive_json()["text"] == "How did you pay?"
            ws.send_json({"type": "end"})
            close_reason(ws, 1000)


def test_audio_without_transcript_cannot_play(context):
    c = context
    with TestClient(
        app(
            c,
            provider=Provider(
                [{"type": "audio", "audio": b"\0\0" * 320}, {"type": "turn_complete"}]
            ),
        )
    ) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            close_reason(ws, 4500)


def test_registry_global_limit_owner_language_expiry_single_use_and_retry_cap(context):
    c = context
    registry = LiveSessionRegistry(c.intake)
    leases = [registry.acquire(c.actor, c.case_id, "en") for _ in range(3)]
    with pytest.raises(IntakeError):
        registry.acquire(c.actor, c.case_id, "en")
    for lease in leases:
        registry.release(lease)
    lease = registry.acquire(c.actor, c.case_id, "en")
    for _ in range(3):
        resume = registry.resumption(lease, "upstream-secret-handle")
        registry.release(lease)
        with pytest.raises(IntakeError):
            registry.acquire(Actor("other", "victim"), c.case_id, "en", resume["handle"])
        with pytest.raises(IntakeError):
            registry.acquire(c.actor, c.case_id, "hi", resume["handle"])
        lease = registry.acquire(c.actor, c.case_id, "en", resume["handle"])
        with pytest.raises(IntakeError):
            registry.acquire(c.actor, c.case_id, "en", resume["handle"])
    resume = registry.resumption(lease, "upstream-secret-handle")
    registry.release(lease)
    with pytest.raises(IntakeError):
        registry.acquire(c.actor, c.case_id, "en", resume["handle"])
    assert resume["handle"] != "upstream-secret-handle"


def test_registry_expired_resume_and_lease_cannot_extend_absolute_session(context):
    c = context
    registry = LiveSessionRegistry(c.intake)
    lease = registry.acquire(c.actor, c.case_id, "en")
    resume = registry.resumption(lease, "opaque-upstream")
    registry.release(lease)
    c.clock[0] += timedelta(seconds=121)
    with pytest.raises(IntakeError):
        registry.acquire(c.actor, c.case_id, "en", resume["handle"])


def test_thin_tools_cannot_confirm_send_override_confirmed_or_store_secrets(context):
    c = context
    c.intake.update_facts(c.actor, c.case_id, {"facts": {"payment": {"method": "upi"}}})
    tools = LiveIntakeTools(c.intake, c.actor, c.case_id, "en")
    tools.caption("user", "I am in India. I paid by card.")
    result = tools.call(
        "record_facts",
        {
            "facts": {
                "payment": {"method": "card"},
                "country": {"value": "IN", "provenance": {"source": "confirmed"}},
            }
        },
        "call1",
    )
    assert result["facts"]["payment"]["method"] == "upi"
    assert result["facts"]["country"]["provenance"]["source"] == "victim_statement"
    assert (
        tools.call(
            "record_facts",
            {
                "facts": {
                    "payment": {"method": "card"},
                    "country": {"value": "IN", "provenance": {"source": "confirmed"}},
                }
            },
            "call1",
        )
        == result
    )
    with pytest.raises(IntakeError):
        tools.call("record_facts", {"facts": {}, "source": "confirmed"}, "call2")
    with pytest.raises(IntakeError):
        tools.call("send_packet", {}, "call3")
    with pytest.raises(IntakeError):
        tools.call("record_facts", {"facts": {"notes": "My OTP is 123456"}}, "call4")
    with pytest.raises(IntakeError):
        tools.call("record_facts", {"facts": {}}, "call1")


@pytest.mark.parametrize("text", ["I cannot go on", "मुझे जीना नहीं", "jeena nahi"])
def test_distress_stops_collection_and_processing_without_invented_resource(context, text):
    c = context
    tools = LiveIntakeTools(c.intake, c.actor, c.case_id, "en")
    assert tools.observe(text)["distress"]
    assert (
        tools.call("record_facts", {"facts": {"country": {"value": "IN"}}}, "r")["reason_if_not"]
        == "distress_paused"
    )
    assert tools.call("request_processing", {}, "p")["reason_if_not"] == "distress_paused"
    assert c.repo.get(f"cases/{c.case_id}")["flags"]["distress"]
    assert "emergency" in tools.distress_reply


def test_sdk_adapter_requires_explicit_verified_config_and_builds_only_known_tools(context):
    with pytest.raises(ValueError):
        GoogleLiveProvider(None, "gemini-3.8-live")
    with pytest.raises(ValueError):
        GoogleLiveProvider(None, "gemini-2.5-live", capabilities_verified=True)
    seen = {}

    class Live:
        @asynccontextmanager
        async def connect(self, *, model, config):
            seen.update(model=model, config=config)
            yield SimpleNamespace()

    client = SimpleNamespace(aio=SimpleNamespace(live=Live()))
    provider = GoogleLiveProvider(client, "gemini-3-test-live", capabilities_verified=True)

    async def scenario():
        tools = LiveIntakeTools(context.intake, context.actor, context.case_id, "en")
        async with provider.connect(tools=tools, language="en"):
            pass

    asyncio.run(scenario())
    assert {tool.name for tool in seen["config"].tools[0].function_declarations} == {
        "record_facts",
        "flag_distress",
        "request_upload",
        "request_processing",
    }
    assert seen["config"].thinking_config is None
    assert seen["model"] == "gemini-3-test-live"


def test_registry_indexes_cascade_cleanup_and_cannot_extend_case_expiry(context):
    c = context
    path = f"cases/{c.case_id}"
    case = c.repo.get(path)
    case["accessExpiresAtMs"] = int((c.clock[0] + timedelta(seconds=45)).timestamp() * 1000)
    c.repo.set(path, case)
    registry = LiveSessionRegistry(c.intake)
    lease = registry.acquire(c.actor, c.case_id, "en")
    assert datetime.fromisoformat(lease["expiresAt"].replace("Z", "+00:00")) <= c.clock[
        0
    ] + timedelta(seconds=45)
    resume = registry.resumption(lease, "private-provider-handle")
    with pytest.raises(IntakeError):
        registry.acquire(c.actor, c.case_id, "en", resume["handle"])
    case = c.repo.get(path)
    assert case["liveSessionRefs"] == [lease["sessionId"]]
    assert len(case["liveResumeRefs"]) == 1
    c.repo.atomic(
        lambda tx: registry.cleanup_case(
            tx,
            c.case_id,
            {"sessions": case["liveSessionRefs"], "resumptions": case["liveResumeRefs"]},
        )
    )
    assert not any(
        p.startswith(("liveSessions/", "liveResumptions/", "liveUsers/")) for p in c.repo.documents
    )
    with pytest.raises(IntakeError):
        registry.acquire(c.actor, c.case_id, "en", resume["handle"])


def test_provider_tool_allowlist_facts_and_upload_only(context):
    c = context
    provider = Provider(
        [
            {"type": "input_text", "text": "I am in India.", "final": True},
            {
                "type": "tool",
                "id": "facts1",
                "name": "record_facts",
                "arguments": {"facts": {"country": {"value": "IN"}}},
            },
            {
                "type": "tool",
                "id": "upload1",
                "name": "request_upload",
                "arguments": {"kind": "screenshot"},
            },
            {"type": "tool", "id": "bad1", "name": "place_hold", "arguments": {}},
            {"type": "output_text", "text": "How did you pay?"},
            {"type": "turn_complete"},
        ]
    )
    with TestClient(app(c, provider=provider)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            assert ws.receive_json()["role"] == "user"
            assert ws.receive_json()["type"] == "facts_delta"
            assert ws.receive_json() == {"type": "upload_requested", "kind": "screenshot"}
            assert ws.receive_json()["text"] == "How did you pay?"
            ws.send_json({"type": "end"})
            close_reason(ws, 1000)
    assert provider.connection.responses[-1][2]["code"] == "tool_limit"
    assert provider.connection.responses[-1][2]["status"] == "limit_reached"
    assert provider.connection.responses[-1][2]["retryable"] is False
    assert all(
        {"status", "retryable", "message"} <= set(r[2]) for r in provider.connection.responses
    )
    assert (
        c.repo.get(f"cases/{c.case_id}")["facts"]["country"]["provenance"]["source"]
        == "victim_statement"
    )


def test_speech_distress_discards_audio_and_collection_reply(context):
    c = context
    provider = Provider(
        [
            {"type": "input_text", "text": "I cannot go on", "final": True},
            {"type": "audio", "audio": b"\0\0" * 320},
            {"type": "output_text", "text": "How much did you pay?"},
            {"type": "turn_complete"},
        ]
    )
    with TestClient(app(c, provider=provider)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            assert ws.receive_json()["role"] == "user"
            assert ws.receive_json()["type"] == "distress_ack"
            assert "emergency" in ws.receive_json()["text"]
            ws.send_json({"type": "end"})
            close_reason(ws, 1000)
    assert "How much did you pay?" not in str(c.repo.documents)


def test_speech_secret_caption_is_scrubbed_before_persistence_and_no_audio(context):
    c = context
    provider = Provider(
        [
            {"type": "audio", "audio": b"\0\0" * 320},
            {"type": "input_text", "text": "My PIN is 7391", "final": True},
        ]
    )
    with TestClient(app(c, provider=provider)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            assert "7391" not in ws.receive_json()["text"]
            close_reason(ws, 4500)
    assert all(
        "7391" not in item["text"]
        for path, item in c.repo.documents.items()
        if "/transcript/" in path
    )


def test_processing_reuses_existing_domain_job_and_never_sets_approval(tmp_path):
    from tests.unit.test_packet_service import make_packet_context

    c = make_packet_context(tmp_path)
    tools = LiveIntakeTools(
        c.intake, c.actor, c.case_id, "en", processing_options={"previewDraft": True}
    )
    before = list(c.repository.documents)
    first = tools.call("request_processing", {}, "call1")
    second = tools.call("request_processing", {}, "call2")
    assert first["queued"] and first["jobId"] == second["jobId"]
    assert set(c.repository.documents) == set(before)
    assert not any(
        "approvals/" in path or path.startswith("mockDeliveries/")
        for path in c.repository.documents
    )


def test_oversize_control_and_output_audio_fail_bounded(context):
    c = context
    with TestClient(app(c)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            ws.send_text("x" * 20001)
            close_reason(ws, 4001)
    with TestClient(
        app(
            c,
            provider=Provider([{"type": "audio", "audio": b"\0" * 4802}]),
            max_output_audio_bytes=4800,
        )
    ) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            close_reason(ws, 4500)


def test_third_consecutive_tool_cannot_mutate_and_safe_completed_reply_resets_limit(context):
    c = context
    provider = Provider(
        [
            {"type": "input_text", "text": "I am in India.", "final": True},
            {
                "type": "tool",
                "id": "a",
                "name": "request_upload",
                "arguments": {"kind": "screenshot"},
            },
            {"type": "tool", "id": "b", "name": "request_upload", "arguments": {"kind": "receipt"}},
            {
                "type": "tool",
                "id": "c",
                "name": "record_facts",
                "arguments": {"facts": {"country": {"value": "GB"}}},
            },
            {"type": "output_text", "text": "How did you pay?"},
            {"type": "turn_complete"},
            {"type": "input_text", "text": "I am in India.", "final": True},
            {
                "type": "tool",
                "id": "d",
                "name": "record_facts",
                "arguments": {"facts": {"country": {"value": "IN"}}},
            },
        ]
    )
    with TestClient(app(c, provider=provider)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            start(ws, c)
            assert ws.receive_json()["role"] == "user"
            assert ws.receive_json()["type"] == "upload_requested"
            assert ws.receive_json()["type"] == "upload_requested"
            assert ws.receive_json()["text"] == "How did you pay?"
            assert ws.receive_json()["role"] == "user"
            assert ws.receive_json()["facts"]["country"]["value"] == "IN"
            ws.send_json({"type": "end"})
            close_reason(ws, 1000)
    responses = provider.connection.responses
    assert responses[2][2]["status"] == "limit_reached" and responses[2][2]["retryable"] is False
    assert responses[3][2]["status"] == "ok"
    assert "GB" not in str(c.repo.documents)


def test_record_facts_waits_for_real_final_caption_then_binds_exact_server_reference(context):
    from agents.intake.live import live_tool_response

    c = context
    tools = LiveIntakeTools(c.intake, c.actor, c.case_id, "en")
    arguments = {
        "facts": {
            "contact": {"claimedIdentity": "Test Bank"},
            "fieldProvenance": {
                "contact.claimed_identity": {"source": "confirmed", "reference": "invented"}
            },
        }
    }
    original = c.repo.get(f"cases/{c.case_id}")
    pending = tools.call("record_facts", arguments, "same-call")
    assert pending == {"ok": False, "reason_if_not": "transcription_pending"}
    assert live_tool_response(pending)["retryable"] is True
    assert c.repo.get(f"cases/{c.case_id}")["facts"] == original["facts"]
    # An assistant sentence is never victim evidence.
    tools.caption("assistant", "How did they contact you?")
    assert tools.call("record_facts", arguments, "same-call") == pending
    turn_id = tools.caption("user", "The caller claimed to be Test Bank.")
    result = tools.call("record_facts", arguments, "same-call")
    assert result["ok"]
    case = c.repo.get(f"cases/{c.case_id}")
    origin = case["facts"]["fieldProvenance"]["contact.claimedIdentity"]
    assert origin["source"] == "victim_statement"
    assert origin["reference"] == f"case:{c.case_id}:turn:{turn_id}:facts:{case['factsRevision']}"
    assert c.repo.get(f"cases/{c.case_id}/transcript/{turn_id}")["role"] == "user"
    tools.begin_statement()
    assert (
        tools.call("record_facts", {"facts": {"victimBank": "New Bank"}}, "new-call")[
            "reason_if_not"
        ]
        == "transcription_pending"
    )


def test_caption_binding_cannot_use_deleted_or_superseded_victim_turn(context):
    c = context
    tools = LiveIntakeTools(c.intake, c.actor, c.case_id, "en")
    turn = tools.caption("user", "I am in India.")
    c.repo.atomic(lambda tx: tx.delete(f"cases/{c.case_id}/transcript/{turn}"))
    assert not tools.call("record_facts", {"facts": {"country": {"value": "IN"}}}, "call1")["ok"]
    other_session = LiveIntakeTools(c.intake, c.actor, c.case_id, "en")
    tools.caption("user", "I am in India.")
    other_session.caption("user", "I have a different detail to report.")
    assert not tools.call("record_facts", {"facts": {"country": {"value": "IN"}}}, "call2")["ok"]


def test_legacy_statement_is_not_repaired_by_repeated_live_extraction(context):
    c = context
    path = f"cases/{c.case_id}"
    case = c.repo.get(path)
    case["facts"]["contact"]["claimedIdentity"] = "Test Bank"
    case["facts"]["fieldProvenance"]["contact.claimedIdentity"] = {"source": "victim_statement"}
    c.repo.set(path, case)
    tools = LiveIntakeTools(c.intake, c.actor, c.case_id, "en")
    tools.caption("user", "The caller claimed to be Test Bank.")
    result = tools.call(
        "record_facts", {"facts": {"contact": {"claimedIdentity": "Test Bank"}}}, "repeat"
    )
    assert result["ok"]
    origin = c.repo.get(path)["facts"]["fieldProvenance"]["contact.claimedIdentity"]
    assert origin.get("reference") is None


def test_actual_packet_verifier_accepts_live_turn_origin_and_blocks_legacy_unknown(
    tmp_path, monkeypatch
):
    from itertools import count
    from uuid import UUID

    from agents.packets import PacketPipeline
    from tests.unit.test_packet_agents import Client
    from tests.unit.test_packet_service import make_packet_context

    # Keep opaque fixture IDs reproducible: random hex can contain card-shaped digit runs.
    # Production credential controls remain conservative and unchanged.
    sequence = count(1)
    monkeypatch.setattr(
        "packages.common.identifiers.uuid4",
        lambda: UUID(hex=f"aaaaaaaaaaaaaaaaaaaaaaaa{next(sequence):08x}"),
    )
    c = make_packet_context(tmp_path)
    path = f"cases/{c.case_id}"
    # New-case fixture has no statement about the claimed identity yet.
    case = c.repository.get(path)
    case["facts"]["contact"]["claimedIdentity"] = None
    for alias in ("contact.claimedIdentity", "contact.claimed_identity"):
        case["facts"]["fieldProvenance"].pop(alias, None)
    c.repository.set(path, case)
    c.intake.update_facts(
        c.actor,
        c.case_id,
        {
            "facts": {
                "payment": {
                    "transactionRef": "TEST0000000001",
                    "recipientIdentifier": {"type": "upi", "value": "safe.verify@fakebank"},
                },
                "victimBank": "Test Bank",
            }
        },
    )
    tools = LiveIntakeTools(c.intake, c.actor, c.case_id, "en")
    turn = tools.caption("user", "The caller claimed to be Test Bank.")
    assert tools.call(
        "record_facts", {"facts": {"contact": {"claimedIdentity": "Test Bank"}}}, "new-statement"
    )["ok"]
    job = c.planning.enqueue(c.actor, c.case_id, {"previewDraft": True})
    asyncio.run(c.planning.process_case(job["jobId"]))
    plan = c.planning.get_plan(c.actor, c.case_id)
    case = c.repository.get(path)
    context = c.packets._context(case, plan, "bank")
    origin = context["facts"].field_provenance["contact.claimed_identity"]
    assert f":turn:{turn}:facts:" in origin.reference
    pipeline = PacketPipeline(Client())
    result = asyncio.run(pipeline.build(**context))
    assert result.status == "VERIFIED", [
        (item.id, item.detail) for item in result.checks if not item.passed
    ]
    # Unknown legacy origins remain blockers; no cite wrapper/reference guessing.
    context["facts"].field_provenance["contact.claimed_identity"].reference = None
    blocked = asyncio.run(pipeline.build(**context))
    assert blocked.status == "NEEDS_HUMAN_REVIEW"
    assert any(not check.passed and check.id == "provenance" for check in blocked.checks)


def test_cached_upload_cannot_bypass_later_distress_pause(context):
    c = context
    tools = LiveIntakeTools(c.intake, c.actor, c.case_id, "en")
    assert tools.call("request_upload", {"kind": "screenshot"}, "same-id")["upload_prompt_shown"]
    tools.observe("I cannot go on")
    assert tools.call("request_upload", {"kind": "screenshot"}, "same-id") == {
        "ok": False,
        "reason_if_not": "distress_paused",
    }


def test_resumed_distress_case_starts_with_support_not_deadline_pressure(context):
    c = context
    LiveIntakeTools(c.intake, c.actor, c.case_id, "en").observe("I cannot go on")
    with TestClient(app(c)) as client:
        with client.websocket_connect(
            "/live/v1/session", headers={"origin": "https://relay.test"}
        ) as ws:
            ws.send_json(
                {"type": "auth", "idToken": "synthetic-id", "appCheckToken": "synthetic-appcheck"}
            )
            ws.send_json(
                {
                    "type": "start",
                    "caseId": c.case_id,
                    "language": "en",
                    "audio": {"encoding": "pcm_s16le", "sampleRateHz": 16000, "channels": 1},
                }
            )
            assert ws.receive_json()["type"] == "ready"
            assert "emergency" in ws.receive_json()["text"]
            ws.send_json({"type": "end"})
            close_reason(ws, 1000)
