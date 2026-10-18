"""Private OIDC client using the installed A2A JSON-RPC SDK transport."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx
from a2a.client.transports.jsonrpc import JsonRpcTransport
from a2a.types import (
    AgentCard,
    AgentInterface,
    GetTaskRequest,
    Message,
    Role,
    SendMessageRequest,
    TaskState,
)
from google.protobuf.json_format import MessageToDict

from services.a2a_receiver.store import HandoffReference, data_part, task_identifier


class HandoffUnavailable(RuntimeError):
    pass


class A2AHandoffClient:
    def __init__(
        self,
        endpoint_url: str,
        *,
        scope: str,
        runtime_mode: str = "cloud",
        token_provider: Any = None,
        transport: Any = None,
    ):
        parsed = urlsplit(endpoint_url)
        if (
            parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or runtime_mode not in {"cloud", "local"}
        ):
            raise ValueError("Invalid fixed A2A endpoint")
        if runtime_mode == "cloud":
            if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".run.app"):
                raise ValueError("Private Cloud Run A2A endpoint required")
        elif parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("Local A2A endpoint must be loopback")
        self.endpoint_url, self.scope = endpoint_url, scope
        self.audience = f"{parsed.scheme}://{parsed.netloc}"
        self.token_provider, self.transport = token_provider, transport
        self.runtime_mode = runtime_mode

    async def _token(self) -> str:
        if self.token_provider:
            token = await asyncio.to_thread(self.token_provider, self.audience)
        elif self.runtime_mode == "cloud":
            from google.auth.transport.requests import Request
            from google.oauth2.id_token import fetch_id_token

            token = await asyncio.to_thread(fetch_id_token, Request(), self.audience)
        else:
            return ""
        if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
            raise HandoffUnavailable("Service identity unavailable")
        return token

    async def send(self, reference: dict[str, Any], message_id: str) -> dict[str, Any]:
        expected = HandoffReference.model_validate(reference)
        expected_id = task_identifier(self.scope, expected, message_id)
        try:
            token = await self._token()
            headers = {"A2A-Version": "1.0"}
            if token:
                headers["Authorization"] = "Bearer " + token
            async with httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(28, connect=5),
                follow_redirects=False,
                transport=self.transport,
            ) as http:
                card = AgentCard(
                    supported_interfaces=[
                        AgentInterface(
                            url=self.endpoint_url,
                            protocol_binding="JSONRPC",
                            protocol_version="1.0",
                        )
                    ]
                )
                sdk = JsonRpcTransport(http, card, self.endpoint_url)
                reply = await sdk.send_message(
                    SendMessageRequest(
                        message=Message(
                            message_id=message_id,
                            role=Role.ROLE_USER,
                            parts=[data_part(expected.model_dump(mode="json", by_alias=True))],
                        )
                    )
                )
                if not reply.HasField("task") or reply.task.id != expected_id:
                    raise HandoffUnavailable("Invalid receiver task")
                task = reply.task
                if task.status.state == TaskState.TASK_STATE_WORKING:
                    task = await sdk.get_task(GetTaskRequest(id=expected_id))
                if task.status.state != TaskState.TASK_STATE_COMPLETED or len(task.artifacts) != 1:
                    raise HandoffUnavailable("Receiver task is pending")
                parts = task.artifacts[0].parts
                if len(parts) != 1 or parts[0].WhichOneof("content") != "data":
                    raise HandoffUnavailable("Invalid receiver artifact")
                data = MessageToDict(parts[0].data)
                if (
                    data.get("simulated") is not True
                    or data.get("humanAcknowledged") is not False
                    or data.get("transportStatus") not in {"received", "needs_info"}
                    or data.get("briefStatus") not in {"generated", "unavailable"}
                ):
                    raise HandoffUnavailable("Invalid receiver receipt")
                # Do not duplicate the private receiver brief into the victim-side job.
                return {
                    "taskId": expected_id,
                    "transportStatus": data["transportStatus"],
                    "simulated": True,
                    "humanAcknowledged": False,
                    "briefStatus": data["briefStatus"],
                }
        except Exception:
            raise HandoffUnavailable("Private receiver handoff unavailable") from None
