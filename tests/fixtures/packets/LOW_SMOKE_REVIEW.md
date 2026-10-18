# Separately authorized LOW follow-up

Identical frozen input hash: b6b16aa8ecbfbdab4c41317f3fd6c0867cb35e233a01192d2547e0923a7e4141.
Provider model/project/location and15s HTTP/20s outer bounds unchanged. Packet
profile opted into LOW,2500 writer output tokens,temperature0.3; baseline used
2000/0.0. n=3:0 verified,3 NEEDS_HUMAN_REVIEW. This does not replace baseline1/3.

Seven provider attempts:4 successful writer responses; repair errors in order
HTTP429, HTTP504, HTTP429. All attempts are in the exclusive JSONL ledger.
No verifier request occurred because deterministic identifiers checks blocked
initial drafts. The run stopped as configured without retrying provider errors.
Bank11.094s/cyber20.672s/payment-app17.937s; mean16.568s;
nearest-rank p9520.672s, n=3. These are failed-packet latencies, not verified
packet completion latency. No causal comparison with the baseline is justified.
Observed SDK usage:6574 input,2141 output;
reasoning usage unknown (all absent). Failed requests have no returned usage.
Cost remains unknown, not zero.

Offline regression reproduced identifier-guard false positives for the harmless
request "Please provide a reference number." and sentence-terminal punctuation
following a correct UPI handle. The guard now distinguishes numeric reference
values from the word "number" and strips sentence-terminal dots from handles;
actual invented references/handles remain blocked. The original generated drafts
were not snapshotted, so their exact triggering substrings are unavailable and we
cannot claim that every original block had this exact cause. Both reports and
ledgers stay unchanged. No lost model prose has been reconstructed or invented.

Initial safe draft availability: only the original baseline bank finalcontent is
available. LOW initial drafts and failed baseline earlier drafts are lost; repair
inputs/previousDraft were not persisted by the old instrumentation. Future
synthetic-only smoke snapshots save shape-valid, credential-safe writer outputs
with an unverified marker and matching input hash. No model draft goes to general
runtime logs. Later provider failure retains prior safe draft and its blockers,
while first-call failure still returnsNone.

Offline proof after guard/snapshot fixes:162 combined tests pass (40 packet,
122 intake/classification). Ruff/mypy clean. No additional model calls occurred.

## Proposed targeted recovery, awaiting approval

For a future packet-only wrapper, allow at mostone transient retry per logical
writer/verifier call on typed429/503/504/connect_timeout/read_timeout/timeout.
Never retry400/401/403/404, schema errors, safety blockers or outer cancellation.
Each attempt remains a separate ledger row and consumes the global provider cap.
Use a single2s backoff (first bounded exponential step), honor cancellation, and
admit a retry only if at least17s remains in the logical deadline. Keep15s per
HTTP attempt; set this explicit logical call budget to35s including queue/backoff.
This changes the latency budget, so the existing latency target remains unmet.
Use one global per-recipient120s deadline across writer/entailment/repairs, retain
partial safe content, and stop before any call lacking budget. Do not multiply
this with SDK retries (SDK remains attempts1). Keep max2 semantic repair rounds
separate from transient transport retries. Root must choose a fresh explicit
provider cap before another paid run; no retry policy is enabled by this report.

HTTP429 establishes resource-exhaustion/capacity pressure, but does not distinguish
quota, shared capacity or acceleration limits for this project. No billing/quota
mutation is justified. Official general guidance supports bounded backoff:
https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/deploy/error-code-429
https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/retry-strategy
