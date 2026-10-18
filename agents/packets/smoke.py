"""Explicitly authorized three-recipient synthetic live smoke; no hidden reruns."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from agents.intake.clients import GoogleGenAIClient, ModelClient, ModelFailure
from agents.packets import PacketPipeline, RetryPacketClient
from agents.packets.core import WriterOutput
from packages.common.settings import Settings
from packages.packs.registry import PackRegistry
from packages.safety.guard import SafetyGuard, scrub_credentials
from packages.schemas import CaseFacts, Plan


class CappedClient:
    mode: Literal["live"] = "live"

    def __init__(
        self,
        client: ModelClient,
        *,
        usage_source: GoogleGenAIClient,
        ledger_path: Path,
        synthetic_input_hash: str | None = None,
    ) -> None:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("x", encoding="utf-8"):
            pass
        self.ledger_path, self.usage_source = ledger_path, usage_source
        self.synthetic_input_hash = synthetic_input_hash
        self.snapshot_path: Path | None = None
        if synthetic_input_hash is not None:
            if not re.fullmatch(r"[a-f0-9]{64}", synthetic_input_hash):
                raise ValueError("synthetic_input_hash_required")
            self.snapshot_path = ledger_path.with_suffix(".drafts.jsonl")
            with self.snapshot_path.open("x", encoding="utf-8"):
                pass
        self.ledger: list[dict[str, Any]] = []
        self.client = client
        self.model_id = client.model_id
        self.attempts = 0
        self.failures: list[str] = []

    def record_retry(self, event: dict[str, Any]) -> None:
        self.ledger.append(event)
        with self.ledger_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=True) + "\n")

    async def generate(
        self,
        *,
        prompt: str,
        data: dict[str, Any],
        schema: type[BaseModel],
        media: tuple[str, bytes] | None = None,
    ) -> str:
        if self.attempts >= 18:
            raise ModelFailure("smoke_request_limit")
        self.attempts += 1
        started = time.monotonic()
        record: dict[str, Any] = {
            "event": "provider_attempt",
            "attempt": self.attempts,
            "schemaName": schema.__name__,
            "stage": {
                "WriterOutput": "writer",
                "EntailmentOutput": "verifier",
                "Classification": "classifier",
            }.get(schema.__name__, "other"),
            "repairCheckIds": [
                c
                for c in data.get("repairChecks", [])
                if isinstance(c, str) and re.fullmatch(r"[a-z0-9_]{1,80}", c)
            ],
            "reason": "success",
            "statusCode": None,
        }
        usage_start = len(self.usage_source.usage_records)
        try:
            raw = await self.client.generate(prompt=prompt, data=data, schema=schema, media=media)
            if self.snapshot_path is not None and schema is WriterOutput:
                try:
                    output = WriterOutput.model_validate_json(raw)
                    text = json.dumps(output.model_dump(), ensure_ascii=False)
                    if (
                        len(raw) > 16000
                        or scrub_credentials(text) != text
                        or not SafetyGuard().inspect_output(text).allow
                    ):
                        record["snapshotRejected"] = "unsafe_or_oversized"
                    else:
                        snapshot = {
                            "attempt": self.attempts,
                            "verified": False,
                            "synthetic": True,
                            "inputSha256": self.synthetic_input_hash,
                            "recipientId": data.get("recipient", {}).get("id"),
                            "writerOutput": output.model_dump(),
                        }
                        with self.snapshot_path.open("a", encoding="utf-8") as stream:
                            stream.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
                        record["snapshotSaved"] = True
                except ValueError:
                    record["snapshotRejected"] = "schema_invalid"
            return raw
        except asyncio.CancelledError:
            record["reason"] = "cancelled"
            self.failures.append("cancelled")
            raise
        except ModelFailure as error:
            record.update(reason=error.reason, statusCode=error.status_code)
            self.failures.append(error.reason)
            raise
        finally:
            record["latencyMs"] = round((time.monotonic() - started) * 1000)
            record["usage"] = self.usage_source.usage_records[usage_start:]
            self.ledger.append(record)
            # Flush each completed call, so an interrupted batch keeps failure evidence.
            with self.ledger_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=True) + "\n")


async def run(args: argparse.Namespace) -> dict[str, Any]:
    raw = args.input.read_bytes()
    if len(raw) > 48000:
        raise ValueError("input_bounds")
    data = json.loads(raw)
    if data.get("synthetic") is not True or data.get("draftPreview") is not True:
        raise ValueError("explicit_synthetic_and_draft_preview_required")
    facts, plan = CaseFacts.model_validate(data["facts"]), Plan.model_validate(data["plan"])
    registry = PackRegistry(Path("packs"))
    pack = next(
        (
            p
            for p in registry.available(
                allow_draft_preview=True, environment="local", demo_mode=True
            )
            if p.pack_id == plan.pack_id and p.version == plan.pack_version
        ),
        None,
    )
    if pack is None or [s.recipient_id for s in plan.steps] != ["bank", "cyber", "payment-app"]:
        raise ValueError("three_recipient_plan_required")
    sdk = GoogleGenAIClient(
        Settings(
            genai_mode="live",
            service="api",
            intake_enabled=True,
            gcp_project_id="demo-relay-local",
            model_reasoning=args.model,
            genai_project_id=args.project,
            genai_location=args.location,
            max_model_concurrency=1,
            packet_thinking_level=args.packet_thinking_level,
        )
    )
    client = CappedClient(
        sdk.for_packets(),
        usage_source=sdk,
        ledger_path=args.output.with_suffix(".attempts.jsonl"),
        synthetic_input_hash=hashlib.sha256(raw).hexdigest(),
    )
    logical_client: ModelClient = (
        RetryPacketClient(client, on_retry=client.record_retry) if args.transient_retry else client
    )
    results: list[dict[str, Any]] = []
    try:
        for step in plan.steps:
            start = time.monotonic()
            try:
                async with asyncio.timeout(120):
                    result = await PacketPipeline(
                        logical_client, timeout=35 if args.transient_retry else 20
                    ).build(
                        facts=facts,
                        plan_step=step,
                        recipient=next(r for r in pack.recipients if r.id == step.recipient_id),
                        pack=pack,
                        source_passages=registry.passages(pack),
                        evidence=[],
                        victim_language=data.get("victimLanguage", "en"),
                        recipient_language="en",
                        attachments=[],
                    )
            except TimeoutError:
                results.append(
                    {
                        "recipient": step.recipient_id,
                        "status": "NEEDS_HUMAN_REVIEW",
                        "writerAttempts": None,
                        "latencySeconds": time.monotonic() - start,
                        "checks": [
                            {
                                "id": "recipient_deadline",
                                "type": "deterministic",
                                "passed": False,
                                "severity": "blocker",
                                "detail": "Recipient120second deadline exceeded.",
                            }
                        ],
                        "content": None,
                    }
                )
                continue
            results.append(
                {
                    "recipient": step.recipient_id,
                    "status": result.status,
                    "writerAttempts": result.attempts,
                    "attemptHistory": result.attempt_history,
                    "latencySeconds": time.monotonic() - start,
                    "checks": [c.model_dump(mode="json", by_alias=True) for c in result.checks],
                    "content": result.content.model_dump(mode="json", by_alias=True)
                    if result.content
                    else None,
                }
            )
    finally:
        await sdk.close()
    return {
        "runAt": datetime.now(UTC).isoformat(),
        "inputSha256": hashlib.sha256(raw).hexdigest(),
        "model": args.model,
        "project": args.project,
        "processingLocation": args.location,
        "sdkVersion": importlib.metadata.version("google-genai"),
        "n": 3,
        "providerAttempts": client.attempts,
        "providerFailures": client.failures,
        "attemptLedger": client.ledger,
        "sdkFailures": sdk.failure_records,
        "packetThinkingLevel": args.packet_thinking_level,
        "writerMaxOutputTokens": 2500,
        "transientRetry": args.transient_retry,
        "logicalDeadlineSeconds": 35 if args.transient_retry else 20,
        "usage": sdk.usage_records,
        "cost": None,
        "costNote": "No fabricated monetary estimate; usage recorded where SDK supplied it.",
        "limitations": [
            "Synthetic smoke n=3; no production accuracy claim.",
            "Draft sources remain unverified; model entailment is fallible.",
        ],
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--packet-thinking-level", choices=["LOW"], default=None)
    parser.add_argument("--transient-retry", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error(
            "Explicit --live and parent authorization required; this command makes billable calls."
        )
    if args.output.exists():
        parser.error("Output must be unique; preserve previous failures.")
    report = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {"n": 3, "providerAttempts": report["providerAttempts"], "report": str(args.output)}
        )
    )


if __name__ == "__main__":
    main()
