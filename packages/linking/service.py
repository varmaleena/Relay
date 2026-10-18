"""Bounded private repository materialization; no receiver reads of victim cases."""

from datetime import datetime
from typing import Any

from packages.intake.repository import Repository, Transaction

from .core import Hasher, Sighting, compute

INDEX = "linkingPrivate/index"


class LinkingService:
    def __init__(self, repository: Repository, hasher: Hasher) -> None:
        self.repository = repository
        self.hasher = hasher

    def replace_case(
        self,
        case_ref: str,
        org_ids: set[str],
        entities: list[dict[str, Any]],
        first_seen: datetime,
        country: str = "IN",
        *,
        case_id: str | None = None,
        tx: Transaction | None = None,
    ) -> None:
        # Trusted ingestion hook only: org scopes come from approved delivery, never request input.
        if not org_ids or len(entities) > 50:
            raise ValueError("Bounded approved projection required")
        sightings = []
        for entity in entities:
            item = self.hasher.sighting(
                case_ref=case_ref,
                entity_type=entity["type"],
                value=entity["value"],
                role=entity["role"],
                status=entity["status"],
                first_seen=first_seen,
                country=country,
                case_sensitive_wallet=entity.get("caseSensitiveWallet", True),
            )
            if item is not None:
                sightings.append(item.model_dump(mode="json"))

        def save(tx: Transaction) -> None:
            record = tx.get(INDEX) or {"cases": {}}
            cases = record["cases"]
            cases[case_ref] = {
                "orgIds": sorted(org_ids),
                "sightings": sightings,
                "caseId": case_id or case_ref,
            }
            if len(cases) > 40 or sum(len(v["sightings"]) for v in cases.values()) > 500:
                raise ValueError("Private development index capacity reached")
            self._materialize(record)
            tx.set(INDEX, record)

        if tx is not None:
            save(tx)
        else:
            self.repository.atomic(save)

    def _materialize(self, record: dict[str, Any]) -> None:
        sightings = [
            Sighting.model_validate(s)
            for case in record["cases"].values()
            for s in case["sightings"]
        ]
        links, clusters = compute(sightings, self.hasher.denylist)
        record["links"] = [x.model_dump(mode="json") for x in links]
        record["clusters"] = [x.model_dump(mode="json") for x in clusters]

    def cleanup_case(self, tx: Transaction, case_ref: str) -> None:
        record = tx.get(INDEX)
        if record and case_ref in record["cases"]:
            del record["cases"][case_ref]
            for field in ("reviews", "reviewRequests"):
                record[field] = {
                    key: value
                    for key, value in record.get(field, {}).items()
                    if case_ref not in value.get("caseRefs", [])
                }
            self._materialize(record)
            tx.set(INDEX, record)

    def links_for(self, case_ref: str, org_id: str) -> list[dict[str, Any]]:
        record = self.repository.get(INDEX) or {"cases": {}, "links": []}
        cases = record["cases"]
        if org_id not in cases.get(case_ref, {}).get("orgIds", []):
            raise PermissionError("No approved receiver projection")
        # Both records must already be addressed to this organization.
        return [
            link
            for link in record.get("links", [])
            if case_ref in link["case_refs"]
            and all(org_id in cases[ref]["orgIds"] for ref in link["case_refs"])
        ]
