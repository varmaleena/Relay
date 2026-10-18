"""Offline real five-pass pipeline and immutable human publication boundaries."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from packages.intake.repository import MemoryRepository
from packages.intake.service import IntakeError
from packages.packstudio import PackBuilderAdapter, PackStudioService
from packages.safety import Actor
from packages.sources.fetch import FetchedSource
from packages.sources.service import SourceService
from packages.sources.storage import LocalSourceStore
from tests.unit.test_packbuilder_agents import TEXT, FixtureClient


class Client(FixtureClient):
    async def generate(self, *, prompt, data, schema):
        result = await super().generate(prompt=prompt, data=data, schema=schema)
        if schema.__name__ != "CriticOutput":
            result = result.replace("src_synthetic:p0001", data["passages"][0]["passageId"])
        return result


@pytest.fixture
def context(tmp_path):
    actor = Actor("reviewer", "reviewer", "review-org")
    source = SourceService(
        MemoryRepository(),
        LocalSourceStore(tmp_path / "sources"),
        SimpleNamespace(
            validate=lambda _: None,
            fetch=lambda url: FetchedSource(TEXT.encode(), "text/plain", url),
        ),
        api_base_url="http://localhost",
        parser=lambda content, mime: [(1, content.decode())],
        clock=lambda: datetime(2026, 10, 17, tzinfo=UTC),
    )
    sid = source.create(
        actor,
        {
            "kind": "url",
            "url": "https://official.example/policy",
            "title": "Synthetic official source",
            "publisher": "Fixture publisher",
            "language": "en",
        },
        str(uuid4()),
    )["sourceId"]
    job = source.ingest(actor, sid)
    asyncio.run(source.process(job["jobId"]))
    client = Client()
    studio = PackStudioService(source, PackBuilderAdapter(client))
    body = {
        "sourceIds": [sid],
        "jurisdictionCode": "IN",
        "name": "Synthetic draft",
        "archetype": "centralized_rail",
    }
    return SimpleNamespace(
        actor=actor, source=source, studio=studio, body=body, client=client, sid=sid
    )


def built(c):
    result = c.studio.create(c.actor, c.body, str(uuid4()))
    asyncio.run(c.studio.process(result["jobId"]))
    assert c.source.repository.get("jobs/" + result["jobId"])["state"] == "succeeded"
    return result["buildId"]


def reviewed(c):
    bid = built(c)
    items = c.studio._items(c.source.repository.get("packBuilds/" + bid))
    for key in items:
        c.studio.review(
            c.actor,
            bid,
            key,
            {
                "action": "accept" if key == "recipient_bank" else "reject",
                "ifRevision": c.studio.get(c.actor, bid)["revision"],
            },
            str(uuid4()),
        )
    return bid


def publication(c, bid):
    view = c.studio.get(c.actor, bid)
    build = c.source.repository.get("packBuilds/" + bid)
    candidate = view["draft"]["recipients"][0]["body"]
    return {
        "ifRevision": view["revision"],
        "reviewerName": "Synthetic human reviewer",
        "notes": "Explicit synthetic review action.",
        "reviewChecklist": {
            k: True
            for k in (
                "sourcesChecked",
                "contactsChecked",
                "scopeConditionsChecked",
                "languagesChecked",
            )
        },
        "acceptUnverifiedRuleIds": ["recipient_bank"],
        "packDraft": {
            "packId": "pack_synthetic",
            "version": "1.0.0",
            "status": "draft",
            "jurisdiction": {"code": "IN", "name": "India", "archetype": "centralized_rail"},
            "languages": ["en"],
            "timezone": "Asia/Kolkata",
            "currency": "INR",
            "disclaimers": ["Synthetic test guidance only."],
            "sources": build["result"]["sources"],
            "recipients": [
                {
                    "id": candidate["id"],
                    "name": candidate["name"],
                    "type": candidate["recipientType"],
                    "channels": candidate["channels"],
                    "sourceRefs": candidate["sourceRefs"],
                    "status": "unverified",
                    "appliesWhen": "True",
                }
            ],
        },
    }


def test_actual_five_passes_and_full_evidence_body(context):
    c = context
    bid = built(c)
    view = c.studio.get(c.actor, bid)
    assert len(c.client.calls) == 10
    assert all(p["state"] == "completed" for p in view["passes"])
    assert view["draft"]["recipients"][0]["body"]["evidenceSpans"]
    assert view["reviews"] == {} and "unreviewed_items" in view["publicationBlockers"]
    assert all(i["status"] == "unverified" for i in view["draft"]["recipients"])


def test_human_publish_immutable_retirement_and_replay(context):
    c = context
    bid = reviewed(c)
    body, key = publication(c, bid), str(uuid4())
    result = c.studio.publish(c.actor, bid, body, key)
    assert c.studio.publish(c.actor, bid, body, key) == result
    path = "packs/pack_synthetic/versions/1.0.0"
    frozen = c.source.repository.get(path)
    assert frozen["pack"]["recipients"][0]["status"] == "unverified"
    c.studio.retire(
        c.actor, "pack_synthetic", "1.0.0", {"reason": "Synthetic retirement"}, str(uuid4())
    )
    assert c.source.repository.get(path) == frozen
    assert c.source.repository.get("packRetirements/pack_synthetic_1.0.0")


@pytest.mark.parametrize("change", ["conditions", "checklist", "self_verified", "source"])
def test_publication_rejects_implicit_conditions_and_forged_verification(context, change):
    c = context
    bid = reviewed(c)
    body = publication(c, bid)
    if change == "conditions":
        del body["packDraft"]["recipients"][0]["appliesWhen"]
    elif change == "checklist":
        body["reviewChecklist"]["contactsChecked"] = False
    elif change == "self_verified":
        body["packDraft"]["recipients"][0]["name"] = "Invented Bank"
    else:
        body["packDraft"]["sources"][0]["sha256"] = "a" * 64
    with pytest.raises(IntakeError):
        c.studio.publish(c.actor, bid, body, str(uuid4()))
    assert c.source.repository.get("packs/pack_synthetic/versions/1.0.0") is None


def test_review_revision_and_idempotency_proof(context):
    c = context
    bid = built(c)
    body, key = {"action": "accept", "ifRevision": 1}, str(uuid4())
    result = c.studio.review(c.actor, bid, "recipient_bank", body, key)
    assert result["revision"] == 2
    assert c.studio.review(c.actor, bid, "recipient_bank", body, key) == result
    with pytest.raises(IntakeError):
        c.studio.review(c.actor, bid, "recipient_bank", body, str(uuid4()))
    with pytest.raises(IntakeError):
        c.studio.review(c.actor, bid, "recipient_bank", body | {"action": "reject"}, key)


def test_edit_cannot_forge_source_spans(context):
    c = context
    bid = built(c)
    item = deepcopy(c.studio.get(c.actor, bid)["draft"]["recipients"][0]["body"])
    item["evidenceSpans"][0]["quote"] = "Invented quotation"
    with pytest.raises(IntakeError):
        c.studio.review(
            c.actor,
            bid,
            "recipient_bank",
            {"action": "edit", "edit": item, "ifRevision": 1},
            str(uuid4()),
        )


def test_tamper_before_worker_fails_durably_without_model_calls(context):
    c = context
    result = c.studio.create(c.actor, c.body, str(uuid4()))
    source = c.source.repository.get("sources/" + c.sid)
    source["sha256"] = "b" * 64
    c.source.repository.atomic(lambda tx: tx.set("sources/" + c.sid, source))
    asyncio.run(c.studio.process(result["jobId"]))
    assert c.source.repository.get("jobs/" + result["jobId"])["state"] == "failed"
    assert not c.client.calls


def test_org_isolation_and_source_metadata_gap(context):
    c = context
    bid = built(c)
    with pytest.raises(IntakeError):
        c.studio.get(Actor("other", "reviewer", "foreign-org"), bid)
    with pytest.raises(IntakeError):
        c.studio.get(Actor("victim", "victim"), bid)
    source = c.source.repository.get("sources/" + c.sid)
    source.update(url=None, finalUrl=None)
    c.source.repository.atomic(lambda tx: tx.set("sources/" + c.sid, source))
    with pytest.raises(IntakeError) as error:
        c.studio.create(c.actor, c.body, str(uuid4()))
    assert error.value.code == "source_metadata_required"


def test_unsupported_acceptance_cannot_become_verified(context):
    c = context
    c.client.verdicts = {"recipients": "UNSUPPORTED"}
    bid = reviewed(c)
    body = publication(c, bid)
    body["packDraft"]["recipients"][0]["status"] = "verified"
    body["acceptUnverifiedRuleIds"] = []
    with pytest.raises(IntakeError) as error:
        c.studio.publish(c.actor, bid, body, str(uuid4()))
    assert error.value.code == "unverified_status_required"
    body["packDraft"]["recipients"][0]["status"] = "unverified"
    body["acceptUnverifiedRuleIds"] = ["recipient_bank"]
    assert c.studio.publish(c.actor, bid, body, str(uuid4()))["status"] == "published"


def test_edited_then_accepted_cannot_reuse_original_critic_verdict(context):
    c = context
    bid = built(c)
    item = c.studio.get(c.actor, bid)["draft"]["recipients"][0]["body"]
    item["notes"] = "Human edited explanatory note."
    c.studio.review(
        c.actor,
        bid,
        "recipient_bank",
        {"action": "edit", "edit": item, "ifRevision": 1},
        str(uuid4()),
    )
    for key in c.studio._items(c.source.repository.get("packBuilds/" + bid)):
        c.studio.review(
            c.actor,
            bid,
            key,
            {
                "action": "accept" if key == "recipient_bank" else "reject",
                "ifRevision": c.studio.get(c.actor, bid)["revision"],
            },
            str(uuid4()),
        )
    body = publication(c, bid)
    body["packDraft"]["recipients"][0]["status"] = "verified"
    body["acceptUnverifiedRuleIds"] = []
    with pytest.raises(IntakeError) as error:
        c.studio.publish(c.actor, bid, body, str(uuid4()))
    assert error.value.code == "unverified_status_required"


def test_router_models_and_explicit_uuid(context):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from services.api.packstudio.router import create_packstudio_router

    c = context
    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.actor = c.actor
        return await call_next(request)

    @app.exception_handler(IntakeError)
    async def error(request, exc):
        return JSONResponse({"code": exc.code}, status_code=exc.status)

    app.include_router(create_packstudio_router(c.studio))
    with TestClient(app) as client:
        assert client.post("/api/v1/pack-builds", json=c.body).status_code == 422
        created = client.post(
            "/api/v1/pack-builds", json=c.body, headers={"Idempotency-Key": str(uuid4())}
        )
        assert created.status_code == 202, created.text
        data = created.json()
        asyncio.run(c.studio.process(data["jobId"]))
        response = client.get("/api/v1/pack-builds/" + data["buildId"])
        assert response.status_code == 200, response.text
        assert response.json()["revision"] == 1
        response = client.patch(
            "/api/v1/pack-builds/" + data["buildId"] + "/rules/recipient_bank",
            json={"action": "accept", "ifRevision": 1},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 200, response.text
        assert response.json()["revision"] == 2


def test_structural_source_ids_do_not_trigger_secret_false_positives():
    from packages.packstudio.service import clean

    clean({"sourceIds": ["src_" + "1234567890123456" * 2]})
    clean({"sha256": "1" * 64, "sourceRefs": ["src_" + "1" * 32 + ":p0001"]})
    with pytest.raises(IntakeError):
        clean({"notes": "My password is synthetic-secret"})
    with pytest.raises(IntakeError):
        clean({"quote": "OTP 123456"})
