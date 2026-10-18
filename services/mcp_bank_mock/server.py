"""Actual MCP SDK registrations, reachable only by the internal adapter in M3."""

from mcp.server.mcpserver import MCPServer

from packages.delivery.models import DeliveryProjection, DeliveryReceipt, HoldReceipt
from packages.delivery.service import MockDeliveryService


def create_server(service: MockDeliveryService) -> MCPServer:
    server = MCPServer(
        "mcp-bank-mock", instructions="Synthetic simulation only. No bank connection."
    )

    @server.tool()
    async def submit_dispute(
        projection: DeliveryProjection, idempotency_key: str
    ) -> DeliveryReceipt:
        return await service.submit_dispute(projection, idempotency_key)

    @server.tool()
    async def place_hold(
        owner_uid: str, case_id: str, delivery_id: str, idempotency_key: str
    ) -> HoldReceipt:
        return await service.place_hold(owner_uid, case_id, delivery_id, idempotency_key)

    @server.tool()
    async def get_status(owner_uid: str, case_id: str, delivery_id: str) -> dict:
        return service.get_status(owner_uid, case_id, delivery_id, adapter="mcp-bank-mock")

    return server
