"""Pack Studio through the API and worker boundary, synthetic model stages only."""

import asyncio
from unittest.mock import Mock

from fastapi.testclient import TestClient

from packages.common.settings import Settings
from packages.intake.service import IntakeService
from services.api.main import create_app
from services.worker.http import dispatch_job
from tests.unit.test_packstudio import context  # noqa: F401
from tests.unit.test_sources_application import SourceIdentity, headers


def test_studio_job_dispatch_and_reviewer_org_boundaries(context):  # noqa: F811
    c = context
    service = IntakeService(c.source.repository, Mock(), None, None, clock=c.source.clock)
    service.sources, service.packstudio = c.source, c.studio
    config = Settings(
        intake_enabled=True,
        planning_enabled=True,
        sources_enabled=True,
        packstudio_enabled=True,
        allowed_fetch_domains="official.example",
    )
    with TestClient(create_app(config, SourceIdentity(), service)) as client:
        flags = client.get("/api/v1/config/public").json()
        assert flags["sourcesEnabled"] and flags["packstudioEnabled"]
        created = client.post("/api/v1/pack-builds", json=c.body, headers=headers())
        assert created.status_code == 202, created.text
        build_id, job_id = created.json()["buildId"], created.json()["jobId"]
        assert client.get(f"/api/v1/jobs/{job_id}", headers=headers("foreign")).status_code == 404
        assert client.get(f"/api/v1/jobs/{job_id}", headers=headers("victim")).status_code == 403
        assert asyncio.run(dispatch_job(service, job_id)) is True
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers("colleague"))
        assert job.status_code == 200 and job.json()["state"] == "succeeded"
        draft = client.get(f"/api/v1/pack-builds/{build_id}", headers=headers())
        assert draft.status_code == 200 and draft.json()["state"] == "draft"
        assert "canonical_pack_required" in draft.json()["publicationBlockers"]
        assert (
            client.post(
                f"/api/v1/pack-builds/{build_id}/publish",
                json={"reviewerName": "Fixture", "notes": "No actual human review"},
                headers=headers(),
            ).status_code
            == 422
        )
    assert len(c.client.calls) == 10
