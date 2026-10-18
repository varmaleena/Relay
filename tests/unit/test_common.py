import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from packages.common.auth import (
    AuthenticationError,
    FirebaseIdentityVerifier,
    actor_from_verified_claims,
)
from packages.common.i18n import MESSAGES, in_timezone, message, resolve_language
from packages.common.identifiers import canonical_hash, idempotency_scope, new_id
from packages.common.logging import SafeJsonFormatter
from packages.common.normalization import entity_hmac, normalize_entity
from packages.common.settings import Settings


def test_local_settings_require_no_cloud_credentials(monkeypatch):
    monkeypatch.delenv("GENAI_MODE", raising=False)
    assert Settings(_env_file=None).genai_mode == "fake"


@pytest.mark.parametrize(
    "data",
    [
        {"demo_mode": False},
        {"supported_languages": "en"},
        {"supported_languages": "en,hi,ta"},
        {"gcp_project_id": "bad/project"},
        {"allowed_origins": "https://*.example.com"},
        {"allowed_origins": "https://example.com/path"},
        {"allowed_origins": "https://user:pass@example.com"},
        {"environment": "prod"},
        {"genai_mode": "live"},
        {"model_fast": "gemini-2.5-flash"},
        {"model_reasoning": "other-model"},
        {"urgent_minutes": 0},
    ],
)
def test_invalid_configuration_fails_closed(data):
    with pytest.raises((ValidationError, ValueError)):
        Settings(**data)


def test_live_configuration_validates_service_requirements():
    config = Settings(
        service="mcp", genai_mode="live", gcp_project_id="work-511514", genai_location="global"
    )
    assert config.gcp_project_id == "work-511514"
    config = Settings(
        service="api",
        genai_mode="live",
        gcp_project_id="work-511514",
        genai_location="global",
        model_reasoning="gemini-3.8-flash",
        bucket_evidence="e",
        bucket_exports="x",
        pubsub_topic_jobs="jobs",
    )
    assert config.model_reasoning == "gemini-3.8-flash"


def test_ids_hashes_are_stable_scoped_and_precise():
    assert new_id("case") != new_id("case")
    with pytest.raises(ValueError):
        new_id("../unsafe")
    assert canonical_hash({"b": 2, "a": Decimal("0.1")}) == canonical_hash(
        {"a": Decimal("0.1"), "b": 2}
    )
    assert idempotency_scope("a", None, "post", "/cases", "key") != idempotency_scope(
        "b", None, "post", "/cases", "key"
    )
    with pytest.raises(ValueError):
        idempotency_scope("", None, "POST", "/cases", "key")
    with pytest.raises(ValueError):
        canonical_hash(float("nan"))
    with pytest.raises(TypeError):
        canonical_hash(object())


@pytest.mark.parametrize(
    "kind,value,kwargs,expected",
    [
        ("phone", "+91 90000 00000", {}, "+919000000000"),
        ("upi_id", " Safe.Verify@FakeBank ", {}, "safe.verify@fakebank"),
        ("email", " Test@EXAMPLE.com ", {}, "test@example.com"),
        ("social_handle", " TEST ", {}, "test"),
        ("bank_account", "test-00 01", {}, "TEST0001"),
        ("iban", "gb-00 test", {}, "GB00TEST"),
        ("ifsc_or_sort_code", "fake-00", {}, "FAKE00"),
        ("wallet_address", "AbC", {}, "AbC"),
        ("wallet_address", "AbC", {"case_sensitive_wallet": False}, "abc"),
        ("url", "https://WWW.example.com/path/?utm_source=x&a=2#part", {}, "example.com/path?a=2"),
        ("url", "example.com:8443/x", {}, "example.com:8443/x"),
        ("amount", "45,000.10", {"currency": "INR"}, "INR 45000.1"),
        ("timestamp", "2026-10-13T12:00:00+05:30", {}, "2026-10-13T06:30:00Z"),
    ],
)
def test_normalization(kind, value, kwargs, expected):
    assert normalize_entity(kind, value, **kwargs) == expected


@pytest.mark.parametrize(
    "kind,value,kwargs",
    [
        ("phone", "1", {}),
        ("phone", "not a number", {}),
        ("url", "https://user:pw@example.com", {}),
        ("url", "javascript://example.com", {}),
        ("amount", "nan", {"currency": "INR"}),
        ("amount", "-1", {"currency": "INR"}),
        ("amount", "abc", {"currency": "INR"}),
        ("amount", "1", {}),
        ("bank_account", "test!", {}),
        ("timestamp", "2026-10-13", {}),
        ("unknown", "x", {}),
        ("email", "", {}),
    ],
)
def test_invalid_normalization(kind, value, kwargs):
    with pytest.raises(ValueError):
        normalize_entity(kind, value, **kwargs)


def test_hmac_type_domain_and_secret_strength():
    key = b"x" * 32
    assert (
        entity_hmac("email", "test@example.com", key)
        == hmac.new(key, b"email|test@example.com", hashlib.sha256).hexdigest()
    )
    assert entity_hmac("email", "value", key) != entity_hmac("upi_id", "value", key)
    with pytest.raises(ValueError):
        entity_hmac("email", "value", b"short")


def test_language_negotiation_and_coverage():
    assert resolve_language("hi-IN;q=0.9,en;q=0.5") == "hi"
    assert resolve_language("hi;q=0,en;q=1") == "en"
    assert resolve_language("hi;q=bad,fr") == "en"
    assert set(MESSAGES["en"]) == set(MESSAGES["hi"])
    assert message("unauthenticated", "unknown") == MESSAGES["en"]["unauthenticated"]
    assert in_timezone(datetime(2026, 10, 13, tzinfo=UTC), "Asia/Kolkata").hour == 5
    with pytest.raises(ValueError):
        in_timezone(datetime(2026, 10, 13), "Asia/Kolkata")


def test_logs_cannot_serialize_evidence_secret_or_exception_message():
    record = logging.LogRecord("relay", logging.ERROR, "", 0, "OTP 123456", (), None)
    record.evidence = "raw screenshot text"
    record.request_id = "req_" + "a" * 32
    record.case_ref = "contains secret with spaces"
    try:
        raise ValueError("password=secret")
    except ValueError:
        import sys

        record.exc_info = sys.exc_info()
    encoded = SafeJsonFormatter().format(record)
    assert "123456" not in encoded and "password" not in encoded and "raw screenshot" not in encoded
    assert json.loads(encoded)["request_id"] == "req_" + "a" * 32
    assert json.loads(encoded)["exception_type"] == "ValueError"


def test_actor_claims_are_deny_by_default():
    assert (
        actor_from_verified_claims(
            {"sub": "anon", "firebase": {"sign_in_provider": "anonymous"}}
        ).role
        == "victim"
    )
    assert (
        actor_from_verified_claims({"uid": "u", "role": "receiver", "orgId": "org"}).org_id == "org"
    )
    for claims in [
        {},
        {"uid": "u"},
        {"uid": "u", "role": "root"},
        {"uid": "u", "role": "receiver"},
        {"uid": "u", "role": "reviewer", "orgId": ""},
        {"uid": "u", "role": "victim", "orgId": 1},
    ]:
        with pytest.raises(AuthenticationError):
            actor_from_verified_claims(claims)


def test_unconfigured_identity_verifier_rejects_without_network():
    with pytest.raises(AuthenticationError, match="unauthenticated"):
        FirebaseIdentityVerifier("")._verify("token", "appcheck")
    with pytest.raises(AuthenticationError, match="app_check_failed"):
        FirebaseIdentityVerifier("work-511514")._verify("token", "")
