"""No-network construction and lifecycle proof for the opt-in Live runtime."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.routing import WebSocketRoute

from packages.common.settings import Settings
from services.live_gateway.runtime import create_runtime_gateway


def settings(**overrides):
    values = dict(
        intake_enabled=True,
        live_enabled=True,
        live_capabilities_verified=True,
        genai_mode="live",
        gcp_project_id="demo-relay-local",
        genai_project_id="work-511514",
        genai_location="global",
        genai_live_location="us-central1",
        model_reasoning="gemini-3.8-flash",
        model_live="gemini-3.8-live",
        allowed_origins="https://relay.test,http://localhost:5173",
    )
    values.update(overrides)
    return Settings(**values)


def test_separate_enterprise_location_and_sdk_lifecycle_without_any_connection(monkeypatch):
    sdk = Mock()
    sdk.aio.aclose = AsyncMock()
    constructor = Mock(return_value=sdk)
    monkeypatch.setattr("services.live_gateway.runtime.genai.Client", constructor)
    app, handle = create_runtime_gateway(settings(), Mock(), Mock())
    args = constructor.call_args.kwargs
    assert args["enterprise"] is True
    assert args["project"] == "work-511514" and args["location"] == "us-central1"
    assert args["http_options"].api_version == "v1beta1"
    assert args["http_options"].timeout == 15000
    assert args["http_options"].retry_options.attempts == 1
    assert [r.path for r in app.routes if isinstance(r, WebSocketRoute)] == ["/live/v1/session"]
    sdk.aio.live.connect.assert_not_called()
    assert handle is not None
    asyncio.run(handle.close())
    asyncio.run(handle.close())
    sdk.aio.aclose.assert_awaited_once()
    sdk.close.assert_called_once()


def test_injected_provider_skips_all_sdk_resources(monkeypatch):
    constructor = Mock(side_effect=AssertionError("unexpected SDK construction"))
    monkeypatch.setattr("services.live_gateway.runtime.genai.Client", constructor)
    app, client = create_runtime_gateway(
        settings(genai_mode="fake"), Mock(), Mock(), provider=Mock()
    )
    assert client is None and app is not None
    constructor.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"live_enabled": False},
        {"intake_enabled": False},
        {"live_capabilities_verified": False},
        {"genai_live_location": ""},
        {"model_live": "gemini-2.5-live"},
        {"model_live": "secret\nmodel"},
        {"genai_mode": "fake"},
        {"genai_project_id": "", "gcp_project_id": ""},
    ],
)
def test_fail_closed_before_sdk_even_if_a_settings_copy_bypasses_validation(monkeypatch, changes):
    constructor = Mock(side_effect=AssertionError("unexpected SDK construction"))
    monkeypatch.setattr("services.live_gateway.runtime.genai.Client", constructor)
    config = settings().model_copy(update=changes)
    with pytest.raises(ValueError):
        create_runtime_gateway(config, Mock(), Mock())
    constructor.assert_not_called()


def test_explicit_project_fallback_does_not_copy_global_text_location(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr("services.live_gateway.runtime.genai.Client", constructor)
    create_runtime_gateway(
        settings(genai_project_id="", gcp_project_id="work-511514"), Mock(), Mock()
    )
    assert constructor.call_args.kwargs["project"] == "work-511514"
    assert constructor.call_args.kwargs["location"] != "global"


def test_invalid_identity_cannot_create_sdk_even_with_provider_injection(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr("services.live_gateway.runtime.genai.Client", constructor)
    with pytest.raises(ValueError):
        create_runtime_gateway(settings(), Mock(), None, provider=Mock())
    constructor.assert_not_called()
