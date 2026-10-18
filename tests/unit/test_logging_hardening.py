"""Logging must reject plausible secret strings, not just strings with spaces."""

import json
import logging

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from packages.common.logging import SafeJsonFormatter
from packages.common.settings import Settings
from services.api.main import create_app


def record(message="request.failed", **metadata):
    entry = logging.LogRecord("relay", logging.ERROR, "", 0, message, (), None)
    entry.__dict__.update(metadata)
    return entry


def test_unknown_alphanumeric_message_and_metadata_redacted():
    encoded = SafeJsonFormatter().format(
        record(
            "OTP123456",
            request_id="OTP123456",
            case_ref="919000000000",
            error_code="passwordSecret",
            status="passwordSecret",
            agent="passwordSecret",
            service="passwordSecret",
            job_id="OTP123456",
        )
    )
    assert json.loads(encoded)["event"] == "redacted_event"
    for secret in ["OTP123456", "919000000000", "passwordSecret"]:
        assert secret not in encoded


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, 1 << 10000, "123456"])
def test_invalid_numerical_metadata_does_not_break_error_logging(value):
    parsed = json.loads(SafeJsonFormatter().format(record(latency_ms=value, tokens_in=value)))
    assert "latency_ms" not in parsed and "tokens_in" not in parsed


def test_expected_internal_metadata_survives():
    parsed = json.loads(
        SafeJsonFormatter().format(
            record(
                request_id="req_" + "a" * 32,
                trace_id="b" * 32,
                case_ref="RLY-2026-000123",
                job_id="job_" + "c" * 32,
                model_id="gemini-3-flash-preview",
                prompt_version="evidence.v2",
                agent="EvidenceAgent",
                status="failed",
                error_code="ValueError",
                service="worker",
                latency_ms=1.5,
                tokens_in=100,
                tokens_out=5,
            )
        )
    )
    assert parsed["event"] == "request.failed"
    assert parsed["latency_ms"] == 1.5 and parsed["tokens_in"] == 100
    assert parsed["prompt_version"] == "evidence.v2"


def test_unknown_exception_name_and_record_level_cannot_leak_secret():
    secret_exception = type("OTP123456", (Exception,), {})
    entry = record()
    entry.exc_info = (secret_exception, secret_exception("passwordSecret"), None)
    entry.levelname = "passwordSecret"
    encoded = SafeJsonFormatter().format(entry)
    assert "OTP123456" not in encoded and "passwordSecret" not in encoded
    assert json.loads(encoded)["exception_type"] == "unknown"


def test_message_objects_never_have_str_invoked():
    class Secret:
        def __str__(self):
            raise AssertionError("must never stringify untrusted objects")

    assert json.loads(SafeJsonFormatter().format(record(Secret())))["event"] == "redacted_event"


def test_server_request_id_never_accepts_client_secret_header():
    app = create_app(Settings())
    middleware = next(
        entry.kwargs["dispatch"] for entry in app.user_middleware if "dispatch" in entry.kwargs
    )
    generated = []
    for supplied in ["OTP123456", "req_" + "a" * 32]:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/healthz",
                "headers": [(b"x-request-id", supplied.encode())],
            }
        )

        async def healthy_call(_request):
            return JSONResponse({"status": "ok"})

        # This public boundary path has no awaited I/O; executing its coroutine
        # directly avoids Windows socketpair permissions and exercises real code.
        coroutine = middleware(request, healthy_call)
        with pytest.raises(StopIteration) as result:
            coroutine.send(None)
        server_id = result.value.value.headers["X-Request-Id"]
        assert server_id == request.state.request_id
        assert server_id.startswith("req_") and len(server_id) == 36
        assert server_id != supplied
        generated.append(server_id)
    assert generated[0] != generated[1]
