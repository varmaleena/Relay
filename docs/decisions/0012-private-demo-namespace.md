# ADR 0012: private rehearsal namespace and explicit reset approval

18 October 2026. E41's reset-to-seed behavior cannot mean a global data clear in
an owner-isolated SaaS demo. DemoControl therefore requires DEMO_MODE=true, an
admin claim, a configured `synthetic-*` namespace, a separately injected existing
victim Actor, and namespace records bound to one operator and victim UID.
No authentication users or credentials are created. No collection scan occurs.

E41 requires a UUID Idempotency-Key, X-Demo-Namespace and explicit
X-Demo-Reset-Confirm equal to that namespace, in addition to the source's empty
body. Only known case IDs with exact synthetic namespace/operator/owner markers
are eligible. The actual IntakeService.delete_case mark transaction rechecks the
expected marker before deletion, preventing a stale precheck from deleting a
case moved to another namespace. Existing domain cleanup handles evidence,
exports, receiver projections and linked records. A bounded operation journal
records retries; no reset of unrelated reports, packs, evaluation runs or users
is authorized by this endpoint.

Reset seeds four fresh scenario inputs through actual create-case/merge-facts
logic. It creates no model results, source-review signatures, approvals, sent
messages or historical evaluation metrics. The six-case linking ring and actual
measured evaluation seed remain separate unfinished requirements. LIVE labels
mean configured execution mode; preflight marks measurement as absent. Replay
configuration fails until an actual cached-output provider exists.

The actual mock's typed Simulation supports bank auto/success/funds_moved and
rail normal/misrouted. E43 maps public rail success to normal. Forced needs_info
fails501 until that behavior is implemented in the actual adapter. Stored
configuration affects only future approved projections after parent integration;
it does not retroactively alter delivery receipts or real institutions.
