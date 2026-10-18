"""Trusted victim-side hook; never load victim documents from receiver handlers."""

from typing import Any

from packages.intake.repository import Transaction
from packages.receiver.service import identifier


def invalidate_link_projections(
    tx: Transaction, case_id: str, known_refs: list[dict[str, Any]]
) -> int:
    """Atomically mark approved snapshots stale when their input proof changes.

    Invoke inside the same trusted facts/transcript/extraction/plan mutation.
    The case supplies known delivery references; request JSON cannot supply them.
    Historical content is retained for receiver audit; future delivery replaces
    its own projection after fresh approval. No external I/O occurs in callback.
    """
    identifier(case_id)
    if len(known_refs) > 40:
        raise ValueError("Bounded receiver projection references required")
    changed = 0
    for reference in known_refs:
        org = identifier(reference["orgId"])
        packet_id = identifier(reference["packetId"])
        path = f"receiverViews/{org}/cases/{case_id}/packets/{packet_id}"
        projected = tx.get(path)
        if projected and not projected.get("packet", {}).get("stale"):
            projected["packet"]["stale"] = True
            projected["linkingInvalidated"] = True
            tx.set(path, projected)
            changed += 1
    return changed
