"""Keyless IAM signing contract; no credentials or cloud requests in fixtures."""

from unittest.mock import Mock

import pytest

from packages.intake.storage import GoogleBlobStore

EMAIL = "relay-api@work-511514.iam.gserviceaccount.com"


@pytest.mark.parametrize("email", ["", "user@example.com", "fake\n@x.iam.gserviceaccount.com"])
def test_signing_identity_is_explicit_service_account(email):
    with pytest.raises(ValueError, match="signing email"):
        GoogleBlobStore(Mock(), email)


def test_metadata_credentials_use_iam_without_private_key(monkeypatch):
    # This object deliberately has no signer/sign_bytes/private-key interface.
    credentials = Mock(spec=["refresh", "token"], token="synthetic-access-token")
    factory = Mock(return_value=(credentials, "work-511514"))
    monkeypatch.setattr("google.auth.default", factory)
    bucket = Mock()
    bucket.blob.return_value.generate_signed_url.return_value = (
        "https://storage.googleapis.com/synthetic"
    )
    store = GoogleBlobStore(bucket, EMAIL)
    store.upload_url("evidence/test", "synthetic-uid", "image/png", 123)
    kwargs = bucket.blob.return_value.generate_signed_url.call_args.kwargs
    assert kwargs["service_account_email"] == EMAIL
    assert kwargs["access_token"] == "synthetic-access-token"
    assert kwargs["method"] == "PUT"
    assert kwargs["headers"] == {"Content-Length": "123"}
    assert kwargs["content_type"] == "image/png"
    assert kwargs["expiration"].total_seconds() == 600
    store.preview_url("exports/test.pdf", "synthetic-uid", "application/pdf")
    kwargs = bucket.blob.return_value.generate_signed_url.call_args.kwargs
    assert kwargs["method"] == "GET" and kwargs["expiration"].total_seconds() == 60
    assert "headers" not in kwargs


def test_signing_failure_does_not_fallback(monkeypatch):
    credentials = Mock(spec=["refresh", "token"], token="synthetic-access-token")
    monkeypatch.setattr("google.auth.default", Mock(return_value=(credentials, None)))
    bucket = Mock()
    bucket.blob.return_value.generate_signed_url.side_effect = PermissionError("signBlob denied")
    with pytest.raises(PermissionError, match="signBlob"):
        GoogleBlobStore(bucket, EMAIL).preview_url("exports/test.pdf", "uid", "application/pdf")
    bucket.blob.return_value.generate_signed_url.assert_called_once()


def test_missing_access_token_never_signs(monkeypatch):
    credentials = Mock(spec=["refresh", "token"], token=None)
    monkeypatch.setattr("google.auth.default", Mock(return_value=(credentials, None)))
    bucket = Mock()
    with pytest.raises(ValueError, match="access token"):
        GoogleBlobStore(bucket, EMAIL).preview_url("exports/test.pdf", "uid", "application/pdf")
    bucket.blob.return_value.generate_signed_url.assert_not_called()
