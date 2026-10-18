"""Runtime isolation and persistent signing boundaries, without cloud calls."""

from unittest.mock import Mock

import pytest

from packages.common.settings import Settings
from packages.intake.storage import GoogleBlobStore, LocalFileBlobStore
from services.api.runtime import create_intake_runtime, local_signing_key


def live_settings(**overrides):
    values = dict(
        intake_enabled=True,
        genai_mode="live",
        gcp_project_id="work-511514",
        genai_location="global",
        model_reasoning="gemini-3.8-flash",
    )
    values.update(overrides)
    return Settings(**values)


def test_storage_signing_key_survives_restart_and_rejects_corruption(tmp_path):
    first = local_signing_key(tmp_path)
    assert len(first) == 32 and local_signing_key(tmp_path) == first
    (tmp_path / "intake-signing.key").write_bytes(b"invalid")
    with pytest.raises(ValueError, match="signing key"):
        local_signing_key(tmp_path)


def test_disabled_or_fake_runtime_never_creates_clients(monkeypatch):
    database = Mock(side_effect=AssertionError("unexpected client construction"))
    monkeypatch.setattr("services.api.runtime.firestore.Client", database)
    for config in (Settings(), Settings(intake_enabled=True)):
        with pytest.raises(ValueError, match="live inference"):
            create_intake_runtime(config)
    database.assert_not_called()


def test_emulator_runtime_requires_exact_loopback_and_preserves_model_project(
    monkeypatch, tmp_path
):
    config = live_settings(
        auth_mode="emulator",
        gcp_project_id="demo-relay-local",
        genai_project_id="work-511514",
        intake_data_directory=str(tmp_path),
    )
    database = Mock()
    model = Mock(mode="live")
    factory = Mock(return_value=model)
    monkeypatch.setattr("services.api.runtime.firestore.Client", database)
    monkeypatch.setattr("agents.intake.clients.GoogleGenAIClient", factory)
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "remote.example:8095")
    with pytest.raises(ValueError, match="loopback"):
        create_intake_runtime(config)
    database.assert_not_called()
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8095")
    service, returned = create_intake_runtime(config)
    assert returned is model and isinstance(service.storage, LocalFileBlobStore)
    assert database.call_args.kwargs["project"] == "demo-relay-local"
    assert factory.call_args.args[0].genai_project_id == "work-511514"


def test_cloud_storage_runtime_rejects_emulator_then_uses_explicit_bucket(monkeypatch):
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    config = live_settings(
        intake_storage_mode="gcs",
        bucket_evidence="synthetic-evidence",
        bucket_exports="synthetic-exports",
        storage_signing_email="relay-api@work-511514.iam.gserviceaccount.com",
    )
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8095")
    with pytest.raises(ValueError, match="Cloud runtime"):
        create_intake_runtime(config)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST")
    database = Mock()
    storage = Mock()
    monkeypatch.setattr("services.api.runtime.firestore.Client", database)
    monkeypatch.setattr("services.api.runtime.StorageClient", storage)
    monkeypatch.setattr(
        "agents.intake.clients.GoogleGenAIClient", Mock(return_value=Mock(mode="live"))
    )
    service, _ = create_intake_runtime(config)
    assert isinstance(service.storage, GoogleBlobStore)
    assert storage.return_value.bucket.call_args_list[0].args == ("synthetic-evidence",)
    assert storage.return_value.bucket.call_args_list[1].args == ("synthetic-exports",)
    assert service.export_storage is not service.storage
    assert service.storage.signing_email == config.storage_signing_email
    assert service.export_storage.signing_email == config.storage_signing_email
    assert database.call_args.kwargs == {"project": "work-511514", "database": "(default)"}


def test_deployed_runtime_wires_durable_job_publisher(monkeypatch):
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    config = live_settings(
        environment="dev",
        intake_storage_mode="gcs",
        bucket_evidence="synthetic-evidence",
        bucket_exports="synthetic-exports",
        storage_signing_email="relay-api@work-511514.iam.gserviceaccount.com",
        pubsub_topic_jobs="projects/work-511514/topics/relay-dev-jobs",
        allowed_origins="https://synthetic.example",
    )
    publisher = Mock()
    repository = Mock()
    monkeypatch.setattr("services.api.runtime.firestore.Client", Mock())
    monkeypatch.setattr("services.api.runtime.StorageClient", Mock())
    monkeypatch.setattr("google.cloud.pubsub_v1.PublisherClient", publisher)
    monkeypatch.setattr("packages.intake.repository.FirestoreRepository", repository)
    monkeypatch.setattr(
        "agents.intake.clients.GoogleGenAIClient", Mock(return_value=Mock(mode="live"))
    )
    create_intake_runtime(config)
    publisher.assert_called_once_with()
    wired = repository.call_args.kwargs["job_publisher"]
    assert wired.client is publisher.return_value
    assert wired.topic == config.pubsub_topic_jobs
