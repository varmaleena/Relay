"""Construct immutable agent inputs only after verifying private snapshot lineage."""

import hashlib
from typing import Any

from agents.packbuilder import ImmutableSource, PackBuilderAgent
from packages.common.identifiers import canonical_hash
from packages.intake.service import IntakeError
from packages.schemas import Source

PASSES = ("recipients", "deadlines", "remedies", "sequencing", "support")


def load_sources(service, actor, source_ids):
    loaded, proofs = [], []
    for source_id in source_ids:
        source = service._source(service.repository, actor, source_id)
        if source.get("state") != "ready":
            raise IntakeError(409, "source_not_ready")
        url = source.get("finalUrl") or source.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise IntakeError(422, "source_metadata_required")
        content = service.storage.read(source["storagePath"])
        if hashlib.sha256(content).hexdigest() != source.get("sha256"):
            raise IntakeError(422, "source_proof_invalid")
        passages = [
            service.repository.get(f"sources/{source_id}/passages/{pid}")
            for pid in source["passageIds"]
        ]
        if (
            not passages
            or any(item is None for item in passages)
            or canonical_hash(passages) != source.get("extractionHash")
        ):
            raise IntakeError(422, "source_proof_invalid")
        canonical = Source(
            id=source_id,
            title=source["title"],
            publisher=source["publisher"],
            url=url,
            retrieved_at=source["retrievedAt"],
            sha256=source["sha256"],
        )
        loaded.append(
            ImmutableSource(
                source=canonical,
                extraction_hash=source["extractionHash"],
                passages=tuple(
                    item | {"textSha256": hashlib.sha256(item["text"].encode()).hexdigest()}
                    for item in passages
                ),
            )
        )
        proofs.append(
            {
                "sourceId": source_id,
                "sha256": source["sha256"],
                "extractionHash": source["extractionHash"],
                "storagePath": source["storagePath"],
                "metadata": canonical.model_dump(mode="json", by_alias=True),
            }
        )
    return loaded, proofs


class PackBuilderAdapter:
    def __init__(self, client: Any):
        self.client = client

    async def build(self, *, progress, **kwargs):
        client, current = self.client, [None]

        class Observed:
            model_id = getattr(client, "model_id", "unknown")

            async def generate(self, *, prompt, data, schema):
                name = data["passName"]
                if name != current[0]:
                    if current[0] is not None:
                        progress(current[0], "completed")
                    current[0] = name
                    progress(name, "running")
                return await client.generate(prompt=prompt, data=data, schema=schema)

        result = await PackBuilderAgent(Observed()).build(**kwargs)
        progress(PASSES[-1], "completed")
        return result
