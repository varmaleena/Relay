"""Single-consumer evidence worker. Claims are transactional and survive API restarts."""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from google.cloud.firestore_v1.base_query import FieldFilter

from packages.common.logging import configure_logging
from packages.common.settings import Settings
from services.api.runtime import create_intake_runtime


def fetch_jobs(query: Any) -> list[Any]:
    return list(query.stream())


class JobPager:
    """Read one bounded page per poll, including when every item is deferred."""

    def __init__(self) -> None:
        self.cursor: Any = None

    def fetch(self, client: Any) -> list[Any]:
        query = (
            client.collection("jobs")
            .where(filter=FieldFilter("state", "in", ["queued", "running"]))
            .order_by("__name__")
            .limit(25)
        )
        if self.cursor is not None:
            query = query.start_after(self.cursor)
        # Advance only after a successful fetch. A transient read failure must
        # not skip a page; a short or empty page completes this sweep.
        snapshots = fetch_jobs(query)
        self.cursor = snapshots[-1] if len(snapshots) == 25 else None
        return snapshots


async def process_jobs(service: Any, snapshots: list[Any], now: datetime) -> bool:
    processed = False
    for snapshot in snapshots:
        try:
            job = snapshot.to_dict()
            if not job or job.get("type") not in {
                "process_evidence",
                "process_case",
                "rebuild_packets",
                "verify_packet",
                "send_packet",
                "handoff_receiver",
                "pack_ingest",
                "pack_build",
            }:
                continue
            deferred = False
            for field in ("leaseUntil", "retryAfter"):
                value = job.get(field)
                if value and datetime.fromisoformat(value.replace("Z", "+00:00")) > now:
                    deferred = True
            if deferred:
                continue
            if job["type"] in {"rebuild_packets", "verify_packet", "send_packet"}:
                if service.packets is None:
                    continue
                if job["type"] == "send_packet":
                    await service.packets.process_delivery(snapshot.id)
                else:
                    await service.packets.process(snapshot.id)
            elif job["type"] == "handoff_receiver":
                if service.receiver_handoff is None:
                    continue
                await service.receiver_handoff.process(snapshot.id)
            elif job["type"] == "pack_ingest":
                if service.sources is None:
                    continue
                await service.sources.process(snapshot.id)
            elif job["type"] == "pack_build":
                if service.packstudio is None:
                    continue
                await service.packstudio.process(snapshot.id)
            elif job["type"] == "process_case":
                if service.planning is None:
                    continue
                await service.planning.process_case(snapshot.id)
            else:
                await service.process_evidence(snapshot.id)
            processed = True
        except Exception:
            # One malformed record or failed job must not stop other durable work.
            logging.getLogger("relay").error("request.failed", extra={"service": "worker"})
    return processed


async def run() -> None:
    config = Settings()
    configure_logging()
    service, model = create_intake_runtime(config)
    client = service.repository.client
    pager = JobPager()
    deadline_cursor = None
    deadline_checked = 0.0
    try:
        while True:
            try:
                snapshots = await asyncio.to_thread(pager.fetch, client)
            except Exception:
                logging.getLogger("relay").error("request.failed", extra={"service": "worker"})
                await asyncio.sleep(1.0)
                continue
            processed = await process_jobs(service, snapshots, datetime.now(UTC))
            if service.packets is not None and time.monotonic() - deadline_checked >= 60:
                from packages.packets.deadlines import check_case_deadlines

                query = client.collection("cases").order_by("__name__").limit(25)
                if deadline_cursor is not None:
                    query = query.start_after(deadline_cursor)
                try:
                    page = await asyncio.to_thread(fetch_jobs, query)
                except Exception:
                    logging.getLogger("relay").error("request.failed", extra={"service": "worker"})
                    deadline_checked = time.monotonic()
                    continue
                deadline_cursor = page[-1] if len(page) == 25 else None
                for case in page:
                    try:
                        await asyncio.to_thread(check_case_deadlines, service.packets, case.id)
                    except Exception:
                        logging.getLogger("relay").error(
                            "request.failed", extra={"service": "worker"}
                        )
                deadline_checked = time.monotonic()
            await asyncio.sleep(0.2 if processed else 1.0)
    finally:
        await model.close()
        client.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
