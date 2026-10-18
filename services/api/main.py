"""Authenticated HTTP foundation and the explicitly enabled M1 intake runtime."""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from packages.common.auth import AuthenticationError, FirebaseIdentityVerifier, IdentityVerifier
from packages.common.emulator_auth import EmulatorIdentityVerifier
from packages.common.i18n import message, resolve_language
from packages.common.identifiers import new_id
from packages.common.logging import configure_logging
from packages.common.settings import Settings

PUBLIC_PATHS = frozenset(
    {
        "/healthz",
        "/readyz",
        "/api/v1/healthz",
        "/api/v1/readyz",
        "/api/v1/version",
        "/api/v1/config/public",
    }
)


def problem(
    request: Request,
    status: int,
    code: str,
    *,
    detail: str | None = None,
    field_errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    language = resolve_language(request.headers.get("accept-language", "en"))
    body: dict[str, Any] = {
        "type": f"https://relay.example/errors/{code}",
        "title": code.replace("_", " ").capitalize(),
        "status": status,
        "code": code,
        "detail": detail
        or (
            message(code, language)
            if code in {"not_implemented", "unauthenticated", "app_check_failed", "forbidden"}
            else "The request could not be completed."
        ),
        "requestId": getattr(request.state, "request_id", "unknown"),
        "retryable": status in {429, 502, 503, 504},
        "fieldErrors": field_errors or [],
    }
    return JSONResponse(
        body,
        status_code=status,
        media_type="application/problem+json",
        headers={
            "X-Request-Id": body["requestId"],
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def create_app(
    settings: Settings | None = None,
    verifier: IdentityVerifier | None = None,
    intake_service: Any = None,
    live_provider: Any = None,
) -> FastAPI:
    config = settings or Settings()
    identity = verifier or (
        EmulatorIdentityVerifier(config.gcp_project_id, config.auth_emulator_host)
        if config.auth_mode == "emulator"
        else FirebaseIdentityVerifier(config.gcp_project_id)
    )
    runtime_model: Any = None
    live_client: Any = None
    if config.intake_enabled and intake_service is None:
        from services.api.runtime import create_intake_runtime

        intake_service, runtime_model = create_intake_runtime(config)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            yield
        finally:
            if runtime_model is not None:
                await runtime_model.close()
            if live_client is not None:
                await live_client.close()

    configure_logging()
    app = FastAPI(
        title="Relay",
        version="0.2.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=[
            "Authorization",
            "X-Firebase-AppCheck",
            "X-Request-Id",
            "Idempotency-Key",
            "Accept-Language",
            "Content-Type",
        ],
        expose_headers=[
            "X-Request-Id",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "Retry-After",
        ],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def boundary(request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        # Client correlation strings are untrusted and can contain secrets.
        # Only server-generated opaque IDs may enter logs or problem responses.
        request.state.request_id = new_id("req")
        exempt_upload = request.method == "PUT" and request.url.path.startswith(
            "/api/v1/storage/upload/"
        )
        exempt_upload = exempt_upload or bool(
            config.sources_enabled
            and request.method == "PUT"
            and re.fullmatch(r"/api/v1/sources/src_[a-f0-9]{32}/upload", request.url.path)
        )
        if not exempt_upload and request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            declared = request.headers.get("content-length")
            if declared:
                try:
                    size = int(declared)
                except ValueError:
                    return problem(request, 400, "bad_request")
                if size < 0:
                    return problem(request, 400, "bad_request")
                if size > 65_536:
                    return problem(request, 413, "payload_too_large")
            received = bytearray()
            try:
                async with asyncio.timeout(10):
                    async for chunk in request.stream():
                        received.extend(chunk)
                        if len(received) > 65_536:
                            return problem(request, 413, "payload_too_large")
            except TimeoutError:
                return problem(request, 408, "timeout")
            # Starlette's cached-request wrapper replays this bounded body to
            # FastAPI, including requests originally sent with chunked framing.
            request._body = bytes(received)
        if request.method == "OPTIONS":
            response = await call_next(request)
        elif request.url.path not in PUBLIC_PATHS and not (
            config.intake_enabled
            and config.intake_storage_mode == "local"
            and request.method == "GET"
            and request.url.path.startswith(("/api/v1/storage/preview/", "/api/v1/storage/packet/"))
        ):
            header = request.headers.get("authorization", "")
            if not header.startswith("Bearer "):
                response = problem(request, 401, "unauthenticated")
            else:
                try:
                    request.state.actor = await identity.verify(
                        header[7:], request.headers.get("x-firebase-appcheck", "")
                    )
                except AuthenticationError as exc:
                    response = problem(request, 403 if exc.code == "forbidden" else 401, exc.code)
                except TimeoutError:
                    response = problem(request, 503, "timeout")
                except Exception:
                    logging.getLogger("relay").exception(
                        "identity.verification_failed",
                        extra={"request_id": request.state.request_id},
                    )
                    response = problem(request, 503, "identity_unavailable")
                else:
                    response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        rate = getattr(request.state, "intake_rate", None)
        if rate:
            response.headers["X-RateLimit-Limit"] = str(rate["limit"])
            response.headers["X-RateLimit-Remaining"] = str(rate["remaining"])
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = (
            "not_found"
            if exc.status_code == 404
            else "not_implemented"
            if exc.status_code == 501
            else "bad_request"
        )
        return problem(request, exc.status_code, code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo offending values; they can contain volunteered secrets.
        errors = [
            {
                "field": "body"
                if item["type"] == "extra_forbidden"
                else ".".join(str(x) for x in item["loc"]),
                "code": item["type"],
                "message": "Invalid field value",
            }
            for item in exc.errors()
        ]
        return problem(request, 422, "validation_failed", field_errors=errors)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("relay").error(
            "request.failed",
            extra={
                "request_id": getattr(request.state, "request_id", "unknown"),
                "error_code": type(exc).__name__,
            },
        )
        return problem(request, 500, "internal_error")

    @app.get("/healthz")
    @app.get("/api/v1/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    from services.api.readiness import ServingReadiness

    readiness = ServingReadiness(config, intake_service)

    @app.get("/readyz")
    @app.get("/api/v1/readyz")
    async def ready() -> JSONResponse:
        result = await readiness.check()
        return JSONResponse(
            result,
            status_code=200 if result["status"] == "ready" else 503,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/v1/version")
    async def version() -> dict[str, str]:
        return {"gitSha": config.git_sha, "builtAt": config.built_at}

    @app.get("/api/v1/config/public")
    async def public_config() -> dict[str, Any]:
        return {
            "supportedLanguages": config.supported_languages.split(","),
            "demoMode": config.demo_mode,
            "planningEnabled": config.planning_enabled,
            "packetsEnabled": config.packets_enabled,
            "liveEnabled": config.live_enabled,
            "sourcesEnabled": config.sources_enabled,
            "packstudioEnabled": config.packstudio_enabled,
            "linkingEnabled": config.linking_enabled,
            "draftPackPreviewAvailable": config.allow_draft_pack_preview,
            "simBanner": (
                "Simulated institutions: demo environment. No real report or hold is made."
            ),
        }

    # Only the approved intake implementation is mounted. Future business
    # operations remain separate generated contracts.
    if config.intake_enabled:
        from packages.intake.service import IntakeError
        from services.api.intake.router import create_intake_router, intake_error_response

        @app.exception_handler(IntakeError)
        async def intake_error(request: Request, error: IntakeError) -> JSONResponse:
            return intake_error_response(request, error)

        app.include_router(create_intake_router(intake_service))
        if config.sources_enabled:
            from services.api.sources.router import create_source_router

            app.include_router(create_source_router(intake_service.sources))
        if config.packstudio_enabled:
            from services.api.packstudio.router import create_packstudio_router

            app.include_router(create_packstudio_router(intake_service.packstudio))
        if config.packets_enabled:
            from services.api.packets.router import create_packet_router

            app.include_router(create_packet_router(intake_service.packets))
        if config.receiver_enabled:
            from services.api.receiver.router import create_receiver_router

            app.include_router(
                create_receiver_router(
                    intake_service.receiver, rate_limiter=intake_service.rate_limit
                )
            )
        if config.linking_enabled:
            from services.api.linking.router import create_linking_router

            app.include_router(
                create_linking_router(intake_service.receiver_links, intake_service.rate_limit)
            )
    if config.live_enabled:
        from starlette.routing import WebSocketRoute

        from services.live_gateway.runtime import create_runtime_gateway

        gateway, live_client = create_runtime_gateway(
            config, intake_service, identity, provider=live_provider
        )
        app.router.routes.extend(
            route for route in gateway.routes if isinstance(route, WebSocketRoute)
        )
    return app


app = create_app()
