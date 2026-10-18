"""Allowlisted structured logs never serialize evidence or exception messages."""

import json
import logging
import math
import re
from datetime import UTC, datetime
from typing import cast

EVENT_NAMES = frozenset(
    {"identity.verification_failed", "request.failed", "model.call", "job.dispatch_deferred"}
)
EXCEPTION_TYPES = frozenset(
    {
        "ValueError",
        "TypeError",
        "TimeoutError",
        "RuntimeError",
        "KeyError",
        "ConnectionError",
        "OSError",
        "AssertionError",
    }
)
SERVICES = frozenset({"api", "live", "worker", "mcp", "a2a", "eval", "synth"})
AGENTS = frozenset(
    {
        "IntakeLiveAgent",
        "IntakeTextAgent",
        "EvidenceAgent",
        "ClassifierAgent",
        "JurisdictionResolver",
        "PlannerAgent",
        "PacketAgent",
        "VerifierAgent",
        "ReceiverBriefAgent",
        "ClusterExplainerAgent",
        "PackBuilderAgent",
        "PackCriticAgent",
        "ScammerSimAgent",
        "GuidanceBaselineAgent",
        "SafetyGuard",
    }
)
STATUSES = frozenset(
    {
        "ok",
        "failed",
        "queued",
        "running",
        "succeeded",
        "not_ready",
        "INTAKE",
        "CLASSIFIED",
        "PLAN_READY",
        "PACKETS_VERIFIED",
        "IN_PROGRESS",
        "RESOLVED",
        "CLOSED",
        "DRAFT",
        "NEEDS_HUMAN_REVIEW",
        "VERIFIED",
        "APPROVED",
        "SENT",
        "ACKNOWLEDGED",
        "NEEDS_INFO",
        "ACTIONED",
        "REJECTED",
    }
)
ERROR_CODES = EXCEPTION_TYPES | frozenset(
    {
        "unauthenticated",
        "app_check_failed",
        "forbidden",
        "timeout",
        "identity_unavailable",
        "internal_error",
        "validation_failed",
        "not_found",
        "not_implemented",
        "model_unavailable",
        "adapter_unavailable",
        "rate_limited",
    }
)
STRING_PATTERNS = {
    "case_ref": re.compile(r"RLY-\d{4}-\d{6}"),
    "request_id": re.compile(r"req_[a-f0-9]{32}"),
    "trace_id": re.compile(r"(?:trace_)?[a-f0-9]{32}"),
    "job_id": re.compile(r"(?:job_[a-f0-9]{32}|[a-f0-9]{64})"),
    "model_id": re.compile(
        r"gemini-3(?:\.\d{1,2})?-(?:flash(?:-lite)?|pro|live(?:-extended-thinking)?)(?:-preview(?:-\d{2}-\d{2})?|-\d{3})?"
    ),
    "prompt_version": re.compile(
        r"(?:intake_live|intake_text|evidence|classifier|planner|packet|verifier|receiver_brief|cluster_explainer|pack_builder|pack_critic|scammer_sim|guidance_baseline|safety_guard)\.v\d{1,4}"
    ),
}
MODEL_FAILURE_REASONS = frozenset(
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
ENUM_FIELDS = {
    "agent": AGENTS,
    "status": STATUSES,
    "error_code": ERROR_CODES,
    "service": SERVICES,
    "failure_reason": MODEL_FAILURE_REASONS,
}
SAFE_FIELDS = (
    frozenset(STRING_PATTERNS)
    | frozenset(ENUM_FIELDS)
    | {"latency_ms", "tokens_in", "tokens_out", "tokens_reasoning", "http_status"}
)


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Message text is a static event name, never arbitrary request/error text.
        event = (
            record.msg
            if type(record.msg) is str and record.msg in EVENT_NAMES
            else "redacted_event"
        )
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": {10: "DEBUG", 20: "INFO", 30: "WARNING", 40: "ERROR", 50: "CRITICAL"}.get(
                record.levelno, "UNKNOWN"
            )
            if type(record.levelno) is int
            else "UNKNOWN",
            "event": event,
        }
        for key in SAFE_FIELDS:
            value = getattr(record, key, None)
            if key in {"latency_ms", "tokens_in", "tokens_out", "tokens_reasoning", "http_status"}:
                bound = (
                    3_600_000
                    if key == "latency_ms"
                    else 599
                    if key == "http_status"
                    else 1_000_000_000
                )
                lower = 100 if key == "http_status" else 0
                numeric = type(value) in {int, float} if key == "latency_ms" else type(value) is int
                if numeric:
                    number = cast(int | float, value)
                    if lower <= number <= bound and math.isfinite(number):
                        payload[key] = number
            elif type(value) is str and len(value) <= 128:
                if (key in STRING_PATTERNS and STRING_PATTERNS[key].fullmatch(value)) or (
                    key in ENUM_FIELDS and value in ENUM_FIELDS[key]
                ):
                    payload[key] = value
        if record.exc_info:
            # Exception names can themselves be chosen by application/user code.
            name = record.exc_info[0].__name__ if record.exc_info[0] else "unknown"
            payload["exception_type"] = name if name in EXCEPTION_TYPES else "unknown"
        return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def emit_model_call(**metadata: object) -> None:
    """Validate before emitting, so alternate handlers never receive secret-shaped extras."""
    safe: dict[str, object] = {}
    for key, value in metadata.items():
        if key in {"model_id", "agent", "service", "status", "failure_reason"}:
            if (
                type(value) is str
                and len(value) <= 128
                and (
                    (key in STRING_PATTERNS and STRING_PATTERNS[key].fullmatch(value))
                    or (key in ENUM_FIELDS and value in ENUM_FIELDS[key])
                )
            ):
                safe[key] = value
        elif key in {"latency_ms", "tokens_in", "tokens_out", "tokens_reasoning", "http_status"}:
            bound = (
                3_600_000 if key == "latency_ms" else 599 if key == "http_status" else 1_000_000_000
            )
            lower = 100 if key == "http_status" else 0
            if type(value) is int and lower <= value <= bound:
                safe[key] = value
    logging.getLogger("relay.model").info("model.call", extra=safe)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    logging.getLogger("relay").handlers = [handler]
    logging.getLogger("relay").setLevel(logging.INFO)
    logging.getLogger("relay").propagate = False
