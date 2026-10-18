"""SDK AgentCard and JSON-RPC dispatcher behind private Cloud Run IAM."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlsplit

from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    HTTPAuthSecurityScheme,
    SecurityRequirement,
    SecurityScheme,
    StringList,
)
from a2a.utils.errors import InvalidParamsError, UnsupportedOperationError
from fastapi import FastAPI
from starlette.responses import JSONResponse

from services.a2a_receiver.store import RepositoryTaskStore


class SDKPrivacyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # The SDK formats JSON-RPC IDs and validation errors into warning messages.
        record.msg = "A2A transport request rejected"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True


class NoAutonomousActions(AgentExecutor):
    async def execute(self, context, event_queue):
        raise UnsupportedOperationError("Only synchronous addressed handoffs are supported")

    async def cancel(self, context, event_queue):
        raise UnsupportedOperationError("Handoffs cannot grant decision permissions")


class ReceiverRequestHandler(DefaultRequestHandler):
    relay_store: RepositoryTaskStore

    async def on_message_send(self, params, context):
        if params.tenant or params.metadata or params.HasField("configuration"):
            raise InvalidParamsError("Only synchronous reference handoffs are supported")
        return await self.relay_store.send(params.message)

    async def on_get_task(self, params, context):
        return await self.relay_store.get(params.id, context)

    async def on_cancel_task(self, params, context):
        raise UnsupportedOperationError("Human decisions use the authenticated console")

    async def on_message_send_stream(self, params, context):
        raise UnsupportedOperationError("Streaming handoffs are unavailable")
        yield  # pragma: no cover

    async def on_subscribe_to_task(self, params, context):
        raise UnsupportedOperationError("Streaming handoffs are unavailable")
        yield  # pragma: no cover

    async def on_create_task_push_notification_config(self, params, context):
        raise UnsupportedOperationError("Arbitrary push destinations are unavailable")


def create_a2a_app(
    repository: Any,
    receiver_service: Any,
    *,
    endpoint_url: str,
    runtime_mode: str,
    trusted_caller_scope: str,
    allowed_orgs: set[str],
    private_iam: bool,
) -> FastAPI:
    """Cloud factory requires private IAM deployment; explicit local mode is tests only.

    IAM validates service identity before traffic reaches the container. The
    deployment must grant only the victim API service account run.invoker.
    This app never interprets an A2A message as staff authentication.
    """
    parsed = urlsplit(endpoint_url)
    if (
        runtime_mode not in {"cloud", "local"}
        or not private_iam
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Private transport configuration required")
    if runtime_mode == "cloud":
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or any(
                os.environ.get(name)
                for name in ("FIRESTORE_EMULATOR_HOST", "FIREBASE_AUTH_EMULATOR_HOST")
            )
        ):
            raise ValueError("Cloud A2A transport cannot use emulator configuration")
        from packages.intake.repository import FirestoreRepository

        if not isinstance(repository, FirestoreRepository):
            raise ValueError("Cloud A2A requires durable Firestore storage")
    elif parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Local A2A transport must remain loopback")
    logging.getLogger("a2a.server.routes.jsonrpc_dispatcher").addFilter(SDKPrivacyFilter())
    store = RepositoryTaskStore(
        repository, receiver_service, scope=trusted_caller_scope, allowed_orgs=allowed_orgs
    )
    card = AgentCard(
        name="Relay simulated receiver",
        version="1.0.0",
        description="Private simulated addressed packet handoff; human decisions remain separate.",
        supported_interfaces=[
            AgentInterface(url=endpoint_url, protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        capabilities=AgentCapabilities(),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        security_schemes={
            "cloudRunIAM": SecurityScheme(
                http_auth_security_scheme=HTTPAuthSecurityScheme(
                    scheme="Bearer", bearer_format="Google-signed OIDC ID token"
                )
            )
        },
        security_requirements=[SecurityRequirement(schemes={"cloudRunIAM": StringList()})],
        skills=[
            AgentSkill(
                id="receive_packet",
                name="Receive simulated packet",
                description="Read one immutable approved addressed projection.",
                tags=["simulated", "transport-only"],
            ),
            AgentSkill(
                id="request_info",
                name="Identify missing submitted fields",
                description="Return missing fields without initiating human decisions.",
                tags=["simulated", "no-autonomous-action"],
            ),
        ],
    )
    handler = ReceiverRequestHandler(NoAutonomousActions(), store, card)
    # SDK retains its task store privately; keep our typed repository adapter explicit.
    handler.relay_store = store
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.task_store = store

    @app.middleware("http")
    async def bounded_body(request, call_next):
        if request.method == "POST":
            chunks, total = [], 0
            async for chunk in request.stream():
                total += len(chunk)
                if total > 16384:
                    return JSONResponse({"error": "request_too_large"}, status_code=413)
                chunks.append(chunk)
            body = b"".join(chunks)
            request._body = body
            delivered = False

            async def receive():
                nonlocal delivered
                if delivered:
                    return {"type": "http.request", "body": b"", "more_body": False}
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = receive
        return await call_next(request)

    @app.get("/api/v1/healthz")
    async def health():
        return {"status": "ok", "service": "simulated-a2a-receiver"}

    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card, cache_control="no-store"),
        jsonrpc_routes=create_jsonrpc_routes(
            handler, rpc_url=parsed.path or "/", enable_v0_3_compat=True
        ),
    )
    return app
