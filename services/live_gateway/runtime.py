"""Explicit runtime wiring; constructing a client never establishes Live readiness."""

import re
from typing import Any

from fastapi import FastAPI
from google import genai
from google.genai import types

from packages.common.auth import IdentityVerifier
from packages.common.settings import Settings

from .app import GatewayConfig, create_live_gateway
from .provider import GoogleLiveProvider


class LiveRuntimeClient:
    """Parent lifespan owns this handle; the gateway owns each session context."""

    def __init__(self, client: Any):
        self.client = client
        self.closed = False

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            await self.client.aio.aclose()
        finally:
            self.client.close()


def create_runtime_gateway(
    config: Settings,
    intake: Any,
    identity: IdentityVerifier,
    provider: Any = None,
) -> tuple[FastAPI, LiveRuntimeClient | None]:
    """Return an ASGI app for mounting its WS route, plus a lifespan-owned client.

    No discovery, readiness inference, connection, generation or fallback occurs.
    Explicit capability configuration records a prior operational decision; the
    one greeting probe does not establish Hindi, microphone or audio safety.
    """
    if (
        not config.live_enabled
        or not config.intake_enabled
        or not config.live_capabilities_verified
        or intake is None
        or not callable(getattr(identity, "verify", None))
    ):
        raise ValueError(
            "Live requires explicit enablement, intake and verified identity/capability"
        )
    gateway_config = GatewayConfig(
        allowed_origins=tuple(config.origins),
        max_session_seconds=min(config.max_session_seconds, 600),
    )
    client: LiveRuntimeClient | None = None
    if provider is None:
        project = config.genai_project_id or config.gcp_project_id
        if (
            config.genai_mode != "live"
            or not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project)
            or not re.fullmatch(r"[a-z][a-z0-9-]{1,40}", config.genai_live_location)
        ):
            raise ValueError("Live requires an explicit model project and separate Live location")
        # Validate the model and capability assertion before constructing SDK resources.
        selected = GoogleLiveProvider(
            None, config.model_live, capabilities_verified=config.live_capabilities_verified
        )
        sdk_client = genai.Client(
            enterprise=True,
            project=project,
            location=config.genai_live_location,
            http_options=types.HttpOptions(
                api_version="v1beta1",
                timeout=15000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        selected.client = sdk_client
        provider = selected
        client = LiveRuntimeClient(sdk_client)
    # Default options do not turn an unreviewed draft into an automatically selected pack.
    app = create_live_gateway(
        intake=intake, verifier=identity, provider=provider, config=gateway_config
    )
    return app, client
