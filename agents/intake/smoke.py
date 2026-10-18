"""Explicit capped synthetic extraction smoke; never run during normal unit tests."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from packages.common.settings import Settings

from .clients import GoogleGenAIClient, ModelFailure
from .core import EvidenceAgent


async def run(project: str, location: str, model: str, limit: int, offset: int = 0) -> dict:
    fixtures = json.loads(
        (Path(__file__).parents[2] / "tests/fixtures/intake/cases.json").read_text(encoding="utf-8")
    )[offset : offset + limit]
    settings = Settings(
        environment="local",
        genai_mode="live",
        intake_enabled=True,
        gcp_project_id="demo-relay-local",
        genai_project_id=project,
        genai_location=location,
        model_reasoning=model,
        max_model_concurrency=2,
    )
    client = GoogleGenAIClient(settings)
    semaphore = asyncio.Semaphore(2)

    async def one(fixture: dict) -> dict:
        async with semaphore:
            try:
                result = await EvidenceAgent(client, schema_retries=0, timeout=20).extract(
                    evidence_id=fixture["id"],
                    mime="text/plain",
                    content=fixture["evidenceText"],
                    case_language=fixture["language"],
                )
                actual = {(entity.type, entity.raw_value) for entity in result.entities}
                required = {
                    (entity["type"], entity["rawValue"])
                    for entity in fixture["extraction"]["entities"]
                }
                return {
                    "caseId": fixture["id"],
                    "language": fixture["language"],
                    "status": "validated",
                    "requiredFields": len(required),
                    "matchedFields": len(required & actual),
                    "allRequiredMatched": required <= actual,
                    "entityCount": len(result.entities),
                }
            except (ModelFailure, ValueError) as error:
                return {"caseId": fixture["id"], "status": "failed", "code": str(error)}

    try:
        results = await asyncio.gather(*(one(fixture) for fixture in fixtures))
    finally:
        await client.close()
    input_tokens = sum(record["inputTokens"] or 0 for record in client.usage_records)
    output_tokens = sum(
        (record["outputTokens"] or 0) + (record["reasoningTokens"] or 0)
        for record in client.usage_records
    )
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "mode": "live",
        "synthetic": True,
        "model": model,
        "project": project,
        "processingLocation": location,
        "dataset": "M1-hand-authored-text-receipts-v1",
        "usageIncomplete": len(client.usage_records) != len(fixtures),
        "promptVersion": "evidence.v1",
        "promptHash": hashlib.sha256(
            (Path(__file__).parents[1] / "prompts/evidence.v1.md").read_bytes()
        ).hexdigest(),
        "n": len(fixtures),
        "requestsMax": limit,
        "maxConcurrency": 2,
        "maxOutputTokens": 2000,
        "schemaRetries": 0,
        "validatedCases": sum(item["status"] == "validated" for item in results),
        "inputTokens": input_tokens,
        "outputAndReasoningTokens": output_tokens,
        "conservativeModelCostUsd": (input_tokens * 1.5 + output_tokens * 7.5) / 1000000,
        "pricing": "Conservative global 2027 estimate; excludes infrastructure/credits/FX.",
        "limitations": (
            "Text-only synthetic receipts; required-field matching is not complete "
            "entity F1 or screenshot OCR accuracy."
        ),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 20 or not 0 <= args.offset or args.offset + args.limit > 20:
        parser.error("limit must be 1..20 and offset+limit cannot exceed20")
    report = asyncio.run(run(args.project, args.location, args.model, args.limit, args.offset))
    target = Path(args.output).resolve()
    permitted = (Path(__file__).parents[2] / "tests/fixtures/intake").resolve()
    if not target.is_relative_to(permitted):
        parser.error("report must remain in tests/fixtures/intake")
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))
    return int(report["validatedCases"] != report["n"])


if __name__ == "__main__":
    raise SystemExit(main())
