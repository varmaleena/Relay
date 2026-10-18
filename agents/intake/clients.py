"""Bounded Google SDK access; no API mutation tools, raw inputs, or tokens logged."""

import asyncio
import json
import time
from typing import Any, Literal, Protocol

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel

from packages.common.logging import emit_model_call
from packages.common.settings import Settings


class ModelFailure(RuntimeError):
    """Sanitized error with allowlisted machine diagnostics, never provider prose."""

    REASONS = frozenset(
        {
            "http_400",
            "http_401",
            "http_403",
            "http_404",
            "http_408",
            "http_429",
            "http_500",
            "http_502",
            "http_503",
            "http_504",
            "http_other",
            "connect_timeout",
            "read_timeout",
            "timeout",
            "transport_error",
            "cancelled",
            "empty_response",
            "oversized_response",
            "unknown",
        }
    )

    def __init__(
        self, message: str, *, status_code: int | None = None, reason: str = "unknown"
    ) -> None:
        super().__init__(message)
        self.status_code = (
            status_code
            if status_code in {400, 401, 403, 404, 408, 429, 500, 502, 503, 504}
            else None
        )
        self.reason = reason if reason in self.REASONS else "unknown"


def _failure_reason(error: Exception) -> tuple[int | None, str]:
    """Classify actual exception attributes/types; never guess from message text."""
    code = getattr(error, "code", None)
    if isinstance(code, int) and 100 <= code <= 599:
        return code, f"http_{code}" if f"http_{code}" in ModelFailure.REASONS else "http_other"
    if isinstance(error, httpx.ConnectTimeout):
        return None, "connect_timeout"
    if isinstance(error, httpx.ReadTimeout):
        return None, "read_timeout"
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return None, "timeout"
    if isinstance(error, httpx.TransportError):
        return None, "transport_error"
    return None, "unknown"


