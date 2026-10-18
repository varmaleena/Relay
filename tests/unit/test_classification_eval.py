import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from agents.classification.eval import evaluate
from packages.packs.registry import PackRegistry

ROOT = Path(__file__).parents[2]
FIXTURES = json.loads(
    (ROOT / "tests/fixtures/classification/cases.json").read_text(encoding="utf8")
)


def test_offline_smoke_real_adk_and_registry_integrity():
    report = asyncio.run(
        evaluate(
            FIXTURES,
            registry=PackRegistry(ROOT / "packs"),
            now=datetime(2026, 10, 14, 6, tzinfo=UTC),
        )
    )
    assert report["mode"] == "fake" and report["n"] == 20
    assert report["outcomes"] == {"planned": 16, "clarification": 4}
    assert report["recipientOrderChecks"] == {"correct": 16, "n": 16}
    assert all(
        item["noInventedNumericDeadline"] and item["draftPreview"] and item["hasUnverifiedNotice"]
        for item in report["results"]
        if item["outcome"] == "planned"
    )
    assert report["latency"]["n"] == 20 and report["latency"]["p95Ms"] >= 0
    assert all(metric["correct"] == 20 for metric in report["metrics"])


def test_workflow_failures_stay_in_denominator(tmp_path):
    report = asyncio.run(
        evaluate(
            FIXTURES[:1],
            registry=PackRegistry(tmp_path / "missing"),
            now=datetime(2026, 10, 14, 6, tzinfo=UTC),
        )
    )
    assert report["n"] == 1 and report["outcomes"] == {"failed": 1}
    assert all(metric["correct"] == 0 and metric["n"] == 1 for metric in report["metrics"])
    assert report["results"][0]["errorType"]


def test_live_cap_no_gold_forwarding_and_no_retry():
    from agents.classification.eval import CappedClient
    from agents.intake.clients import ModelFailure

    class CountingClient:
        model_id = "fixture-fake"
        mode = "fake"

        def __init__(self):
            self.calls = 0

        async def generate(self, **kwargs):
            self.calls += 1
            assert (
                not {"modelOutput", "expectedAuthorization", "expectedTypology"}
                & kwargs["data"].keys()
            )
            return "{}"

    async def scenario():
        client = CountingClient()
        capped = CappedClient(client)
        for _ in range(20):
            await capped.generate(data={"facts": {}}, prompt="synthetic", schema=object)
        import pytest

        with pytest.raises(ModelFailure, match="budget_exceeded"):
            await capped.generate(data={"facts": {}}, prompt="synthetic", schema=object)
        assert client.calls == 20
        with pytest.raises(ValueError, match="gold_input_leak"):
            await CappedClient(client).generate(
                data={"modelOutput": {}}, prompt="synthetic", schema=object
            )
        assert client.calls == 20

    asyncio.run(scenario())


def test_fixture_gold_ambiguity_does_not_depend_on_mock_confidence():
    unclear = [case for case in FIXTURES if case["expectedAuthorization"] == "unclear"]
    assert len(unclear) == 4
    assert all(case["facts"]["payment"]["authorizedByVictim"] is None for case in unclear)
    assert all("helpline" not in case["expectedRecipients"] for case in FIXTURES)
