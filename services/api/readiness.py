"""Serving dependency readiness, not live model quality or a production SLO.

Cloud checks read one harmless Firestore health document and check an existing
health object in each storage bucket. These are normal dependency read RPCs;
there is no inference, publish, write, bucket metadata, or model/list API call.
Queue/model statuses mean configured, never operationally verified. Deployers
must create the __health/readiness object in evidence and export buckets.
"""

import asyncio
import os
import time
from collections.abc import Callable
from typing import Any

from google.api_core.exceptions import DeadlineExceeded

from packages.common.settings import Settings

HEALTH_RESOURCE = "__health/readiness"


class ServingReadiness:
    def __init__(
        self,
        config: Settings,
        service: Any,
        *,
        rpc_timeout: float = 2,
        overall_timeout: float = 3,
        cache_seconds: float = 5,
    ):
        self.config, self.service = config, service
        self.rpc_timeout, self.overall_timeout = rpc_timeout, overall_timeout
        self.cache_seconds = cache_seconds
        self._lock = asyncio.Lock()
        self._cached: dict[str, Any] | None = None
        self._expires = 0.0

    def _cloud(self) -> bool:
        config = self.config
        return bool(
            config.environment in {"dev", "staging", "prod"}
            and config.intake_enabled
            and config.auth_mode == "firebase"
            and config.intake_storage_mode == "gcs"
            and self.service is not None
            and config.gcp_project_id
            and not config.gcp_project_id.startswith("demo-")
            and not any(
                os.environ.get(name)
                for name in (
                    "FIRESTORE_EMULATOR_HOST",
                    "FIREBASE_AUTH_EMULATOR_HOST",
                    "PUBSUB_EMULATOR_HOST",
                    "STORAGE_EMULATOR_HOST",
                )
            )
        )

    @staticmethod
    def _run_probe(call: Callable[[], bool]) -> str:
        try:
            return "verified" if call() else "sentinel_missing"
        except (TimeoutError, DeadlineExceeded):
            return "timeout"
        except Exception:
            # Never expose resource IDs, exception text, or document contents.
            return "unavailable"

    async def check(self) -> dict[str, Any]:
        if not self._cloud():
            # Preserve the foundation's default/local behavior exactly.
            return {
                "status": "not_ready",
                "deps": {
                    "firestore": "not_verified",
                    "pubsub": "not_verified",
                    "genai": "not_verified",
                },
            }
        async with self._lock:
            if self._cached is not None and time.monotonic() < self._expires:
                return self._cached
            result = await self._check_cloud()
            self._cached, self._expires = result, time.monotonic() + self.cache_seconds
            return result

    async def _check_cloud(self) -> dict[str, Any]:
        config, service = self.config, self.service
        deps = {
            name: "not_configured"
            for name in ("firestore", "evidence_storage", "export_storage", "pubsub", "genai")
        }
        repository = getattr(service, "repository", None)
        database = getattr(repository, "client", None)
        publisher = getattr(repository, "job_publisher", None)
        if (
            config.pubsub_topic_jobs
            and callable(publisher)
            and getattr(publisher, "topic", None) == config.pubsub_topic_jobs
            and getattr(publisher, "client", None) is not None
        ):
            deps["pubsub"] = "configured"
        if (
            config.genai_mode == "live"
            and config.model_reasoning
            and config.genai_location
            and getattr(service, "intake_agent", None) is not None
            and getattr(service, "evidence_agent", None) is not None
        ):
            deps["genai"] = "configured"
        calls: dict[str, Callable[[], bool]] = {}
        if database is not None and getattr(database, "project", None) == config.gcp_project_id:

            def firestore_probe() -> bool:
                database.document(HEALTH_RESOURCE).get(timeout=self.rpc_timeout, retry=None)
                return True

            calls["firestore"] = firestore_probe
        for key, store, expected_bucket in (
            ("evidence_storage", getattr(service, "storage", None), config.bucket_evidence),
            ("export_storage", getattr(service, "export_storage", None), config.bucket_exports),
        ):
            bucket = getattr(store, "bucket", None)
            if (
                expected_bucket
                and bucket is not None
                and getattr(bucket, "name", None) == expected_bucket
            ):

                def storage_probe(bucket: Any = bucket) -> bool:
                    return bool(
                        bucket.blob(HEALTH_RESOURCE).exists(timeout=self.rpc_timeout, retry=None)
                    )

                calls[key] = storage_probe
        tasks = {
            asyncio.create_task(asyncio.to_thread(self._run_probe, call)): key
            for key, call in calls.items()
        }
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=self.overall_timeout)
            for task in done:
                deps[tasks[task]] = task.result()
            for task in pending:
                deps[tasks[task]] = "timeout"
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        ready = all(
            deps[name] == "verified" for name in ("firestore", "evidence_storage", "export_storage")
        ) and all(deps[name] == "configured" for name in ("pubsub", "genai"))
        return {
            "status": "ready" if ready else "not_ready",
            "scope": "serving_dependencies",
            "deps": deps,
            "notProbed": ["model_inference", "queue_delivery", "live_quality"],
        }
