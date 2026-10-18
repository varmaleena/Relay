"""Bounded authenticated WebSocket transport; injected provider, no default credentials."""

import asyncio
import json
import re
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from agents.intake.live import LiveIntakeTools, live_tool_response, safe_live_output
from packages.common.auth import AuthenticationError
from packages.intake.service import IntakeError
from packages.safety import Actor

from .registry import LiveSessionRegistry


@dataclass(frozen=True)
class GatewayConfig:
    allowed_origins: tuple[str, ...]
    auth_timeout: float = 5
    heartbeat_seconds: float = 20
    max_session_seconds: float = 600
    tool_timeout: float = 0.3
    max_control_bytes: int = 20000
    max_output_audio_bytes: int = 1_920_000

    def __post_init__(self):
        if (
            not self.allowed_origins
            or any(
                not origin.startswith(("https://", "http://localhost:", "http://127.0.0.1:"))
                for origin in self.allowed_origins
            )
            or not 0 < self.auth_timeout <= 5
            or not 0 < self.heartbeat_seconds <= 20
            or not 0 < self.max_session_seconds <= 600
            or not 0 < self.tool_timeout <= 0.3
            or not 100 <= self.max_control_bytes <= 20000
            or not 4800 <= self.max_output_audio_bytes <= 1_920_000
        ):
            raise ValueError("Explicit bounded gateway configuration required")


class StopLive(Exception):
    def __init__(self, code: int, reason: str):
        self.code, self.reason = code, reason


