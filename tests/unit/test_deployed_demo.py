"""The dev-only draft exception never grants production pack approval."""

from pathlib import Path

import pytest

from packages.common.settings import Settings
from packages.packs.registry import PackRegistry, PackRegistryError


def config(**overrides):
    return Settings(
        **{
            "environment": "dev",
            "genai_mode": "live",
            "gcp_project_id": "work-511514",
            "genai_location": "global",
            "intake_enabled": True,
            "intake_storage_mode": "gcs",
            "bucket_evidence": "synthetic-evidence",
            "bucket_exports": "synthetic-exports",
            "storage_signing_email": "relay-dev-api@work-511514.iam.gserviceaccount.com",
            "pubsub_topic_jobs": "projects/work-511514/topics/relay-jobs",
            "model_reasoning": "gemini-3.8-flash",
            "allowed_origins": "https://work-511514.web.app",
            "allow_draft_pack_preview": True,
            "deployed_demo_preview": True,
            **overrides,
        }
    )


def test_explicit_dev_exception_retains_draft_status():
    assert config().deployed_demo_preview
    registry = PackRegistry(Path("packs"), deployed_demo_preview=True)
    selected = registry.select("IN", allow_draft_preview=True, environment="dev", demo_mode=True)
    assert selected.draft_preview and selected.pack.status == "draft"
    assert not selected.pack.review.reviewer
    assert registry.available(environment="dev", demo_mode=True) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"environment": "prod"},
        {"environment": "staging"},
        {"deployed_demo_preview": False},
        {"auth_mode": "emulator"},
        {"intake_storage_mode": "local"},
        {"storage_signing_email": ""},
        {"pubsub_topic_jobs": "relay-jobs"},
    ],
)
def test_incomplete_or_release_configuration_fails_closed(overrides):
    with pytest.raises(ValueError):
        config(**overrides)


@pytest.mark.parametrize(
    "environment,demo,flag",
    [
        ("dev", True, False),
        ("prod", True, True),
        ("staging", True, True),
        ("dev", False, True),
    ],
)
def test_registry_requires_all_dev_demo_gates(environment, demo, flag):
    with pytest.raises(PackRegistryError):
        PackRegistry(Path("packs"), deployed_demo_preview=flag).available(
            allow_draft_preview=True, environment=environment, demo_mode=demo
        )
