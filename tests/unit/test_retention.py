from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from packages.intake.retention import cleanup_expired_cases


def test_retention_is_bounded_and_reuses_domain_cascade():
    query = Mock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = [
        SimpleNamespace(id="case_expired"),
        SimpleNamespace(id="case_retry"),
    ]
    service = SimpleNamespace(
        repository=SimpleNamespace(client=SimpleNamespace(collection=Mock(return_value=query))),
        clock=lambda: datetime(2026, 10, 17, tzinfo=UTC),
        delete_case=Mock(side_effect=[None, RuntimeError("do not log payload")]),
    )
    assert cleanup_expired_cases(service, 2) == {"deleted": 1, "failed": 1}
    query.limit.assert_called_once_with(2)
    actor, case_id = service.delete_case.call_args_list[0].args
    assert actor.role == "admin" and case_id == "case_expired"
    condition = query.where.call_args.kwargs["filter"]
    assert condition.field_path == "ttlAt" and condition.op_string == "<="
    assert condition.value == "2026-10-17T00:00:00Z"


@pytest.mark.parametrize("limit", [0, -1, 11])
def test_cleanup_cannot_be_unbounded(limit):
    with pytest.raises(ValueError):
        cleanup_expired_cases(None, limit)
