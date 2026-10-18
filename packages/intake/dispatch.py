"""Post-commit wakeups; durable Firestore jobs remain the source of truth."""

import json
import logging
from typing import Any


class PubSubJobPublisher:
    def __init__(self, client: Any, topic: str) -> None:
        self.client, self.topic = client, topic

    def __call__(self, job: dict[str, Any]) -> None:
        job_id = job["jobId"]
        references = {name: job[name] for name in ("caseId", "resourceId") if job.get(name)}
        self.client.publish(
            self.topic,
            json.dumps({"jobId": job_id}, separators=(",", ":")).encode(),
            type=job["type"],
            schemaVersion="1",
            **references,
            traceId=job_id,
            idempotencyKey=job_id,
        ).result(timeout=10)


def notify_jobs(writes: dict[str, Any], publisher: Any) -> None:
    """Publishing cannot roll back committed work; a private sweep repairs gaps."""
    if publisher is None:
        return
    for path, document in writes.items():
        if (
            path.startswith("jobs/")
            and path.count("/") == 1
            and document
            and document.get("state") == "queued"
        ):
            try:
                publisher(document)
            except Exception:
                # Do not log job payloads, signed URLs, or exception messages.
                logging.getLogger("relay").warning("job.dispatch_deferred")