def create_live_gateway(
    *,
    intake: Any,
    verifier: Any,
    provider: Any,
    config: GatewayConfig,
    registry: LiveSessionRegistry | None = None,
    processing_options: dict[str, Any] | None = None,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    sessions = registry or LiveSessionRegistry(intake)

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.websocket("/live/v1/session")
    async def session(ws: WebSocket):
        if ws.headers.get("origin") not in config.allowed_origins:
            await ws.close(code=4403)
            return
        await ws.accept()
        lock = asyncio.Lock()
        lease: dict[str, Any] | None = None
        tasks: list[asyncio.Task[Any]] = []

        async def send(item: dict[str, Any] | bytes):
            async with lock:
                if isinstance(item, bytes):
                    await ws.send_bytes(item)
                else:
                    await ws.send_json(item)

        async def control(timeout: float | None = None) -> dict[str, Any]:
            message = await asyncio.wait_for(ws.receive(), timeout=timeout)
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect()
            raw = message.get("text")
            if type(raw) is not str or len(raw.encode()) > config.max_control_bytes:
                raise StopLive(4001, "invalid_message")
            try:
                value = json.loads(raw)
            except (ValueError, RecursionError):
                raise StopLive(4001, "invalid_message") from None
            if type(value) is not dict:
                raise StopLive(4001, "invalid_message")
            return value

        async def thin(callback, *args):
            # A timed-out storage thread cannot be killed. Close the session rather
            # than starting more tool calls; no tool can approve/send/hold.
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(callback, *args), timeout=config.tool_timeout
                )
            except TimeoutError:
                raise StopLive(4500, "tool_timeout") from None

        try:
            try:
                auth = await control(config.auth_timeout)
                if (
                    set(auth) != {"type", "idToken", "appCheckToken"}
                    or auth["type"] != "auth"
                    or any(
                        type(auth[key]) is not str or not 1 <= len(auth[key]) <= 8192
                        for key in ("idToken", "appCheckToken")
                    )
                ):
                    raise StopLive(4401, "unauthenticated")
                actor = await asyncio.wait_for(
                    verifier.verify(auth["idToken"], auth["appCheckToken"]),
                    timeout=config.auth_timeout,
                )
                del auth
            except (AuthenticationError, TimeoutError):
                raise StopLive(4401, "unauthenticated") from None
            if not isinstance(actor, Actor) or actor.role != "victim":
                raise StopLive(4403, "forbidden")
            start = await control(config.auth_timeout)
            if (
                set(start) - {"type", "caseId", "language", "audio", "resumeHandle"}
                or start.get("type") != "start"
                or type(start.get("caseId")) is not str
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", start["caseId"])
                or start.get("language") not in {"en", "hi"}
                or start.get("audio")
                != {"encoding": "pcm_s16le", "sampleRateHz": 16000, "channels": 1}
                or (
                    "resumeHandle" in start
                    and (
                        type(start["resumeHandle"]) is not str
                        or not 1 <= len(start["resumeHandle"]) <= 128
                    )
                )
            ):
                raise StopLive(4001, "invalid_message")
            await thin(intake.rate_limit, actor)
            lease = await thin(
                sessions.acquire,
                actor,
                start["caseId"],
                start["language"],
                start.get("resumeHandle"),
            )
            tools = LiveIntakeTools(
                intake,
                actor,
                start["caseId"],
                start["language"],
                processing_options=processing_options,
            )
            await thin(tools.case)
            muted = False
            pong_pending = False
            missed = 0
            queued_job: str | None = None
            announced_plan: str | None = None
            loop = asyncio.get_running_loop()
            rate_at, rate_bytes = loop.time(), 0
            scope_checked_at = loop.time()
            remaining = (
                datetime.fromisoformat(lease["expiresAt"].replace("Z", "+00:00")) - intake.clock()
            ).total_seconds()
            duration = min(config.max_session_seconds, remaining)
            if duration <= 0:
                raise StopLive(4408, "session_limit")
            async with AsyncExitStack() as stack:
                try:
                    upstream = await asyncio.wait_for(
                        stack.enter_async_context(
                            provider.connect(
                                tools=tools,
                                language=start["language"],
                                resume_handle=lease.get("providerHandle"),
                            )
                        ),
                        timeout=20,
                    )
                except Exception:
                    raise StopLive(4503, "model_unavailable") from None
                await send(
                    {
                        "type": "ready",
                        "sessionId": lease["sessionId"],
                        "outputAudio": {
                            "encoding": "pcm_s16le",
                            "sampleRateHz": 24000,
                            "channels": 1,
                        },
                        "limits": {"maxSessionSeconds": int(duration)},
                    }
                )
                # Deterministic visible first-action script; actual spoken fidelity
                # remains an explicit model/audio acceptance test.
                initial_reply = (
                    tools.distress_reply
                    if (await thin(tools.case))["flags"].get("distress")
                    else tools.first_action
                )
                await send(
                    {
                        "type": "caption",
                        "role": "assistant",
                        "text": initial_reply,
                        "final": True,
                        "lang": start["language"],
                        "turnId": await thin(tools.caption, "assistant", initial_reply),
                    }
                )

                async def input_loop():
                    nonlocal muted, pong_pending, rate_at, rate_bytes, scope_checked_at
                    while True:
                        message = await ws.receive()
                        if message["type"] == "websocket.disconnect":
                            return
                        # Bound storage reads independently of 20ms audio frames.
                        if loop.time() - scope_checked_at >= 2:
                            await thin(tools.case)
                            scope_checked_at = loop.time()
                        audio = message.get("bytes")
                        if audio is not None:
                            if not 640 <= len(audio) <= 1280 or len(audio) % 2:
                                raise StopLive(4001, "invalid_audio")
                            if loop.time() - rate_at >= 1:
                                rate_at, rate_bytes = loop.time(), 0
                            rate_bytes += len(audio)
                            if rate_bytes > 64000:
                                raise StopLive(4429, "rate_limited")
                            if not muted:
                                await asyncio.wait_for(upstream.send_audio(audio), timeout=5)
                            continue
                        raw = message.get("text")
                        if type(raw) is not str or len(raw.encode()) > config.max_control_bytes:
                            raise StopLive(4001, "invalid_message")
                        try:
                            item = json.loads(raw)
                        except (ValueError, RecursionError):
                            raise StopLive(4001, "invalid_message") from None
                        if type(item) is not dict:
                            raise StopLive(4001, "invalid_message")
                        kind = item.get("type")
                        if kind == "pong" and set(item) == {"type"}:
                            pong_pending = False
                        elif kind == "end" and set(item) == {"type"}:
                            raise StopLive(1000, "ended")
                        elif (
                            kind == "mute"
                            and set(item) == {"type", "muted"}
                            and type(item["muted"]) is bool
                        ):
                            muted = item["muted"]
                            await asyncio.wait_for(upstream.mute(muted), timeout=5)
                        elif (
                            kind == "text"
                            and set(item) == {"type", "text"}
                            and type(item["text"]) is str
                            and 1 <= len(item["text"]) <= 4000
                        ):
                            await thin(intake.rate_limit, actor)
                            observed = await thin(tools.observe, item["text"])
                            if observed["secret"]:
                                await send(
                                    {
                                        "type": "error",
                                        "code": "unsafe_content_blocked",
                                        "message": "Do not share secret codes or credentials.",
                                        "retryable": False,
                                    }
                                )
                                continue
                            await user_caption(observed["text"])
                            await asyncio.wait_for(upstream.send_text(observed["text"]), timeout=5)
                        else:
                            raise StopLive(4001, "invalid_message")

                async def output_loop():
                    nonlocal queued_job
                    audio = bytearray()
                    transcript = ""
                    input_text = ""
                    consecutive_tools = 0
                    tool_attempts = 0
                    async for event in upstream.events():
                        kind = event.get("type")
                        if kind == "audio":
                            chunk = event.get("audio")
                            if (
                                type(chunk) is not bytes
                                or len(chunk) % 2
                                or len(audio) + len(chunk) > config.max_output_audio_bytes
                            ):
                                raise StopLive(4500, "unsafe_content_blocked")
                            audio.extend(chunk)
                        elif kind == "output_text":
                            text = event.get("text")
                            if type(text) is not str or len(transcript) + len(text) > 4000:
                                raise StopLive(4500, "unsafe_content_blocked")
                            transcript += text
                        elif kind == "input_text":
                            if (
                                type(event.get("text")) is not str
                                or len(input_text) + len(event["text"]) > 4000
                            ):
                                raise StopLive(4001, "invalid_message")
                            if not input_text:
                                tools.begin_statement()
                            input_text += event["text"]
                            if event.get("final"):
                                await user_caption(input_text)
                                input_text = ""
                        elif kind == "interrupted":
                            tools.begin_statement()
                            audio.clear()
                            transcript = ""
                            await send({"type": "interrupted"})
                        elif kind == "tool":
                            name, call_id, arguments = (
                                event.get("name"),
                                event.get("id"),
                                event.get("arguments"),
                            )
                            if (
                                type(name) is not str
                                or type(call_id) is not str
                                or type(arguments) is not dict
                            ):
                                raise StopLive(4500, "invalid_tool")
                            tool_attempts += 1
                            result: dict[str, Any]
                            if tool_attempts > 80:
                                raise StopLive(4429, "rate_limited")
                            if consecutive_tools >= 2:
                                result = {"ok": False, "code": "tool_limit"}
                            else:
                                consecutive_tools += 1
                                try:
                                    result = await thin(tools.call, name, arguments, call_id)
                                except IntakeError as error:
                                    result = {
                                        "ok": False,
                                        "code": error.code
                                        if error.code
                                        in {
                                            "forbidden",
                                            "validation_failed",
                                            "unsafe_content_blocked",
                                            "idempotency_conflict",
                                            "budget_exceeded",
                                        }
                                        else "tool_unavailable",
                                    }
                            result = live_tool_response(result)
                            await asyncio.wait_for(
                                upstream.tool_response(call_id, name, result), timeout=5
                            )
                            if result.get("facts"):
                                await send(
                                    {
                                        "type": "facts_delta",
                                        "facts": result["facts"],
                                        "missingMinimum": result["missing_minimum"],
                                    }
                                )
                            if name == "flag_distress" and result.get("ok"):
                                await send({"type": "distress_ack", "level": arguments["level"]})
                            if result.get("upload_prompt_shown"):
                                await send({"type": "upload_requested", "kind": result["kind"]})
                            if result.get("queued"):
                                queued_job = result["jobId"]
                                await send({"type": "processing_queued", "jobId": result["jobId"]})
                        elif kind == "resumption":
                            handle = await thin(sessions.resumption, lease, event.get("handle"))
                            await send({"type": "session_resumption", **handle})
                        elif kind == "turn_complete":
                            if input_text:
                                await user_caption(input_text)
                                input_text = ""
                            case = await thin(tools.case)
                            if case["flags"].get("distress"):
                                audio.clear()
                                transcript = tools.distress_reply
                            if not transcript.strip() or not safe_live_output(transcript):
                                raise StopLive(4500, "unsafe_content_blocked")
                            await send(
                                {
                                    "type": "caption",
                                    "role": "assistant",
                                    "text": transcript,
                                    "final": True,
                                    "lang": start["language"],
                                    "turnId": await thin(tools.caption, "assistant", transcript),
                                }
                            )
                            # Audio is buffered until the complete transcript is checked.
                            # This is NOT proof that the audio says the same words.
                            for index in range(0, len(audio), 4800):
                                await send(bytes(audio[index : index + 4800]))
                            audio.clear()
                            transcript = ""
                            consecutive_tools = 0
                            tools.begin_statement()
                        elif kind == "error":
                            raise StopLive(4503, "model_unavailable")
                        else:
                            raise StopLive(4500, "invalid_provider_event")
                    raise StopLive(4503, "model_unavailable")

                async def user_caption(text: str):
                    observed = await thin(tools.observe, text)
                    await send(
                        {
                            "type": "caption",
                            "role": "user",
                            "text": observed["text"],
                            "final": True,
                            "lang": start["language"],
                            "turnId": await thin(tools.caption, "user", observed["text"]),
                        }
                    )
                    if observed["secret"]:
                        raise StopLive(4500, "unsafe_content_blocked")
                    if observed["distress"]:
                        await send({"type": "distress_ack", "level": "urgent"})

                async def heartbeat():
                    nonlocal pong_pending, missed, announced_plan
                    while True:
                        await asyncio.sleep(config.heartbeat_seconds)
                        await thin(tools.case)
                        if queued_job:
                            plan_id = await thin(tools.plan_ready, queued_job)
                            if plan_id and plan_id != announced_plan:
                                await send({"type": "plan_ready", "planId": plan_id})
                                announced_plan = plan_id
                        missed = missed + 1 if pong_pending else 0
                        if missed >= 2:
                            raise StopLive(4008, "heartbeat_timeout")
                        pong_pending = True
                        await send({"type": "ping"})

                async def deadline():
                    await asyncio.sleep(duration)
                    raise StopLive(4408, "session_limit")

                tasks = [
                    asyncio.create_task(coro())
                    for coro in (input_loop, output_loop, heartbeat, deadline)
                ]
                try:
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except StopLive as error:
            with suppress(Exception):
                await send({"type": "closed", "reason": error.reason})
                await ws.close(code=error.code)
        except WebSocketDisconnect:
            pass
        except IntakeError as error:
            with suppress(Exception):
                code = 4429 if error.status == 429 else 4403 if error.status in {403, 404} else 4500
                await send(
                    {"type": "closed", "reason": "session_limit" if code == 4429 else "forbidden"}
                )
                await ws.close(code=code)
        except Exception:
            with suppress(Exception):
                await send({"type": "closed", "reason": "model_unavailable"})
                await ws.close(code=4503)
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if lease:
                with suppress(Exception):
                    await asyncio.to_thread(sessions.release, lease)

    return app
