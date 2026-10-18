"""Trusted same-transaction ingestion of approved, confirmed scammer identifiers."""

from datetime import datetime

from packages.schemas import EvidenceExtraction

from .core import WEIGHTS


def index_approved_delivery(service, tx, case, packet):
    # Evidence is not implicitly shared. Restrict inputs to identifier values
    # actually present in the explicitly approved recipient report.
    approved_values = {
        field.get("value") for field in packet["content"]["fields"] if field.get("value")
    }
    entities = []
    for evidence_id in case.get("evidenceIds", []):
        evidence = tx.get(f"cases/{case['caseId']}/evidence/{evidence_id}")
        if not evidence or evidence.get("status") != "ready" or not evidence.get("extraction"):
            continue
        for entity in EvidenceExtraction.model_validate(evidence["extraction"]).entities:
            if (
                entity.type in WEIGHTS
                and entity.role == "scammer"
                and entity.status in {"confirmed", "edited"}
                and entity.normalized_value in approved_values
            ):
                entities.append(
                    {
                        "type": entity.type,
                        "value": entity.normalized_value,
                        "role": entity.role,
                        "status": entity.status,
                    }
                )
    orgs = {reference["orgId"] for reference in case.get("receiverProjectionRefs", [])}
    if orgs:
        service.replace_case(
            case["caseRef"],
            orgs,
            entities,
            datetime.fromisoformat(case["createdAt"].replace("Z", "+00:00")),
            (case["facts"].get("country") or {}).get("value") or "IN",
            case_id=case["caseId"],
            tx=tx,
        )
