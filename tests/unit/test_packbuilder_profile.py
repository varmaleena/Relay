"""Pack Builder request profiles use injected SDK only; no live inference."""

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import create_model

from agents.intake.clients import ModelFailure
from agents.intake.core import IntakeModelOutput
from agents.packbuilder.models import (
    CriticOutput,
    DeadlinesPass,
    RecipientsPass,
    RemediesPass,
    SequencingPass,
    SupportPass,
)
from agents.packets.core import WriterOutput
from tests.unit.test_model_call_logging import log_capture, make_client, rows  # noqa: F401

SCHEMAS = [RecipientsPass, DeadlinesPass, RemediesPass, SequencingPass, SupportPass, CriticOutput]


@pytest.mark.parametrize("schema", SCHEMAS)
def test_actual_sdk_config_and_safe_logging(log_capture, schema):  # noqa: F811
    calls = []

    async def generate_content(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            text="untrusted output never logged",
            usage_metadata=SimpleNamespace(
                prompt_token_count=12,
                candidates_token_count=7,
                thoughts_token_count=3,
            ),
        )

    client = make_client(generate_content)
    target = client.for_packbuilder()
    assert target.parent is client and target.model_id == client.model_id
    assert rows(log_capture) == []
    asyncio.run(
        target.generate(
            prompt="sensitive prompt", data={"passName": "not a log label"}, schema=schema
        )
    )
    assert len(calls) == 1
    config = calls[0]["config"]
    assert config.temperature == 0.1 and config.max_output_tokens == 8000
    assert config.thinking_config is None
    assert config.automatic_function_calling.disable is True
    assert config.tools is None
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema
    assert rows(log_capture)[0]["agent"] == "PackBuilderAgent"
    assert rows(log_capture)[0]["tokens_out"] == 7
    assert len(client.usage_records) == 1
    assert "untrusted output" not in log_capture.getvalue()
    assert "sensitive prompt" not in log_capture.getvalue()
    assert "not a log label" not in log_capture.getvalue()


@pytest.mark.parametrize(
    "schema", [IntakeModelOutput, WriterOutput, create_model("RecipientsPass")]
)
def test_wrong_schema_rejected_before_provider_or_log(log_capture, schema):  # noqa: F811
    async def generate_content(**kwargs):
        raise AssertionError("No provider call is allowed")

    target = make_client(generate_content).for_packbuilder()
    with pytest.raises(ValueError, match="packbuilder_profile_schema_not_allowed"):
        asyncio.run(target.generate(prompt="", data={}, schema=schema))
    assert rows(log_capture) == []


def test_failure_one_attempt_and_typed_safe_event(log_capture):  # noqa: F811
    calls = []

    class ProviderError(Exception):
        code = 503
        message = "OTP123456 provider body never logged"

    async def generate_content(**kwargs):
        calls.append(kwargs)
        raise ProviderError()

    client = make_client(generate_content)
    with pytest.raises(ModelFailure) as failure:
        asyncio.run(client.for_packbuilder().generate(prompt="", data={}, schema=CriticOutput))
    assert failure.value.status_code == 503
    assert len(calls) == 1 and len(client.failure_records) == 1
    record = rows(log_capture)[0]
    assert record["agent"] == "PackBuilderAgent" and record["http_status"] == 503
    assert record["status"] == "failed" and len(rows(log_capture)) == 1
    assert "OTP123456" not in log_capture.getvalue()


def test_intake_packet_and_builder_share_single_concurrency_bucket():
    active, high = 0, 0
    configs = []

    async def generate_content(**kwargs):
        nonlocal active, high
        active += 1
        high = max(high, active)
        configs.append(kwargs["config"])
        await asyncio.sleep(0)
        active -= 1
        return SimpleNamespace(text="{}", usage_metadata=None)

    client = make_client(generate_content)

    async def run():
        await asyncio.gather(
            client.generate(prompt="", data={}, schema=IntakeModelOutput),
            client.for_packets().generate(prompt="", data={}, schema=WriterOutput),
            client.for_packbuilder().generate(prompt="", data={}, schema=RecipientsPass),
        )

    asyncio.run(run())
    assert high == 1
    assert [(c.temperature, c.max_output_tokens) for c in configs] == [
        (0.0, 2000),
        (0.3, 2500),
        (0.1, 8000),
    ]
    assert configs[0].thinking_config is None and configs[2].thinking_config is None
    assert configs[1].thinking_config.thinking_level.value == "LOW"
