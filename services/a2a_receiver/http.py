"""Minimal private Cloud Run A2A receiver process; no victim API or hold tools."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

from google.cloud import firestore

from agents.intake.clients import GoogleGenAIClient
from agents.receiver import ReceiverBriefAgent
from packages.common.logging import configure_logging
from packages.common.settings import Settings
from packages.intake.repository import FirestoreRepository
from packages.receiver.bridge import DEMO_RECIPIENT_ORGS
from packages.receiver.service import ReceiverService
from services.a2a_receiver.app import create_a2a_app


def validate_cloud_settings(config: Settings) -> None:
    endpoint = urlsplit(config.a2a_receiver_url)
    if (
        config.service != "a2a"
        or config.environment == "local"
        or config.genai_mode != "live"
        or config.auth_mode != "firebase"
        or not config.gcp_project_id
        or not config.genai_location
        or not config.model_reasoning
        or endpoint.scheme != "https"
        or not (endpoint.hostname or "").endswith(".run.app")
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
        or endpoint.path not in {"", "/"}
        or endpoint.port not in {None, 443}
        or os.environ.get("A2A_PRIVATE_IAM_REQUIRED") != "true"
        or any(
            os.environ.get(key)
            for key in (
                "FIRESTORE_EMULATOR_HOST",
                "FIREBASE_AUTH_EMULATOR_HOST",
                "STORAGE_EMULATOR_HOST",
            )
        )
    ):
        raise ValueError(
            "A2A requires explicit private cloud configuration and live model settings"
        )


def create_receiver_app():
    config = Settings()
    validate_cloud_settings(config)
    configure_logging()
    database = firestore.Client(project=config.gcp_project_id, database=config.firestore_db)
    model: Any = None
    try:
        repository = FirestoreRepository(database)
        model = GoogleGenAIClient(config)
        receiver = ReceiverService(
            repository,
            recipient_orgs=DEMO_RECIPIENT_ORGS,
            brief_maker=ReceiverBriefAgent(model).make_brief,
        )
        app = create_a2a_app(
            repository,
            receiver,
            endpoint_url=config.a2a_receiver_url,
            runtime_mode="cloud",
            trusted_caller_scope="victim-api",
            allowed_orgs=set(DEMO_RECIPIENT_ORGS.values()),
            private_iam=True,
        )
    except Exception:
        database.close()
        raise

    @asynccontextmanager
    async def lifecycle(app):
        try:
            yield
        finally:
            try:
                await model.close()
            finally:
                database.close()

    app.router.lifespan_context = lifecycle
    return app
