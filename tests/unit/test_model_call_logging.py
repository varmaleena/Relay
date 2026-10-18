"""Actual SDK invocation logging is bounded and contains no user/provider prose."""

import asyncio
import io
import json
import logging
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from agents.intake.clients import GoogleGenAIClient, ModelFailure
from agents.intake.core import EvidenceModelOutput, IntakeModelOutput
from agents.packets.core import EntailmentOutput, WriterOutput
from packages.common.logging import SafeJsonFormatter, emit_model_call
from packages.common.settings import Settings
from packages.schemas import Classification


@pytest.fixture
def log_capture():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SafeJsonFormatter())
    logger = logging.getLogger("relay.model")
    old_handlers, old_level, old_propagate = logger.handlers[:], logger.level, logger.propagate
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield stream
    finally:
        logger.handlers = old_handlers
        logger.setLevel(old_level)
        logger.propagate = old_propagate


def make_client(generate):
    sdk = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    return GoogleGenAIClient(
        Settings(
            genai_mode="live",
            intake_enabled=True,
            gcp_project_id="demo-relay-local",
            genai_location="global",
            model_reasoning="gemini-3.8-flash",
            packet_thinking_level="LOW",
            max_model_concurrency=1,
        ),
        sdk_client=sdk,
    )


def rows(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


@pytest.mark.parametrize(
    "schema,agent,packet",
    [
        (IntakeModelOutput, "IntakeTextAgent", False),
        (EvidenceModelOutput, "EvidenceAgent", False),
        (Classification, "ClassifierAgent", False),
        (WriterOutput, "PacketAgent", True),
        (EntailmentOutput, "VerifierAgent", True),
    ],
)
def test_one_success_event_per_actual_call_both_profiles(log_capture, schema, agent, packet):
    async def generate_content(**kwargs):
        return SimpleNamespace(
            text="sensitive output never logged",
            usage_metadata=SimpleNamespace(
                prompt_token_count=12, candidates_token_count=7, thoughts_token_count=3
            ),
        )

    client = make_client(generate_content)
    assert rows(log_capture) == []
    target = client.for_packets() if packet else client
    assert rows(log_capture) == []
    asyncio.run(
        target.generate(
            prompt="OTP123456 system prompt", data={"secret": "passwordSecret"}, schema=schema
        )
    )
    records = rows(log_capture)
    assert len(records) == 1
    assert records[0]["event"] == "model.call" and records[0]["agent"] == agent
    assert records[0]["model_id"] == "gemini-3.8-flash" and records[0]["status"] == "ok"
    assert records[0]["tokens_in"] == 12 and records[0]["tokens_out"] == 7
    assert records[0]["tokens_reasoning"] == 3
    assert "latency_ms" in records[0]
    for secret in ["OTP123456", "passwordSecret", "sensitive output", "system prompt"]:
        assert secret not in log_capture.getvalue()


@pytest.mark.parametrize("code", [400, 429, 499, 503, 504])
def test_failed_provider_event_never_logs_error_body_or_headers(log_capture, code):
    class ProviderError(Exception):
        message = "passwordSecret OTP123456 https://example.com/?X-Goog-Signature=secret"
        headers = {"Authorization": "Bearer secret"}

    error = ProviderError("raw secret exception")
    error.code = code

    async def generate_content(**kwargs):
        raise error

    client = make_client(generate_content)
    with pytest.raises(ModelFailure):
        asyncio.run(
            client.generate(
                prompt="secret prompt", data={"password": "secret"}, schema=IntakeModelOutput
            )
        )
    records = rows(log_capture)
    assert len(records) == 1 and records[0]["status"] == "failed"
    assert records[0]["http_status"] == code
    assert records[0]["failure_reason"] == ("http_other" if code == 499 else f"http_{code}")
    assert "tokens_in" not in records[0]
    for secret in [
        "passwordSecret",
        "OTP123456",
        "Bearer",
        "X-Goog",
        "raw secret",
        "secret prompt",
    ]:
        assert secret not in log_capture.getvalue()


@pytest.mark.parametrize(
    "text,reason",
    [(None, "empty_response"), ("x" * 100001, "oversized_response")],
    ids=["empty", "oversized"],
)
def test_empty_or_oversized_response_exactly_one_failed_event(log_capture, text, reason):
    async def generate_content(**kwargs):
        return SimpleNamespace(text=text, usage_metadata=None)

    with pytest.raises(ModelFailure):
        asyncio.run(
            make_client(generate_content).generate(
                prompt="synthetic", data={}, schema=IntakeModelOutput
            )
        )
    records = rows(log_capture)
    assert len(records) == 1 and records[0]["failure_reason"] == reason


def test_cancellation_logs_once_for_invoked_sdk_and_never_for_queue_wait(log_capture):
    async def scenario():
        started = asyncio.Event()

        async def generate_content(**kwargs):
            started.set()
            await asyncio.sleep(60)

        client = make_client(generate_content)
        first = asyncio.create_task(
            client.generate(prompt="secret", data={}, schema=IntakeModelOutput)
        )
        await started.wait()
        queued = asyncio.create_task(
            client.generate(prompt="secret", data={}, schema=IntakeModelOutput)
        )
        await asyncio.sleep(0)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        assert rows(log_capture) == []
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

    asyncio.run(scenario())
    records = rows(log_capture)
    assert len(records) == 1 and records[0]["failure_reason"] == "cancelled"


def test_malicious_model_unknown_schema_and_numerical_metadata_filtered(log_capture):
    class OTP123456(BaseModel):
        value: str

    async def generate_content(**kwargs):
        return SimpleNamespace(
            text="secret output",
            usage_metadata=SimpleNamespace(
                prompt_token_count="passwordSecret",
                candidates_token_count=True,
                thoughts_token_count=1 << 1000,
            ),
        )

    client = make_client(generate_content)
    client.model_id = "gemini-3.8-flash\npasswordSecret"
    asyncio.run(client.generate(prompt="secret prompt", data={}, schema=OTP123456))
    record = rows(log_capture)[0]
    assert record["event"] == "model.call"
    assert not {"model_id", "agent", "tokens_in", "tokens_out", "tokens_reasoning"} & record.keys()
    assert (
        "passwordSecret" not in log_capture.getvalue() and "OTP123456" not in log_capture.getvalue()
    )
    emit_model_call(
        model_id="gemini-3.8-flash",
        http_status=99,
        tokens_reasoning=-1,
        failure_reason="passwordSecret",
        status="ok",
        prompt="OTP123456",
    )
    assert (
        not {"http_status", "tokens_reasoning", "failure_reason", "prompt"}
        & rows(log_capture)[1].keys()
    )


def test_deferred_dispatch_event_is_static_and_drops_job_body():
    record = logging.LogRecord("relay", logging.INFO, "", 0, "job.dispatch_deferred", (), None)
    record.job = {"password": "passwordSecret"}
    record.error_body = "OTP123456"
    encoded = SafeJsonFormatter().format(record)
    assert json.loads(encoded)["event"] == "job.dispatch_deferred"
    assert "passwordSecret" not in encoded and "OTP123456" not in encoded
