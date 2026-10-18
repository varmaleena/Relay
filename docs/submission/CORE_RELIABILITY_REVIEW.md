# Core reliability review: fastest safe next live report check

18 October 2026. Read-only inspection of existing local artifacts and current
source; no inference, cloud reads, deployment, quota or code changes performed.

Recommendation: keep the currently validated `gemini-3.8-flash` LOW packet profile,
strict deterministic and entailment verification, current one-request transport,
single-recipient sequencing, and newly implemented8–10s429 backoff. After the
already tested core revision is deployed, run ONE bounded, isolated synthetic
hosted flow with the updated harness. Inspect every stored packet even when the
aggregate job fails. If any current canonical packet is VERIFIED with
verification.passed=true, zero blocker failures and unchanged content/version
proof, check that packet's actual authorized PDF. Record this as a partial live
report/PDF success if observed, while retaining the failed three-recipient gate.
Do not require the whole batch to succeed before inspecting useful checked work.

## What the existing hosted evidence actually says

| Run | Observed result | Concrete limitation |
|---|---|---|
| full-r1 | Three canonical VERIFIED reports;30/29/30 checks, zero failed | Browser polling stopped after API429; terminal job not observed; PDF never attempted. Full gate failed. Cases deleted204. |
| full-r2 | Aggregate job succeeded; three NEEDS_HUMAN_REVIEW reports, each16 checks and one failure | Eight SDK calls: intake/classifier success, three writer successes, two504s and one429; no verifier calls. Failed check IDs were not retained. Full gate failed. |
| full-r3 | Aggregate job failed; canonical quality inspection unavailable | Eight SDK calls: intake/classifier success, two writer/verifier transport-success pairs, two429s on another writer. Three API429s blocked final inspection; quality=[] is unknown, not proof zero stored reports. Cases deleted204, no PDF. |

These runs use one synthetic case each and differing repairs/configurations.
They are diagnostic attempts, not an independent accuracy dataset or an
established reliability percentage. Verifier HTTP success alone does not prove
its verdict was passed. The previous frozen same-case recovery obtained2/3
verified with8 actual calls and4 typed429 failures, but its outputs cannot be
silently combined with another run and relabeled a fresh live result.

## Current budgets and retry behavior

- GoogleGenAIClient uses15s HTTP timeout, SDK attempts=1, shared semaphore;
  deployed configuration files set MAX_MODEL_CONCURRENCY=1 and global routing.
- Packet writer has2500 maximum output tokens/temperature0.3; entailment2000/0.0;
  LOW is explicitly capability-validated only for gemini-3.8-flash.
- RetryPacketClient has35s PER logical writer/verifier call, at most two HTTP
  attempts. It retries only allowed typed transient failures.429 now waits8–10s;
  other transients2s. It admits retry only if backoff+15s remains. Fast429s fit
  this window; a sufficiently late failure correctly gets no second attempt.
- The35s budget is not the budget for all three reports. PacketService builds
  recipients sequentially, each with a120s outer deadline. Each recipient may
  perform up to three writer/verifier rounds.35s x6 can exceed120s, so the outer
  deadline may stop an expensive repair sequence. Cancellation must remain real.
- Successful per-recipient content commits durably before the next recipient.
  A partial failure must not erase it. Missing recipients can be resumed under
  current input/plan/content proof. Existing stored unverified version1 content
  is also retained; rerunning generation is not a guarantee it will be repaired.

The8–10s backoff postdates the failed hosted runs above. It is a proposed capacity
mitigation, not a measured improvement. No evidence proves an adjustable fixed
project quota caused the429s; the saved Service Usage review explicitly says it
did not distinguish pooled capacity, acceleration or usage-tier pressure.
Do not change billing, request a guessed quota increase or parallelize requests.

## Why not change token limits or models tonight first?

Observed successful hosted writer outputs were371–505 candidate tokens; two
successful verifier outputs were170. These are candidate output counts, not a
proven upper bound including all reasoning tokens. Lowering max output to e.g.
1024/512 is a plausible separately tested experiment, but current evidence does
not establish that it fixes429, and truncation may break structured JSON or
verdict completeness. Do not introduce that extra variable into the immediate
one-report attempt. Preserve the successful schema/profile first.

No alternative reasoning model is established as generation-capable for this
project by the artifacts inspected here. `gemini-3.8-live` has an actual audio
setup/turn probe, which does not validate it for structured packet writing or
entailment. No unvalidated model switch is recommended. LOW itself already had
a failed historical batch and is not a proven fix by name alone.

## Concrete execution/stop rules for the parent

1. Verify the deployed image contains statement-provenance anchoring, worker
   model logging, safe GET429 final inspection, partial-report PDF handling and
   the8–10s transport retry. Keep receiver/linking/voice disabled for this check
   unless their presence is required; no unrelated model jobs should compete.
2. Use one synthetic case and one generation action, preserve the original
   declared attempt ceiling and exact observed call ledger. No automatic new
   paid run or automatic mutation retry after failure. Do not interpret unused
   ceiling as permission for repeated experiments.
3. Current scripts/cloud_browser_smoke.mjs already records terminal job error,
   progress, failedCheckIds, safe final GET retries and selects any verified
   partial report for PDF. Use those observations rather than aggregate success
   alone. The ordinary UI also needs to expose stored partial reports clearly.
4. A partial VERIFIED result may be inspected/exported through its normal
   authenticated current-version path. Do not mark all packets verified, remove
   required recipient coverage, downgrade blockers or auto-approve delivery.
5. Before deletion, persist sanitized status/check IDs, actual model call counts,
   timing/token availability, current version/hash proof and PDF result. Preserve
   all failure records. If none verifies, stop, retain exact blockers and report
   the failure; do not substitute synthetic verifier outputs or historical drafts.

This recommendation aims for one honestly observed current live checked report.
It does not claim the full hosted flow, three-minute live presentation, all
three reports, quality target or finalist readiness has already passed.

Evidence inspected: .tmp/cloud-browser-full-r{1,2,3}/result.json;
.tmp/cloud-full-r{2,3}-audit.json; docs/planning/DEV_DEPLOYMENT_EXECUTION.md;
tests/fixtures/packets/{QUOTA_CAPACITY_REVIEW,LOW_SMOKE_REVIEW,
RECOVERY_SMOKE_REVIEW}.md; agents/{intake/clients.py,packets/clients.py,
packets/core.py}; packages/packets/service.py; services/api/runtime.py;
infra/env/dev-application.yaml; scripts/cloud_browser_smoke.mjs.
