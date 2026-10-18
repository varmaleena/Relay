# T40 Demo Control backend checkpoint

18 October 2026. The operator is an authenticated admin rehearsing an explicitly
synthetic dataset in a dedicated namespace. Their job is to load a fresh scenario,
choose supported simulated behavior or reset only their namespace with explicit
confirmation. No credentials or external communications are generated.

New packages/demo contains DemoControl and four fictional scenario definitions.
New services/api/demo/router.py provides E41/E42/E43 using existing canonical
DTOs plus mandatory namespace and UUID headers; reset also requires an explicit
namespace confirmation header. The namespace is fixed server-side, bound to an
operator UID and injected existing victim Actor, and accepts at most20 case IDs /
100 operation journal entries. Unknown scenarios, other namespaces/operators,
off-mode/nonadmin use, conflicting idempotency, stale load replay and capacity
fail explicitly. Reset validates all known targets before deletion and invokes
the actual owner-bound IntakeService deletion with the exact marker rechecked
in its initial transaction. It then seeds four fresh INPUT cases. No plans,
verified packets, approvals, deliveries or past model results are fabricated.

`overview` is a cheap configured-versus-measured report. Dependencies are marked
configured true/false and measured false; qualityGate is not_measured. Linking
ring and evaluation run seed flags are false. Replay is unavailable without an
actual cached-output provider and configuration rejects it. Scenario input mode
voice does not claim a completed voice conversation; injection_attempt provides
an explicitly adversarial suggested input without executing or obeying it.

Parent integration:

- Configure a disabled-by-default Demo feature, DEMO_MODE, a dedicated namespace
  `synthetic-...` and trusted existing demo victim UID; inject Actor(uid,'victim').
  Never derive that UID or namespace ownership from untrusted request JSON.
- Construct DemoControl(intake,namespace=...,victim=...,demo_mode=...,
  genai_mode='live',configured={...}); mount create_demo_router before E41–43
  fallback stubs under existing Firebase/AppCheck/admin authentication.
- Add custom X-Demo-Namespace headers for all controls, UUID Idempotency-Key for
  every mutation, and X-Demo-Reset-Confirm equal to the namespace only after a
  human confirms reset. Existing generated client lacks these custom headers;
  do not weaken backend headers to work around that integration gap.
- In trusted approved delivery transaction use simulation_for(tx,case) only for
  marked tracked cases. Preserve actual minutesSincePayment when copying its
  bank/rail modes into the existing DeliveryProjection. No behavior change
  bypasses the current version-bound human approval. Forced needs_info501 is an
  honest incomplete behavior, not a simulated successful control.
- Parent's exact expected_demo_marker guard in IntakeService.delete_case is a
  required dependency, already implemented. Never call admin global deletion
  from reset. Existing owner deletion handles domain cascades.

Open source requirements: Demo Control UI, actual production-safe feature wiring,
preflight CLI target, replay provider/cache labels in actual execution, timer
speed controls, jurisdiction switch UI, six-case ring seeding and a genuine
completed evaluation seed, scene/present-mode integration. No cloud/model calls
or human usability validation were performed in this slice. Synthetic fixture
checks do not establish the full three-minute live presentation acceptance gate.

Actual validation: 14 focused tests passed, including admin/off-mode/namespace/
operator isolation, fresh/idempotent scenario inputs, canonical HTTP headers,
namespace-only reset with unrelated same-owner report preserved, tampered target
precheck, actual initial-deletion-marker TOCTOU rejection, stale load replay,
capacity/active operation guards, unsupported needs_info501, and configured versus
measured overview. A supported funds_moved setting was passed through the actual
registered local MCP adapter and produced FUNDS_ALREADY_MOVED with simulated=true.
No model calls occurred. Ruff and mypy passed for the five owned source modules.
