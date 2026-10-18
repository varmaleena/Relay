from mcp.server.mcpserver import MCPServer

from packages.delivery.models import DeliveryProjection, DeliveryReceipt
from packages.delivery.service import MockDeliveryService


def create_server(service: MockDeliveryService) -> MCPServer:
    server = MCPServer(
        "mcp-rail-mock", instructions="Synthetic simulation only. No authority connection."
    )

    @server.tool()
    async def file_report(projection: DeliveryProjection, idempotency_key: str) -> DeliveryReceipt:
        return await service.file_report(projection, idempotency_key)

    @server.tool()
    async def get_ticket(owner_uid: str, case_id: str, delivery_id: str) -> dict:
        return service.get_status(owner_uid, case_id, delivery_id, adapter="mcp-rail-mock")

    @server.tool()
    async def list_recipients_notified(owner_uid: str, case_id: str, delivery_id: str) -> dict:
        result = service.get_status(owner_uid, case_id, delivery_id, adapter="mcp-rail-mock")
        return {
            "simulated": True,
            "ticketRef": result["ticketRef"],
            "notifiedInstitutions": result["routedTo"],
        }

    return server
