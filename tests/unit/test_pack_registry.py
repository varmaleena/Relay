import json
import shutil
from pathlib import Path

import pytest
import yaml

from packages.packs.registry import PackRegistry, PackRegistryError

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def registry(tmp_path: Path) -> PackRegistry:
    shutil.copytree(ROOT / "packs", tmp_path / "packs")
    shutil.copytree(ROOT / "docs/pack-sources", tmp_path / "docs/pack-sources")
    return PackRegistry(tmp_path / "packs")


def preview(registry: PackRegistry, country: str | None = "IN"):
    return registry.select(country, allow_draft_preview=True, environment="local", demo_mode=True)


def test_real_drafts_validate_offline_without_claiming_review(registry):
    india = preview(registry)
    assert india.pack.pack_id == "pack_in_cyber_rail"
    assert india.draft_preview and not india.fallback
    assert [r.id for r in india.pack.recipients] == ["bank", "cyber", "payment-app"]
    assert [s.recipient_id for s in india.pack.sequencing] == ["bank", "cyber", "payment-app"]
    assert [s.step for s in india.pack.sequencing] == [1, 2, 3]
    cyber = india.pack.recipients[1]
    assert [(c.type, c.value) for c in cyber.channels] == [
        ("phone", "1930"),
        ("portal", "https://www.cybercrime.gov.in/"),
    ]
    assert cyber.source_refs == ["mha-1930:reporting"]
    assert [f.recipient_id for f in india.pack.forms] == ["bank", "cyber", "payment-app"]
    assert not india.pack.review.reviewer and not india.pack.review.reviewed_at
    assert not india.pack.deadlines
    assert all(r.status == "unverified" for r in india.pack.recipients)
    assert all(not c.verified for r in india.pack.recipients for c in r.channels)
    passages = registry.passages(india.pack)
    assert "1930" in passages["mha-1930:reporting"]
    assert all(len(text) < 4000 for text in passages.values())
    fallback = preview(registry, "US")
    assert fallback.fallback and fallback.pack.jurisdiction.code == "GENERIC"
    assert not fallback.pack.sources


def test_normal_selection_never_silently_serves_drafts(registry):
    assert registry.available() == []
    with pytest.raises(PackRegistryError, match="no_published_pack"):
        registry.select("IN")


@pytest.mark.parametrize("environment,demo", [("production", True), ("local", False)])
def test_preview_gate_requires_both_local_and_demo(registry, environment, demo):
    with pytest.raises(PackRegistryError, match="local_demo"):
        registry.select("IN", allow_draft_preview=True, environment=environment, demo_mode=demo)


def test_snapshot_tampering_fails_closed(registry):
    path = registry.source_root / "snapshots/mha-1930.html"
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(PackRegistryError, match="snapshot_hash"):
        preview(registry)


def test_passage_cannot_invent_legal_claim_even_with_new_hash(registry):
    import hashlib

    path = registry.source_root / "passages.json"
    passages = json.loads(path.read_text(encoding="utf-8"))
    passages[0]["text"] = "Every manipulated payment is guaranteed a refund."
    passages[0]["sha256"] = hashlib.sha256(passages[0]["text"].encode()).hexdigest()
    path.write_text(json.dumps(passages), encoding="utf-8")
    with pytest.raises(PackRegistryError, match="passage_integrity"):
        preview(registry)


def test_source_path_traversal_rejected(registry):
    path = registry.source_root / "retrievals.json"
    records = json.loads(path.read_text())
    records[0]["snapshot"] = "../../outside.html"
    path.write_text(json.dumps(records))
    with pytest.raises(PackRegistryError, match="invalid_source_path"):
        preview(registry)


def test_missing_directory_and_country_path_rejected(tmp_path):
    registry = PackRegistry(tmp_path / "absent")
    with pytest.raises(PackRegistryError, match="directory_missing"):
        registry.available()
    with pytest.raises(PackRegistryError, match="country_code"):
        registry.select("../../IN")


def test_numeric_semver_selects_highest_published_not_draft(registry):
    # This is a synthetic fixture review, not checked-in human authorization.
    original = registry.root / "generic-fragmented.yaml"
    pack = yaml.safe_load(original.read_text(encoding="utf-8"))
    for version in ["1.9.0", "1.10.0"]:
        pack["version"] = version
        pack["status"] = "published"
        pack["review"] = {
            "reviewer": "TEST FIXTURE ONLY",
            "reviewed_at": "2026-10-14T00:00:00Z",
            "accepted_unverified_rule_ids": [
                r["id"] for group in ("recipients", "sequencing") for r in pack[group]
            ],
        }
        (registry.root / f"test-{version}.yaml").write_text(yaml.safe_dump(pack), encoding="utf-8")
    assert registry.select("US").pack.version == "1.10.0"
