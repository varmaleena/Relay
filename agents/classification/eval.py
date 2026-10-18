"""M2 offline fixture consistency through actual ADK and deterministic pack planning."""

import argparse
import asyncio
import hashlib
import json
import math
import time
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from agents.classification import ClassifierAgent, FixtureClassifierClient
from agents.intake.clients import GoogleGenAIClient, ModelClient, ModelFailure
from agents.workflows.planning import PlanningWorkflow
from packages.common.settings import Settings
from packages.packs.registry import PackRegistry
from packages.schemas.models import CaseFacts, Classification, Plan


def wilson(k: int, n: int) -> list[float]:
    z = 1.959963984540054
    center = (k / n + z * z / (2 * n)) / (1 + z * z / n)
    width = z * math.sqrt(k / n * (1 - k / n) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [center - width, center + width]


async def evaluate(
    fixtures: list[dict[str, Any]],
    *,
    registry: PackRegistry,
    now: datetime,
    live_client: ModelClient | None = None,
) -> dict[str, Any]:
    if not fixtures or len(fixtures) > 20:
        raise ValueError("smoke_requires_1_to_20_cases")
    if live_client is not None and len(fixtures) != 20:
        raise ValueError("live_smoke_requires_exactly_20_cases")
    results: list[dict[str, Any]] = []
    confusion: Counter[str] = Counter()
    for fixture in fixtures:
        facts = CaseFacts.model_validate(fixture["facts"])
        workflow = PlanningWorkflow(
            ClassifierAgent(
                live_client or FixtureClassifierClient(fixture["modelOutput"]), schema_retries=0
            ),
            registry,
            environment="local",
            demo_mode=True,
            allow_draft_preview=True,
        )
        start = time.perf_counter()
        try:
            output = await workflow.execute(
                uid="synthetic-smoke",
                facts=facts.model_dump(mode="json", by_alias=True),
                facts_revision=1,
                history=[{"text": fixture["narration"], "at": now.isoformat()}],
                evidence=[],
                now=now,
                language=fixture["language"],
                preview_draft=True,
            )
            classified = Classification.model_validate(output["classification"])
            confusion[f"{fixture['expectedAuthorization']}:{classified.authorization_type}"] += 1
            result = {
                "caseId": fixture["id"],
                "outcome": output["outcome"],
                "authorizationCorrect": classified.authorization_type
                == fixture["expectedAuthorization"],
                "typologyCorrect": classified.typology == fixture["expectedTypology"],
                "urgency": classified.urgency.level,
                "urgencyCorrect": classified.urgency.level == fixture["expectedUrgency"],
                "requiresClarification": classified.needs_human_review,
            }
            if output.get("plan"):
                plan = Plan.model_validate(output["plan"])
                actual = [step.recipient_id for step in plan.steps]
                expected = fixture["expectedRecipients"]
                result.update(
                    recipients=actual,
                    recipientOrderCorrect=actual == expected,
                    draftPreview=plan.draft_preview,
                    packVersion=plan.pack_version,
                    hasUnverifiedNotice=bool(plan.unverified_notices),
                    noInventedNumericDeadline=all(
                        step.deadline is None or step.deadline.due_at is None for step in plan.steps
                    ),
                )
            results.append(result)
        except Exception as error:
            results.append(
                {
                    "caseId": fixture["id"],
                    "outcome": "failed",
                    "errorType": type(error).__name__,
                    "failureCode": str(error)
                    if str(error) in {"model_unavailable", "schema_invalid", "unsafe_output"}
                    else None,
                }
            )
        results[-1]["latencyMs"] = (time.perf_counter() - start) * 1000
    n = len(results)
    times = sorted(item["latencyMs"] for item in results)
    metrics = []
    for field in ("authorizationCorrect", "typologyCorrect", "urgencyCorrect"):
        k = sum(bool(item.get(field)) for item in results)
        metrics.append(
            {"metric": field, "correct": k, "n": n, "value": k / n, "ci95": wilson(k, n)}
        )
    planned = [item for item in results if item["outcome"] == "planned"]
    return {
        "mode": "live" if live_client else "fake",
        "synthetic": True,
        "model": live_client.model_id if live_client else "fixture-fake",
        "n": n,
        "claimBoundary": (
            "Small synthetic live smoke; not production accuracy or an SLO."
            if live_client
            else "Offline fixture consistency, not live AI accuracy or production latency."
        ),
        "orchestration": "Actual ADK Workflow, FunctionNode and Runner",
        "evaluationClock": now.isoformat(),
        "sdkVersions": {
            "google-adk": version("google-adk"),
            "google-genai": version("google-genai"),
        },
        "draftPreviewExplicit": True,
        "humanPackReview": "pending",
        "metrics": metrics,
        "authorizationConfusionCounts": dict(confusion),
        "outcomes": dict(Counter(item["outcome"] for item in results)),
        "recipientOrderChecks": {
            "correct": sum(item["recipientOrderCorrect"] for item in planned),
            "n": len(planned),
        },
        "latency": {"meanMs": sum(times) / n, "p95Ms": times[math.ceil(0.95 * n) - 1], "n": n},
        "results": results,
    }


class CappedClient:
    """One request per fixture; never forwards gold/fixture response information."""

    def __init__(self, client: ModelClient) -> None:
        self.client = client
        self.model_id = client.model_id
        self.requests = 0

    @property
    def mode(self):
        return self.client.mode

    async def generate(self, **kwargs: Any) -> str:
        forbidden = {
            "modelOutput",
            "expectedAuthorization",
            "expectedTypology",
            "expectedRecipients",
            "expectedUrgency",
        }
        if forbidden.intersection(kwargs["data"]):
            raise ValueError("gold_input_leak")
        if self.requests >= 20:
            raise ModelFailure("model_request_budget_exceeded")
        self.requests += 1
        return await self.client.generate(**kwargs)


async def run_live(
    fixtures: list[dict[str, Any]],
    registry: PackRegistry,
    now: datetime,
    project: str,
    location: str,
    model: str,
) -> dict[str, Any]:
    if len(fixtures) != 20:
        raise ValueError("live_smoke_requires_exactly_20_cases")
    settings = Settings(
        genai_mode="live",
        intake_enabled=True,
        gcp_project_id="demo-relay-local",
        genai_project_id=project,
        genai_location=location,
        model_reasoning=model,
        max_model_concurrency=2,
    )
    client = GoogleGenAIClient(settings)
    capped = CappedClient(client)
    try:
        report = await evaluate(fixtures, registry=registry, now=now, live_client=capped)
    finally:
        await client.close()
    input_tokens = sum(item["inputTokens"] or 0 for item in client.usage_records)
    output_tokens = sum(
        (item["outputTokens"] or 0) + (item["reasoningTokens"] or 0)
        for item in client.usage_records
    )
    report.update(
        provider="Google GenAI Vertex backend",
        project=project,
        processingLocation=location,
        requestsAttempted=capped.requests,
        maxConcurrency=2,
        schemaRetries=0,
        httpAttempts=1,
        maxOutputTokens=2000,
        inputTokens=input_tokens,
        outputAndReasoningTokens=output_tokens,
        usageIncomplete=len(client.usage_records) != capped.requests,
        modelCostEstimateUsd=(input_tokens * 1.5 + output_tokens * 7.5) / 1000000,
        pricingBasis=(
            "Recorded assumption: input1.50/output7.50 USD per1M, not verified current pricing; "
            "excludes infrastructure/FX/unreported usage."
        ),
        costRatesVerifiedCurrent=False,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--live", action="store_true", help="Explicit paid synthetic model evaluation"
    )
    parser.add_argument("--project")
    parser.add_argument("--location")
    parser.add_argument("--model")
    args = parser.parse_args()
    root = Path(__file__).parents[2]
    source = root / "tests/fixtures/classification/cases.json"
    target = Path(args.output).resolve()
    if not target.is_relative_to((root / "tests/fixtures/classification").resolve()):
        parser.error("report must stay under tests/fixtures/classification")
    fixtures = json.loads(source.read_text(encoding="utf8"))
    registry = PackRegistry(root / "packs")
    clock = datetime(2026, 10, 14, 6, tzinfo=UTC)
    if args.live:
        if not all((args.project, args.location, args.model)):
            parser.error("--live requires explicit --project --location --model")
        if target.exists():
            parser.error("live report exists; refusing accidental rerun/overwrite")
        report = asyncio.run(
            run_live(fixtures, registry, clock, args.project, args.location, args.model)
        )
    else:
        report = asyncio.run(evaluate(fixtures, registry=registry, now=clock))
    report.update(
        datasetHash=hashlib.sha256(source.read_bytes()).hexdigest(),
        promptVersion="classifier.v1",
        promptHash=hashlib.sha256(
            (root / "agents/prompts/classifier.v1.md").read_bytes()
        ).hexdigest(),
        generatedAt=datetime.now(UTC).isoformat(),
        catalogHashes={
            pack.pack_id + ":" + pack.version: hashlib.sha256(
                pack.model_dump_json().encode()
            ).hexdigest()
            for pack in registry.available(
                allow_draft_preview=True, environment="local", demo_mode=True
            )
        },
    )
    target.write_text(json.dumps(report, indent=2), encoding="utf8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("mode", "n", "outcomes", "metrics", "recipientOrderChecks", "latency")
            },
            indent=2,
        )
    )
    return int(any(item["outcome"] == "failed" for item in report["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
