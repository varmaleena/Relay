# M4 receiver and follow-up checkpoint

17 October 2026. Primary user: the person preparing a scam report. Secondary user:
a signed-in fictional institution reviewer, restricted to its addressed projection.
The user approved remaining phases toward the submission deadline.

Implemented: scoped receiver queue and review console, explicit version-bound
decisions, simulated MCP hold, missing-information requests, and user answers that
create a new draft and require verification and fresh send approval. The receiver
cannot read the full victim case. The real A2A SDK receiver and durable caller use
immutable references, private OIDC transport, leases, idempotency and deletion
hooks. Transport receipt is distinct from a human acknowledgment.

Evidence: 96 focused receiver/A2A/worker tests passed, plus the newly added actual
approved-delivery → worker → SDK A2A → deletion integration test. Seventeen
contract checks and TypeScript compilation passed. All 55 actual Firebase
Firestore/Storage rule checks passed. These runs overlap; do not sum them into a
unique test count. No provider inference was used in these checks.

Actual local browser run r2 used separate legitimate Firebase user/staff accounts,
actual API/Firestore/MCP transport, and explicitly synthetic model-stage fixtures.
It passed approval, addressed delivery, staff information request, foreign-org
404 denial, one user answer, successful verification of the new version, fresh
approval requirement, and deletion204. Exactly one send approval and one answer
were observed. Evidence: `.tmp/m4-browser-r2/result.json`. Screenshots capture an
intermediate draft before the next detail refresh, not final verified UI evidence.
The earlier r1 generic GET error did not recur in r2 and remains recorded; frontend
refresh behavior is under follow-up review.

Judge relevance: this demonstrates controlled multi-party follow-through and
human control beyond a conversational answer. It does not demonstrate a real bank
integration, money recovery, production AI reliability or measured social impact.
Human Hindi/source review, outsider comprehension, hosted M4 transport and final
submission artifacts remain open. Cloud build/rollout is a separate gate.
