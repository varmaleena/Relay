"""Real HTTP framework boundary with explicit injected synthetic verifier only."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from packages.common.auth import AuthenticationError
from packages.common.settings import Settings
from packages.intake.repository import MemoryRepository
from packages.intake.service import IntakeError, IntakeService
from packages.intake.storage import LocalFileBlobStore
from packages.safety import Actor
from services.api.intake.router import create_intake_router, intake_error_response
from services.api.main import create_app


class TestVerifier:
    __test__ = False

    async def verify(self, id_token, app_check_token):
        if app_check_token != "test-appcheck" or id_token not in {
            "victim-a",
            "victim-b",
            "receiver",
        }:
            raise AuthenticationError("unauthenticated")
        return Actor(id_token, "receiver" if id_token == "receiver" else "victim", "test-org")


@pytest.fixture
def client(tmp_path):
    service = IntakeService(
        MemoryRepository(), LocalFileBlobStore(tmp_path, "http://testserver", b"r" * 32), None, None
    )
    app = create_app(Settings(), TestVerifier())
    app.include_router(create_intake_router(service))
    app.add_exception_handler(IntakeError, intake_error_response)
    with TestClient(app) as connection:
        yield connection


def headers(uid="victim-a"):
    return {
        "Authorization": "Bearer " + uid,
        "X-Firebase-AppCheck": "test-appcheck",
        "Idempotency-Key": str(uuid4()),
    }


def test_http_identity_ownership_shape_and_replay(client):
    body = {"language": "hi", "consentVersion": "1.0"}
    denied = client.post("/api/v1/cases", json=body)
    assert denied.status_code == 401
    auth = headers()
    created = client.post("/api/v1/cases", json=body, headers=auth)
    assert created.status_code == 201
    assert client.post("/api/v1/cases", json=body, headers=auth).json() == created.json()
    case_id = created.json()["caseId"]
    case_url = f"/api/v1/cases/{case_id}"
    assert client.get(case_url, headers=headers("victim-b")).status_code == 403
    assert client.get(case_url, headers=headers("receiver")).status_code == 403
    case = client.get(case_url, headers=headers()).json()
    assert case["factsRevision"] == 0 and case["transcript"] == []
    patch = client.patch(
        case_url + "/facts",
        json={"facts": {"payment": {"method": "upi"}}, "source": "confirmed", "ifRevision": 0},
        headers=headers(),
    )
    assert patch.status_code == 200 and patch.json()["factsRevision"] == 1
    assert (
        client.patch(
            case_url + "/facts",
            json={"facts": {}, "source": "confirmed", "ifRevision": 0},
            headers=headers(),
        ).status_code
        == 409
    )
    process = client.post(case_url + "/process", json={}, headers=headers())
    assert process.status_code == 501 and process.json()["code"] == "not_implemented"
    assert client.delete(case_url, headers=headers()).status_code == 204
    assert client.get(case_url, headers=headers()).status_code == 404


def test_privacy_deletion_not_starved_by_read_budget_and_still_owner_scoped(client):
    created = client.post(
        "/api/v1/cases", json={"language": "en", "consentVersion": "1.0"}, headers=headers()
    )
    case_url = "/api/v1/cases/" + created.json()["caseId"]
    for _ in range(29):
        assert client.get(case_url, headers=headers()).status_code == 200
    throttled = client.get(case_url, headers=headers())
    assert throttled.status_code == 429
    assert 1 <= int(throttled.headers["Retry-After"]) <= 60
    assert client.delete(case_url, headers=headers("victim-b")).status_code == 403
    deleted = client.delete(case_url, headers=headers())
    assert deleted.status_code == 204
    assert deleted.headers["X-RateLimit-Limit"] == "5"
