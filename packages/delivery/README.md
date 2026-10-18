# M3 mock delivery boundary

These adapters call registered MCP SDK tools in process. No HTTP/stdio listener,
external institution address, or caller-selected destination is exposed. The
trusted API outbox receives the adapter object after authenticating the user and
validating explicit packet-version/content-hash approval. This package does not
grant approval or bypass that API gate.

The installed `mcp==2.3.0` names the high-level server `MCPServer`; its former
`FastMCP` import deliberately fails. Bank and rail `create_server(service)`
factories register real SDK tools. `LocalMCPDeliveryAdapter.deliver` invokes
`MCPServer.call_tool`, validates its structured result, and uses a five-second
bound. It starts no network transport and cannot send to a real institution.

`DeliveryProjection` accepts packet identifiers, approval binding, recipient and
pack identity, bounded scalar approved field values, typology/category, and
explicit simulation controls. It rejects full case documents, nested evidence,
transcripts, known credential fields/values, and oversized input. It has no full
case lookup or blob-storage dependency. The repository ledger stores owner/case
identity, request hashes, minimal receipts and hold simulations, never field
values. A restarted service using the same repository replays the same receipt;
changed content under an existing idempotency namespace fails closed.

All receipts carry `simulated: true` and `SIM-` tickets. Payment app submissions
honestly identify `mcp-bank-mock`. Rail categories must come from the selected
pack's recipient mapping. A missing mapping yields `NEEDS_INFO`; it never
invents a category. Hold rules follow the specification's simulation controls
and 90-minute boundary; these are not legal or banking rules. Delivery never
calls `place_hold` automatically. A separate human decision is required by the
owning API before that tool may be invoked.

The API stores returned `deliveryId` values on the case for deletion. Its delete
transaction calls `MockDeliveryService.cleanup_case(tx, owner_uid, case_id,
delivery_ids)`; matching owner/case records alone are removed. MCP status tools
also check owner, case, and adapter before returning a ticket.

An MCP HTTP deployment, Google ID-token authentication, and real institution
connectivity are not supplied by this internal-only M3 implementation.