def provider_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Project canonical schema onto Vertex's supported responseSchema subset.

    Local Pydantic validation remains strict, including omitted size/extra rules.
    References are expanded; unconstrained maps are omitted from optional output.
    """
    root = schema.model_json_schema(by_alias=True)
    definitions = root.get("$defs", {})
    supported = {"type", "properties", "items", "enum", "required", "format", "anyOf"}

    def convert(node: dict[str, Any]) -> dict[str, Any]:
        if "$ref" in node:
            return convert(definitions[node["$ref"].rsplit("/", 1)[1]])
        if "anyOf" in node:
            choices = [choice for choice in node["anyOf"] if choice.get("type") != "null"]
            if len(choices) == 1:
                return convert(choices[0])
        result = {key: value for key, value in node.items() if key in supported}
        if "properties" in result:
            properties = {key: convert(value) for key, value in result["properties"].items()}
            # Provenance maps are assigned by trusted server code, not model output.
            properties.pop("fieldProvenance", None)
            properties.pop("span", None)
            properties.pop("degraded", None)
            properties.pop("failureCode", None)
            result["properties"] = properties
            if "required" in result:
                result["required"] = [name for name in result["required"] if name in properties]
        if "items" in result:
            result["items"] = convert(result["items"])
        if "anyOf" in result:
            result["anyOf"] = [convert(choice) for choice in result["anyOf"]]
        return result

    return convert(root)


class ModelClient(Protocol):
    model_id: str

    @property
    def mode(self) -> Literal["live", "fake", "replay"]: ...

    async def generate(
        self,
        *,
        prompt: str,
        data: dict[str, Any],
        schema: type[BaseModel],
        media: tuple[str, bytes] | None = None,
    ) -> str: ...


class GoogleGenAIClient:
    """ADC-backed Vertex SDK; configured explicit 3.x model and no automatic tools."""

    mode: Literal["live"] = "live"

    def __init__(self, settings: Settings, *, sdk_client: Any = None) -> None:
        if settings.genai_mode != "live" or not settings.model_reasoning:
            raise ValueError("live client requires configured live model")
        self.model_id = settings.model_reasoning
        self._service = settings.service
        self._packet_thinking_level = settings.packet_thinking_level
        self.usage_records: list[dict[str, Any]] = []
        self.failure_records: list[dict[str, Any]] = []
        self._semaphore = asyncio.Semaphore(settings.max_model_concurrency)
        self._client = sdk_client or genai.Client(
            vertexai=True,
            project=settings.genai_project_id or settings.gcp_project_id,
            location=settings.genai_location,
            http_options=types.HttpOptions(
                api_version="v1",
                timeout=15000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    async def generate(
        self,
        *,
        prompt: str,
        data: dict[str, Any],
        schema: type[BaseModel],
        media: tuple[str, bytes] | None = None,
    ) -> str:
        async with self._semaphore:
            return await self._generate(prompt=prompt, data=data, schema=schema, media=media)

    def for_packets(self) -> "PacketModelClient":
        """Share transport/semaphore; opt-in settings affect packets only."""
        if self._packet_thinking_level and self.model_id != "gemini-3.8-flash":
            raise ValueError("packet LOW capability verified only for gemini-3.8-flash")
        return PacketModelClient(self)

    def for_packbuilder(self) -> "PackBuilderModelClient":
        """Explicit 8000-token/0.1 extraction profile sharing transport and bounds."""
        return PackBuilderModelClient(self)

    async def _generate(
        self,
        *,
        prompt: str,
        data: dict[str, Any],
        schema: type[BaseModel],
        media: tuple[str, bytes] | None = None,
        packet_profile: bool = False,
        packbuilder_profile: bool = False,
    ) -> str:
        parts = [types.Part.from_text(text=json.dumps(data, ensure_ascii=False))]
        if media:
            parts.append(types.Part.from_bytes(data=media[1], mime_type=media[0]))
        is_writer = packet_profile and schema.__name__ == "WriterOutput"
        thinking = (
            types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
            if packet_profile and self._packet_thinking_level == "LOW"
            else None
        )
        config = types.GenerateContentConfig(
            system_instruction=prompt,
            temperature=0.1 if packbuilder_profile else (0.3 if is_writer else 0.0),
            max_output_tokens=8000 if packbuilder_profile else (2500 if is_writer else 2000),
            thinking_config=thinking,
            response_mime_type="application/json",
            response_json_schema=provider_schema(schema),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        contents = types.Content(role="user", parts=parts)
        generate = self._client.aio.models.generate_content
        started = time.monotonic()
        call_status = "failed"
        call_reason: str | None = "unknown"
        call_http: int | None = None
        call_usage: Any = None
        try:
            try:
                response = await generate(model=self.model_id, contents=contents, config=config)
            except asyncio.CancelledError:
                call_reason = "cancelled"
                self.failure_records.append(
                    {
                        "schemaName": schema.__name__,
                        "reason": "cancelled",
                        "statusCode": None,
                        "latencyMs": round((time.monotonic() - started) * 1000),
                    }
                )
                raise
            except Exception as error:
                code, reason = _failure_reason(error)
                call_reason, call_http = reason, code
                suffix = str(code) if code is not None else reason
                self.failure_records.append(
                    {
                        "schemaName": schema.__name__,
                        "reason": reason,
                        "statusCode": code,
                        "latencyMs": round((time.monotonic() - started) * 1000),
                    }
                )
                message = getattr(error, "message", "") or ""
                known_fields = (
                    "responseJsonSchema",
                    "responseSchema",
                    "additionalProperties",
                    "maxOutputTokens",
                    "systemInstruction",
                    "anyOf",
                    "properties",
                    "generationConfig",
                    "minLength",
                    "maxLength",
                    "span",
                )
                names = [name for name in known_fields if name.lower() in str(message).lower()]
                if names:
                    suffix += ":" + ",".join(names)
                raise ModelFailure(
                    f"model_unavailable:{suffix}", status_code=code, reason=reason
                ) from None
            usage = response.usage_metadata
            call_usage = usage
            self.usage_records.append(
                {
                    "model": self.model_id,
                    "latencyMs": round((time.monotonic() - started) * 1000),
                    "inputTokens": getattr(usage, "prompt_token_count", None),
                    "outputTokens": getattr(usage, "candidates_token_count", None),
                    "reasoningTokens": getattr(usage, "thoughts_token_count", None),
                }
            )
            if not response.text or len(response.text) > 100000:
                reason = "empty_response" if not response.text else "oversized_response"
                call_reason = reason
                self.failure_records.append(
                    {
                        "schemaName": schema.__name__,
                        "reason": reason,
                        "statusCode": None,
                        "latencyMs": round((time.monotonic() - started) * 1000),
                    }
                )
                raise ModelFailure("model_response_empty_or_oversized", reason=reason)
            call_status, call_reason = "ok", None
            return str(response.text)
        finally:
            agent = {
                "IntakeModelOutput": "IntakeTextAgent",
                "EvidenceModelOutput": "EvidenceAgent",
                "Classification": "ClassifierAgent",
                "WriterOutput": "PacketAgent",
                "EntailmentOutput": "VerifierAgent",
                "ReceiverBriefModelOutput": "ReceiverBriefAgent",
                "ReceiverBriefEntailmentOutput": "ReceiverBriefAgent",
            }.get(schema.__name__)
            if packbuilder_profile:
                agent = "PackBuilderAgent"
            emit_model_call(
                model_id=self.model_id,
                agent=agent,
                service=self._service,
                status=call_status,
                failure_reason=call_reason,
                http_status=call_http,
                latency_ms=round((time.monotonic() - started) * 1000),
                tokens_in=getattr(call_usage, "prompt_token_count", None),
                tokens_out=getattr(call_usage, "candidates_token_count", None),
                tokens_reasoning=getattr(call_usage, "thoughts_token_count", None),
            )

    async def close(self) -> None:
        await self._client.aio.aclose()


class PacketModelClient:
    """No second SDK client, close ownership or independent concurrency bucket."""

    mode: Literal["live"] = "live"

    def __init__(self, parent: GoogleGenAIClient) -> None:
        self.parent = parent
        self.model_id = parent.model_id

    async def generate(
        self,
        *,
        prompt: str,
        data: dict[str, Any],
        schema: type[BaseModel],
        media: tuple[str, bytes] | None = None,
    ) -> str:
        if schema.__name__ not in {"WriterOutput", "EntailmentOutput"}:
            raise ValueError("packet_profile_schema_not_allowed")
        async with self.parent._semaphore:
            return await self.parent._generate(
                prompt=prompt, data=data, schema=schema, media=media, packet_profile=True
            )


class PackBuilderModelClient:
    """Five strict extraction schemas plus critic; shared SDK and concurrency cap."""

    mode: Literal["live"] = "live"

    def __init__(self, parent: GoogleGenAIClient) -> None:
        self.parent = parent
        self.model_id = parent.model_id

    async def generate(
        self,
        *,
        prompt: str,
        data: dict[str, Any],
        schema: type[BaseModel],
        media: tuple[str, bytes] | None = None,
    ) -> str:
        # Lazy imports avoid the workflow -> ModelFailure import cycle. Check actual
        # class identity, not a caller-controlled class name or model-provided label.
        from agents.packbuilder.models import (
            CriticOutput,
            DeadlinesPass,
            RecipientsPass,
            RemediesPass,
            SequencingPass,
            SupportPass,
        )

        allowed = {
            RecipientsPass,
            DeadlinesPass,
            RemediesPass,
            SequencingPass,
            SupportPass,
            CriticOutput,
        }
        if schema not in allowed or media is not None:
            raise ValueError("packbuilder_profile_schema_not_allowed")
        async with self.parent._semaphore:
            return await self.parent._generate(
                prompt=prompt, data=data, schema=schema, packbuilder_profile=True
            )


class FixtureModelClient:
    """Explicit fake mode: exact hand-authored fixtures, no claimed model accuracy."""

    model_id = "fixture-fake"
    mode: Literal["fake"] = "fake"

    def __init__(self, fixtures: list[dict[str, Any]] | None = None) -> None:
        self.fixtures = fixtures or []
        self.calls = 0

    async def generate(
        self,
        *,
        prompt: str,
        data: dict[str, Any],
        schema: type[BaseModel],
        media: tuple[str, bytes] | None = None,
    ) -> str:
        self.calls += 1
        source = data.get("untrustedText", "")
        for fixture in self.fixtures:
            if source == fixture.get("text"):
                return json.dumps(fixture.get("intake", {"factsDelta": {}}), ensure_ascii=False)
            if source == fixture.get("evidenceText"):
                return json.dumps(fixture["extraction"], ensure_ascii=False)
        if schema.__name__ == "IntakeModelOutput":
            return '{"factsDelta": {}}'
        return json.dumps(
            {
                "documentType": "other",
                "entities": [],
                "summary": "No fixture extraction available.",
                "confidence": 0,
                "injectionSuspected": False,
                "notes": "Fake mode.",
            }
        )
