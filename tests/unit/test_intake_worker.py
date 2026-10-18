"""Durable worker scheduling survives leases, failures and corrupt records."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

from services.worker.main import process_jobs


def snapshot(identifier, **fields):
    item = Mock()
    item.id = identifier
    item.to_dict.return_value = {"type": "process_evidence", **fields}
    return item


def test_worker_defers_active_leases_and_backoff_but_resumes_expired_work():
    now = datetime.now(UTC)
    future = (now + timedelta(minutes=1)).isoformat()
    past = (now - timedelta(minutes=1)).isoformat()
    service = Mock(process_evidence=AsyncMock())
    jobs = [
        snapshot("leased", leaseUntil=future),
        snapshot("backoff", retryAfter=future),
        snapshot("expired", leaseUntil=past, retryAfter=past),
        snapshot("future-phase", type="classify_plan"),
    ]
    assert asyncio.run(process_jobs(service, jobs, now))
    service.process_evidence.assert_awaited_once_with("expired")


def test_worker_continues_after_corrupt_and_failed_jobs_without_logging_contents(caplog):
    service = Mock(process_evidence=AsyncMock(side_effect=[ValueError("SECRET CONTENT"), None]))
    jobs = [
        snapshot("corrupt", leaseUntil="SECRET CONTENT"),
        snapshot("failed"),
        snapshot("next"),
    ]
    assert asyncio.run(process_jobs(service, jobs, datetime.now(UTC)))
    assert [call.args[0] for call in service.process_evidence.await_args_list] == ["failed", "next"]
    assert "SECRET CONTENT" not in caplog.text


def test_worker_all_deferred_has_no_model_call():
    service = Mock(process_evidence=AsyncMock())
    now = datetime.now(UTC)
    assert not asyncio.run(
        process_jobs(
            service, [snapshot("backoff", retryAfter=(now + timedelta(hours=1)).isoformat())], now
        )
    )
    service.process_evidence.assert_not_awaited()
