"""Atomic Firestore unit of work; memory implementation is test-only."""

from collections.abc import Callable
from copy import deepcopy
from threading import RLock
from typing import Any, Protocol, TypeVar

T = TypeVar("T")
Document = dict[str, Any]


class Transaction(Protocol):
    def get(self, path: str) -> Document | None: ...
    def set(self, path: str, value: Document) -> None: ...
    def delete(self, path: str) -> None: ...


class Repository(Protocol):
    def get(self, path: str) -> Document | None: ...
    def atomic(self, callback: Callable[[Transaction], T]) -> T: ...


class FirestoreRepository:
    def __init__(self, client: Any, job_publisher: Any = None) -> None:
        self.client = client
        self.job_publisher = job_publisher

    def get(self, path: str) -> Document | None:
        snapshot = self.client.document(path).get()
        return snapshot.to_dict() if snapshot.exists else None

    def atomic(self, callback: Callable[[Transaction], T]) -> T:
        from google.api_core.exceptions import Aborted
        from google.api_core.retry import Retry
        from google.cloud import firestore

        client = self.client
        committed_writes: dict[str, Document | None] = {}

        class Work:
            def __init__(self, transaction: Any) -> None:
                self.transaction = transaction
                self.writes: dict[str, Document | None] = {}

            def get(self, path: str) -> Document | None:
                if path in self.writes:
                    return deepcopy(self.writes[path])
                snap = client.document(path).get(transaction=self.transaction)
                return snap.to_dict() if snap.exists else None

            def set(self, path: str, value: Document) -> None:
                self.writes[path] = deepcopy(value)

            def delete(self, path: str) -> None:
                self.writes[path] = None

        @firestore.transactional
        def execute(transaction: Any) -> T:
            work = Work(transaction)
            result = callback(work)
            # All reads finish before any real Firestore write.
            for path, value in work.writes.items():
                reference = client.document(path)
                if value is None:
                    transaction.delete(reference)
                else:
                    transaction.set(reference, value)
            committed_writes.clear()
            committed_writes.update(work.writes)
            return result

        rounds = 0

        def run_fresh() -> T:
            nonlocal rounds
            rounds += 1
            return execute(client.transaction())

        def retry_contention(error: Exception) -> bool:
            # The SDK retries commit contention five times, then wraps Aborted
            # in ValueError. Read/callback Aborted bypasses that SDK loop.
            # Never replay validation/domain failures or other RPC failures.
            contention = isinstance(error, Aborted) or (
                type(error) is ValueError and isinstance(error.__cause__, Aborted)
            )
            return contention and rounds < 3

        # Standard Google full-jitter backoff. The 10-second retry scheduling
        # window does not cancel an RPC already in flight. Each round gets a
        # fresh SDK transaction; callbacks must keep all side effects in Work.
        result = Retry(
            predicate=retry_contention, initial=0.05, maximum=0.5, multiplier=2, timeout=10
        )(run_fresh)()
        from .dispatch import notify_jobs

        notify_jobs(committed_writes, self.job_publisher)
        return result


class MemoryRepository:
    """Explicit test fixture, never selected by runtime configuration."""

    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self.lock = RLock()

    def get(self, path: str) -> Document | None:
        with self.lock:
            return deepcopy(self.documents.get(path))

    def atomic(self, callback: Callable[[Transaction], T]) -> T:
        with self.lock:
            original = deepcopy(self.documents)
            try:
                return callback(self)
            except Exception:
                self.documents = original
                raise

    def set(self, path: str, value: Document) -> None:
        self.documents[path] = deepcopy(value)

    def delete(self, path: str) -> None:
        self.documents.pop(path, None)
