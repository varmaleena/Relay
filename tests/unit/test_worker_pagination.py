import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from services.worker.main import JobPager, process_jobs


class Query:
    def __init__(self, records, reads, cursor=None):
        self.records, self.reads, self.cursor = records, reads, cursor

    def collection(self, name):
        assert name == "jobs"
        return self

    def where(self, *, filter):
        assert filter.field_path == "state"
        return self

    def order_by(self, field):
        assert field == "__name__"
        return self

    def limit(self, count):
        assert count == 25
        return self

    def start_after(self, snapshot):
        return Query(self.records, self.reads, snapshot.id)

    def stream(self):
        page = [record for record in self.records if not self.cursor or record.id > self.cursor][
            :25
        ]
        self.reads.append(len(page))
        return iter(page)


def test_deferred_first_page_does_not_starve_runnable_job_and_sweep_resets():
    now = datetime.now(UTC)
    later = (now + timedelta(minutes=5)).isoformat()
    records = []
    for index in range(31):
        data = {"type": "process_case", "state": "queued"}
        if index < 30:
            data["retryAfter" if index % 2 else "leaseUntil"] = later
        records.append(SimpleNamespace(id=f"job-{index:03}", to_dict=lambda data=data: data))
    calls = []

    async def process(job_id):
        calls.append(job_id)

    service = SimpleNamespace(planning=SimpleNamespace(process_case=process))
    query = Query(records, [])
    pager = JobPager()
    assert not asyncio.run(process_jobs(service, pager.fetch(query), now))
    assert asyncio.run(process_jobs(service, pager.fetch(query), now))
    assert calls == ["job-030"] and query.reads == [25, 6]
    assert pager.cursor is None
    # A job inserted behind the previous cursor becomes visible next sweep.
    records[0].to_dict = lambda: {"type": "process_case", "state": "queued"}
    asyncio.run(process_jobs(service, pager.fetch(query), now))
    assert calls[-1] == "job-000"


def test_exact_page_uses_empty_page_to_reset_and_failed_fetch_preserves_cursor():
    records = [SimpleNamespace(id=f"job-{i:03}") for i in range(25)]
    query = Query(records, [])
    pager = JobPager()
    pager.fetch(query)
    cursor = pager.cursor

    class Broken:
        def collection(self, _):
            raise OSError("synthetic read failure")

    with pytest.raises(OSError):
        pager.fetch(Broken())
    assert pager.cursor is cursor
    assert pager.fetch(query) == [] and pager.cursor is None
