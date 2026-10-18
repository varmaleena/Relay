from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from packages.intake.repository import MemoryRepository
from packages.intake.service import IntakeError
from packages.linking.core import Hasher
from packages.linking.receiver import ReceiverLinks
from packages.linking.service import INDEX, LinkingService
from packages.safety import Actor
from services.api.contracts import CaseLink, LinkResult

NOW = datetime(2026, 10, 18, tzinfo=UTC)
ACTOR = Actor("staff", "receiver", "bank")


def fixture():
    repo = MemoryRepository()
    linking = LinkingService(repo, Hasher(b"x" * 32))
    service = ReceiverLinks(linking, clock=lambda: NOW)
    for i in range(6):
        case, ref = f"case_{i}", f"RLY_{i}"
        linking.replace_case(
            ref,
            {"bank"},
            [
                {
                    "type": "upi_id",
                    "value": "ring@fictional",
                    "role": "scammer",
                    "status": "confirmed",
                }
            ],
            NOW,
            case_id=case,
        )
        expiry = int((NOW + timedelta(hours=1)).timestamp() * 1000)
        repo.set(
            f"receiverViews/bank/cases/{case}",
            {
                "caseRef": ref,
                "latestPacketId": "p",
                "packetIds": ["p"],
                "accessExpiresAtMs": expiry,
            },
        )
        repo.set(
            f"receiverViews/bank/cases/{case}/packets/p",
            {
                "caseRef": ref,
                "accessExpiresAtMs": expiry,
                "packet": {
                    "packetId": "p",
                    "version": 1,
                    "contentHash": "hash",
                    "status": "SENT",
                    "planId": "plan",
                    "factsRevision": 1,
                },
            },
        )
    return repo, linking, service


def test_six_ring_canonical_metadata_only_and_explicit_validation():
    repo, linking, service = fixture()
    result = service.list(ACTOR, "case_0")
    assert len(result["items"]) == 5
    for link in result["items"]:
        CaseLink.model_validate(link)
        assert "ring@fictional" not in str(link)
        assert link["validation"]["decision"] is None
    link_id = result["items"][0]["linkId"]
    key = str(uuid4())
    first = service.validate(ACTOR, link_id, "related", "Synthetic review", key)
    assert service.validate(ACTOR, link_id, "related", "Synthetic review", key) == first
    LinkResult.model_validate(first)
    assert len(repo.get(INDEX)["reviewRequests"]) == 1
    with pytest.raises(IntakeError) as error:
        service.validate(ACTOR, link_id, "not_related", "Synthetic review", key)
    assert error.value.code == "idempotency_conflict"
    record = repo.get(INDEX)
    assert "Synthetic review" not in str(record)
    assert service.list(ACTOR, "case_0")["items"][0]["validation"]["decision"] == "related"
    repo.atomic(lambda tx: linking.cleanup_case(tx, "RLY_0"))
    assert not repo.get(INDEX)["reviewRequests"]
    with pytest.raises(IntakeError):
        service.validate(ACTOR, link_id, "related", "Synthetic review", key)


@pytest.mark.parametrize(
    "actor",
    [
        Actor("v", "victim", "bank"),
        Actor("a", "admin", "bank"),
        Actor("staff", "receiver", "other"),
    ],
)
def test_role_and_other_org(actor):
    _, _, service = fixture()
    with pytest.raises(IntakeError):
        service.list(actor, "case_0")


@pytest.mark.parametrize(
    "change", ["expired", "deleted", "deleting", "stale", "version", "contentHash", "status"]
)
def test_pair_proof_expiry_and_races(change):
    repo, _, service = fixture()
    old = service.list(ACTOR, "case_0")["items"][0]["linkId"]
    path = "receiverViews/bank/cases/case_1/packets/p"
    projection = repo.get(path)
    if change == "expired":
        projection["accessExpiresAtMs"] = int(NOW.timestamp() * 1000)
    elif change in {"deleted", "deleting"}:
        projection[change] = True
    elif change == "stale":
        projection["packet"]["stale"] = True
    else:
        projection["packet"][change] = {"version": 2, "contentHash": "new", "status": "ACK"}[change]
    repo.set(path, projection)
    with pytest.raises(IntakeError) as error:
        service.validate(ACTOR, old, "related", None, str(uuid4()))
    assert error.value.code == "stale_link"
    assert not repo.get(INDEX).get("reviews")


def test_cross_org_scope_excludes_other_pair_and_bad_key_secret():
    repo, _, service = fixture()
    record = repo.get(INDEX)
    record["cases"]["RLY_1"]["orgIds"] = ["other"]
    repo.set(INDEX, record)
    assert len(service.list(ACTOR, "case_0")["items"]) == 4
    link_id = service.list(ACTOR, "case_0")["items"][0]["linkId"]
    with pytest.raises(IntakeError):
        service.validate(ACTOR, link_id, "related", None, "not-a-uuid")
    with pytest.raises(IntakeError):
        service.validate(ACTOR, link_id, "related", "password is secret123", str(uuid4()))


def test_real_http_router_requires_uuid_and_uses_canonical_contract():
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from services.api.linking.router import create_linking_router

    _, _, service = fixture()
    app = FastAPI()

    @app.middleware("http")
    async def authentication(request: Request, call_next):
        request.state.actor = ACTOR
        return await call_next(request)

    @app.exception_handler(IntakeError)
    async def domain_error(request, error):
        return JSONResponse({"code": error.code}, status_code=error.status)

    app.include_router(create_linking_router(service))
    client = TestClient(app)
    response = client.get("/api/v1/console/cases/case_0/links")
    assert response.status_code == 200
    link_id = response.json()["items"][0]["linkId"]
    route = f"/api/v1/console/links/{link_id}/validate"
    assert client.post(route, json={"decision": "related"}).status_code == 422
    approved = client.post(
        route, json={"decision": "not_related"}, headers={"Idempotency-Key": str(uuid4())}
    )
    assert approved.status_code == 200
    assert approved.json() == {"linkId": link_id, "decision": "not_related"}


def test_trusted_invalidation_same_transaction_prevents_review_and_keeps_snapshot():
    from packages.linking.invalidation import invalidate_link_projections

    repo, _, service = fixture()
    old = service.list(ACTOR, "case_0")["items"][0]["linkId"]
    changed = repo.atomic(
        lambda tx: invalidate_link_projections(tx, "case_1", [{"orgId": "bank", "packetId": "p"}])
    )
    assert changed == 1
    assert len(service.list(ACTOR, "case_0")["items"]) == 4
    assert repo.get("receiverViews/bank/cases/case_1/packets/p")["packet"]["contentHash"] == "hash"
    with pytest.raises(IntakeError):
        service.validate(ACTOR, old, "related", None, str(uuid4()))
    assert (
        repo.atomic(
            lambda tx: invalidate_link_projections(
                tx, "case_1", [{"orgId": "bank", "packetId": "p"}]
            )
        )
        == 0
    )
