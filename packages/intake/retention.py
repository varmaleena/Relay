"""Bounded expiry cleanup through the same cascade used for explicit deletion."""

from typing import Any

from google.cloud.firestore_v1.base_query import FieldFilter

from packages.safety import Actor

from .service import IntakeError, stamp


def cleanup_expired_cases(service: Any, limit: int = 5) -> dict[str, int]:
    if not 1 <= limit <= 10:
        raise ValueError("cleanup limit must be between one and ten")
    query = (
        service.repository.client.collection("cases")
        .where(filter=FieldFilter("ttlAt", "<=", stamp(service.clock())))
        .order_by("ttlAt")
        .limit(limit)
    )
    deleted, failed = 0, 0
    for snapshot in query.stream():
        try:
            # delete_case marks deleting before touching objects, then atomically
            # removes child records. A failed object deletion remains retryable.
            service.delete_case(Actor("retention-worker", "admin"), snapshot.id)
            deleted += 1
        except IntakeError as exc:
            if exc.status != 404:
                failed += 1
        except Exception:
            failed += 1
    return {"deleted": deleted, "failed": failed}
