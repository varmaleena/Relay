# ADR 0006: packet verification, review and simulated delivery

Status: M3 implementation decision, 15 October 2026. Validation results and
remaining gates belong to the phase report; this decision is not a deployment claim.

Packet jobs use the existing transactional repository and worker. A packet binds
its plan, canonical input hash, facts revision, recipient, version and content
hash. Editing creates another version and queues verification. A missing field
may be confirmed for that packet; it cannot replace an existing recorded fact.
Known fact corrections go through intake and invalidate prior plans/messages.
Old versions remain available to the audit export and deletion cascade.

The writer prepares bounded prose; trusted code supplies structured fields,
provenance, source references, footer and completeness. Deterministic checks run
before sentence-level model entailment. Initial generation plus at most two
repairs are allowed. Unsafe credentials are never retained as a failed draft.
Verification failure keeps approval unavailable; it is not a human signoff on
the pack or an assurance that the model is infallible.

Explicit confirmation identifies the recipient and current version. The API
persists a content-bound approval and outbox job before calling any mock tool.
ActionPolicy rechecks the stored approval, owner, current version, verification,
input freshness, expiry and simulated-only boundary. Delivery idempotence uses
packet/version and owner/case/recipient namespace. Timing is frozen at approval
so a retry cannot change the projection hash. Claim tokens and bounded attempts
prevent competing workers from overwriting one another.

The deterministic receipt identity is reserved on the case before delivery.
The mock ledger atomically checks case existence, ownership, deletion and expiry;
deletion removes reserved receipts and all packet versions, approvals, jobs,
notifications and generated files. This closes a delete-during-send race without
claiming exactly-once delivery to a real institution.

MCP 2.3's installed API registers actual bank and rail tools with MCPServer. The
local adapter invokes those registered tools in process. No publicly accessible
institution endpoint or real bank integration is deployed. Sending submits a
simulated report; it does not automatically place a hold or invent an institution
decision. The current draft rail pack lacks a category mapping, so its honest
receipt may be NEEDS_INFO. Receivers and the actual information-request/answer
loop remain M4 (T25); E19 rejects a nonexistent request and never resends implicitly.

E18 returns a typed, authenticated JSON capability response instead of the source
spec's bare 302. This lets the generated JSON client validate a download URL and
expiry before opening it. Local capabilities last 60 seconds and recheck owner,
case and current version on download; edits and deletion revoke them. Production
GCS signing remains subject to full application infrastructure verification.
The PDF is a real ReportLab artifact, with HarfBuzz shaping and licensed Google
Noto Devanagari glyphs, a simulation banner and separate victim copy. Visual
rendering does not establish fluent Hindi review or accessible PDF tagging.

Packet-only LOW thinking is an explicit configuration for the documented
gemini-3.8-flash capability; intake/classifier defaults are unchanged. A wrapper
shares the underlying SDK and semaphore. One bounded transient retry is allowed
for typed transport/429/503/504 failures, with backoff and a logical deadline;
schema, safety and cancellation failures do not receive that retry. Every actual
attempt counts against the smoke cap and is recorded. This is failure handling,
not evidence that provider capacity or latency targets are met. Original failed
batches remain frozen alongside any separately measured follow-up.

Local fixture browser testing runs with the queue worker paused to prevent a
synthetic pipeline job from being consumed by live inference. The test helper
requires exact emulator configuration and a newly created empty case. It calls
domain services, exposes no privileged product endpoint and grants no production
identity bypass. Fixture UI evidence and live model evidence are reported separately.
