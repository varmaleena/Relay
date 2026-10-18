"""Explicit staff hold adapter invoking an actual registered MCP mock tool."""

import asyncio

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from packages.delivery.models import DeliveryError, HoldReceipt


class MCPHoldAdapter:
    def __init__(self, delivery_adapter):
        self.server = delivery_adapter.bank_server

    async def __call__(
        self, owner_uid: str, case_id: str, delivery_id: str, key: str
    ) -> HoldReceipt:
        try:
            result = await asyncio.wait_for(
                self.server.call_tool(
                    "place_hold",
                    {
                        "owner_uid": owner_uid,
                        "case_id": case_id,
                        "delivery_id": delivery_id,
                        "idempotency_key": key,
                    },
                ),
                timeout=5,
            )
        except (ToolError, TimeoutError):
            raise DeliveryError("mock_hold_unavailable") from None
        if (
            not isinstance(result, CallToolResult)
            or result.is_error
            or not result.structured_content
        ):
            raise DeliveryError("mock_hold_unavailable")
        return HoldReceipt.model_validate(result.structured_content)
