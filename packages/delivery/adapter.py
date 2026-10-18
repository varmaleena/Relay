"""Internal capability: calls real registered MCP SDK tools without network I/O.

No HTTP/stdio listener or caller-controlled destination exists. Only the trusted
API outbox receives this object; external users cannot invoke MCP tool calls.
"""

import asyncio

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult
from pydantic import ValidationError

from .models import DeliveryError, DeliveryLookup, DeliveryProjection, DeliveryReceipt, HoldReceipt
from .service import MockDeliveryService


class LocalMCPDeliveryAdapter:
    def __init__(self, service: MockDeliveryService):
        from services.mcp_bank_mock.server import create_server as bank_server
        from services.mcp_rail_mock.server import create_server as rail_server

        self.service = service
        self.bank_server: MCPServer = bank_server(service)
        self.rail_server: MCPServer = rail_server(service)

    async def deliver(
        self, projection: DeliveryProjection, idempotency_key: str
    ) -> DeliveryReceipt:
        # Revalidate even if an in-process caller used model_construct/copy.
        projection = DeliveryProjection.model_validate(
            projection.model_dump(mode="json", by_alias=True)
        )
        _, recipient = self.service._recipient(projection)
        if recipient.type in {"bank", "payment_app"}:
            server, tool = self.bank_server, "submit_dispute"
        elif recipient.type == "national_cyber_authority":
            server, tool = self.rail_server, "file_report"
        else:
            raise DeliveryError("recipient_adapter_unavailable")
        try:
            result = await asyncio.wait_for(
                server.call_tool(
                    tool,
                    {
                        "projection": projection.model_dump(mode="json", by_alias=True),
                        "idempotency_key": idempotency_key,
                    },
                ),
                timeout=5,
            )
        except (ToolError, TimeoutError):
            raise DeliveryError("mock_delivery_failed") from None
        if (
            not isinstance(result, CallToolResult)
            or result.is_error
            or not result.structured_content
        ):
            # Never echo tool error content, which may contain invalid inputs.
            raise DeliveryError("mock_delivery_failed")
        return DeliveryReceipt.model_validate(result.structured_content)

    async def place_hold(
        self, owner_uid: str, case_id: str, delivery_id: str, idempotency_key: str
    ) -> HoldReceipt:
        """Internal capability invoked only after a receiver's explicit decision."""
        try:
            lookup = DeliveryLookup(owner_uid=owner_uid, case_id=case_id, delivery_id=delivery_id)
            if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 200:
                raise DeliveryError("mock_hold_failed")
            result = await asyncio.wait_for(
                self.bank_server.call_tool(
                    "place_hold",
                    {
                        "owner_uid": lookup.owner_uid,
                        "case_id": lookup.case_id,
                        "delivery_id": lookup.delivery_id,
                        "idempotency_key": idempotency_key,
                    },
                ),
                timeout=5,
            )
            if (
                not isinstance(result, CallToolResult)
                or result.is_error
                or not result.structured_content
            ):
                raise DeliveryError("mock_hold_failed")
            return HoldReceipt.model_validate(result.structured_content)
        except (ToolError, TimeoutError, ValidationError):
            raise DeliveryError("mock_hold_failed") from None
