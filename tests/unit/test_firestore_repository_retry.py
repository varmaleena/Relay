"""Bounded fresh transaction retries, with no domain-error suppression."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from google.api_core.exceptions import Aborted
from pydantic import BaseModel, ValidationError

from packages.intake.repository import FirestoreRepository


class FakeTransaction:
    def __init__(self, client):
        self.client = client
        self._read_only = False
        self._max_attempts = 5
        self._id = None
        self.writes = {}

    def _clean_up(self):
        self._id = None
        self.writes = {}

    def _begin(self, retry_id=None):
        self._id = b"synthetic-transaction"

    def _commit(self):
        self.client.commits += 1
        if self.client.abort_first_round and len(self.client.transactions) == 1:
            raise Aborted("synthetic commit contention")
        self.client.documents.update(self.writes)

    def _rollback(self):
        self.client.rollbacks += 1
        self.writes = {}

    def set(self, reference, value):
        self.writes[reference.path] = value


class FakeClient:
    def __init__(self, *, abort_first_round=False):
        self.transactions, self.documents = [], {}
        self.commits = self.rollbacks = 0
        self.abort_first_round = abort_first_round

    def transaction(self):
        transaction = FakeTransaction(self)
        self.transactions.append(transaction)
        return transaction

    def document(self, path):
        return SimpleNamespace(path=path)


def test_callback_read_abort_restarts_with_fresh_transaction_and_no_partial_writes():
    client = FakeClient()
    calls = []

    def callback(tx):
        calls.append(tx)
        tx.set("tests/synthetic", {"attempt": len(calls)})
        if len(calls) == 1:
            raise Aborted("synthetic read contention")
        return "committed"

    with patch("google.api_core.retry.retry_unary.time.sleep") as sleep:
        assert FirestoreRepository(client).atomic(callback) == "committed"
    assert len(client.transactions) == 2 and client.transactions[0] is not client.transactions[1]
    assert client.documents == {"tests/synthetic": {"attempt": 2}}
    assert client.rollbacks == 1 and sleep.call_count == 1
    assert 0 <= sleep.call_args.args[0] <= 0.05


def test_sdk_exhausted_commit_aborted_gets_fresh_round_without_duplicate_commit():
    client = FakeClient(abort_first_round=True)

    def callback(tx):
        tx.set("tests/synthetic", {"value": "synthetic"})
        return "done"

    with patch("google.api_core.retry.retry_unary.time.sleep"):
        result = FirestoreRepository(client).atomic(callback)
    assert result == "done" and len(client.transactions) == 2
    assert client.commits == 6 and client.rollbacks == 1
    assert client.documents == {"tests/synthetic": {"value": "synthetic"}}


def test_persistent_abort_stops_at_three_fresh_rounds_and_propagates_error():
    client = FakeClient()

    def aborted(_):
        raise Aborted("synthetic permanent contention")

    with patch("google.api_core.retry.retry_unary.time.sleep") as sleep:
        with pytest.raises(Aborted):
            FirestoreRepository(client).atomic(aborted)
    assert len(client.transactions) == 3 and sleep.call_count == 2
    assert not client.documents


@pytest.mark.parametrize("error_kind", ["value", "validation"])
def test_domain_validation_failures_are_never_retried(error_kind):
    class StrictInput(BaseModel):
        count: int

    error = ValueError("synthetic domain validation")
    if error_kind == "validation":
        try:
            StrictInput.model_validate({"count": "invalid"})
        except ValidationError as validation:
            error = validation
    client = FakeClient()

    def invalid(_):
        raise error

    with patch("google.api_core.retry.retry_unary.time.sleep") as sleep:
        with pytest.raises(type(error)) as caught:
            FirestoreRepository(client).atomic(invalid)
    assert caught.value is error and len(client.transactions) == 1
    sleep.assert_not_called()
