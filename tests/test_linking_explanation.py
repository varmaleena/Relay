import asyncio

import pytest

from agents.linking.core import ExplanationText, explain
from packages.linking.core import Link


def test_explanation_receives_metadata_only():
    captured = []

    async def generate(value):
        captured.append(value)
        return ExplanationText(text="There is a possible link between these reports.")

    link = Link(
        link_id="l",
        case_refs=("a", "b"),
        shared_entity_types=["upi_id"],
        strength=0.9,
        confidence_band="likely",
        hours_apart=1,
    )
    result = asyncio.run(explain(link, generate))
    assert set(captured[0]) == {
        "caseRefs",
        "entityTypes",
        "hoursApart",
        "confidenceBand",
        "sharedTypeCount",
    }
    assert len(result["evidencePointers"]) == 2
    assert "person must confirm" in result["text"]


def test_explanation_rejects_identifier_output():
    async def generate(value):
        return ExplanationText(text="A possible link with test@example.invalid.")

    link = Link(
        link_id="l",
        case_refs=("a", "b"),
        shared_entity_types=["email"],
        strength=0.6,
        confidence_band="possible",
        hours_apart=1,
    )
    with pytest.raises(ValueError):
        asyncio.run(explain(link, generate))
