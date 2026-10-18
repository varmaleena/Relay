"""Packet-only bounded transient retry; SDK remains one attempt per HTTP call."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel

from agents.intake.clients import ModelClient, ModelFailure


class RetryPacketClient:
    TRANSIENT = frozenset(
        {"http_429", "http_503", "http_504", "connect_timeout", "read_timeout", "timeout"}
    )

    def __init__(
        self,
        client: ModelClient,
        *,
        timeout: float = 35,
        on_retry: Callable[[dict[str, Any]], None] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = lambda: random.uniform(0, 2),
    ) -> None:
        if not 0 < timeout <= 35:
            raise ValueError("packet logical deadline must be at most35seconds")
        self.client, self.model_id = client, client.model_id
        self.timeout, self.on_retry, self.sleep = timeout, on_retry, sleep
        self.jitter = jitter
        self.retry_events: list[dict[str, Any]] = []

    @property
    def mode(self) -> Literal["live", "fake", "replay"]:
        return self.client.mode

    async def generate(
        self,
        *,
        prompt: str,
        data: dict[str, Any],
        schema: type[BaseModel],
        media: tuple[str, bytes] | None = None,
    ) -> str:
        if schema.__name__ not in {"WriterOutput", "EntailmentOutput"}:
            raise ValueError("packet_retry_schema_not_allowed")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout
        async with asyncio.timeout(self.timeout):
            for attempt in range(2):
                try:
                    return await self.client.generate(
                        prompt=prompt, data=data, schema=schema, media=media
                    )
                except ModelFailure as error:
                    backoff = 8 + max(0, min(2, self.jitter())) if error.reason == "http_429" else 2
                    if (
                        attempt != 0
                        or error.reason not in self.TRANSIENT
                        or deadline - loop.time() < backoff + 15
                    ):
                        raise
                    event = {
                        "event": "retry_backoff",
                        "schemaName": schema.__name__,
                        "reason": error.reason,
                        "statusCode": error.status_code,
                        "retryNumber": 1,
                        "backoffSeconds": backoff,
                    }
                    self.retry_events.append(event)
                    if self.on_retry is not None:
                        self.on_retry(event)
                    await self.sleep(backoff)
        raise AssertionError("unreachable")
