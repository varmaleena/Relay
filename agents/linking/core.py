"""Only sanitized link metadata reaches an injected explanatory model."""

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from packages.linking.core import Link


class ExplanationText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=20, max_length=1200)


async def explain(
    link: Link, generate: Callable[[dict[str, Any]], Awaitable[ExplanationText]]
) -> dict[str, Any]:
    pointers = [
        {"caseRef": ref, "entityType": kind}
        for ref in link.case_refs
        for kind in link.shared_entity_types
    ]
    output = await generate(
        {
            "caseRefs": list(link.case_refs),
            "entityTypes": link.shared_entity_types,
            "hoursApart": link.hours_apart,
            "confidenceBand": link.confidence_band,
            "sharedTypeCount": len(link.shared_entity_types),
        }
    )
    text = output.text
    # Bound model text to metadata-derived vocabulary: no identifier output is accepted.
    import re

    if re.search(r"@|https?://|\b\d{7,}\b", text) or "possible link" not in text.lower():
        raise ValueError("Unsafe explanation")
    return {
        "text": text + " A person must confirm this possible link.",
        "confidenceBand": link.confidence_band,
        "evidencePointers": pointers,
        "heuristic": True,
    }
