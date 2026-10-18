"""Synthetic reviewer fixtures; these tests do not authorize a real pack publication."""

from pathlib import Path
from uuid import uuid4

import pytest

from packages.packs.durable import StudioCatalog
from packages.packs.registry import PackRegistry, PackRegistryError
from tests.unit.test_packet_service import make_packet_context
from tests.unit.test_packstudio import context as studio_context
from tests.unit.test_packstudio import publication, reviewed

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def context(tmp_path):
    return studio_context.__wrapped__(tmp_path)


def published(context):
    bid = reviewed(context)
    context.studio.publish(context.actor, bid, publication(context, bid), str(uuid4()))
    return PackRegistry(ROOT / "packs", studio_catalog=StudioCatalog(context.source))


def test_catalog_reads_human_publication_and_private_metadata_stays_private(context):
    registry = published(context)
    selected = registry.select("IN")
    assert selected.pack.pack_id == "pack_synthetic" and not selected.draft_preview
    assert registry.passages(selected.pack)
    assert len(registry.proof(selected.pack)) == 64
    assert len(registry.catalog_hash()) == 64
    public = str(registry.public_metadata(selected.pack))
    assert context.actor.uid not in public and "notes" not in public


def test_retirement_removes_available_version_and_changes_catalog(context):
    registry = published(context)
    selected = registry.select("IN").pack
    before = registry.catalog_hash()
    context.studio.retire(
        context.actor, "pack_synthetic", "1.0.0", {"reason": "Synthetic retirement"}, str(uuid4())
    )
    assert registry.available() == [] and registry.catalog_hash() != before
    with pytest.raises(PackRegistryError, match="unavailable"):
        registry.proof(selected)


@pytest.mark.parametrize("change", ["source", "passage", "pack", "checklist", "review", "org"])
def test_catalog_fails_closed_when_stored_evidence_changes(context, change):
    registry = published(context)
    repo = context.source.repository
    record = repo.documents["packs/pack_synthetic/versions/1.0.0"]
    if change == "source":
        source = repo.documents["sources/" + context.sid]
        context.source.storage.read = lambda _: b"tamper"
        assert source["sha256"]
    elif change == "passage":
        source = repo.documents["sources/" + context.sid]
        repo.documents[f"sources/{context.sid}/passages/{source['passageIds'][0]}"]["text"] = (
            "tamper"
        )
    elif change == "pack":
        record["pack"]["recipients"][0]["name"] = "Invented bank"
    elif change == "checklist":
        record["reviewChecklist"]["sourcesChecked"] = False
    elif change == "review":
        record["humanReviews"] = {}
    else:
        record["orgId"] = "different-org"
    with pytest.raises(PackRegistryError, match="integrity_failure"):
        registry.available()


def test_registration_limit_rejects_partial_catalog(context):
    for number in range(51):
        context.source.repository.set(
            f"packRegistrations/pack_synthetic{number}", {"orgId": "review-org", "versions": []}
        )
    with pytest.raises(PackRegistryError, match="size_limit"):
        StudioCatalog(context.source).available()


def test_nested_uk_is_explicit_and_unreviewed():
    registry = PackRegistry(ROOT / "packs")
    options = {"allow_draft_preview": True, "environment": "local", "demo_mode": True}
    assert registry.select("GB", **options).fallback
    registry.register_known("uk")
    selection = registry.select("GB", **options)
    assert not selection.fallback and selection.draft_preview
    assert selection.pack.jurisdiction.code == "GB"
    assert registry.passages(selection.pack)
    assert registry.proof(selection.pack)
    assert registry.available() == []
    with pytest.raises(PackRegistryError, match="unknown_pack"):
        registry.register_known("../uk")


def test_retirement_invalidates_existing_plan_and_blocks_packet_generation(context, tmp_path):
    from packages.intake.service import IntakeError

    registry = published(context)
    case = make_packet_context(tmp_path / "victim")
    case.planning.workflow.registry = registry
    job = case.planning.enqueue(case.actor, case.case_id, {"previewDraft": True})
    import asyncio

    asyncio.run(case.planning.process_case(job["jobId"]))
    plan = case.planning.get_plan(case.actor, case.case_id)
    assert not plan["stale"] and plan["packId"] == "pack_synthetic"
    context.studio.retire(
        context.actor, "pack_synthetic", "1.0.0", {"reason": "Synthetic retirement"}, str(uuid4())
    )
    assert case.planning.get_plan(case.actor, case.case_id)["stale"]
    with pytest.raises(IntakeError) as error:
        case.packets.generate(case.actor, case.case_id, {"planId": plan["planId"]}, str(uuid4()))
    assert error.value.code == "version_conflict"


def test_snapshot_tamper_marks_existing_plan_stale_without_changing_pack_yaml(tmp_path):
    case = make_packet_context(tmp_path)
    assert not case.planning.get_plan(case.actor, case.case_id)["stale"]
    snapshot = case.registry.source_root / "snapshots/mha-1930.html"
    snapshot.write_bytes(snapshot.read_bytes() + b"tamper")
    assert case.planning.get_plan(case.actor, case.case_id)["stale"]
