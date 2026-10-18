# Separately authorized recovery smoke

The frozen input is unchanged: b6b16aa8ecbfbdab4c41317f3fd6c0867cb35e233a01192d2547e0923a7e4141.
This third separately authorized run used the fixed identifier predicates, packet
LOW profile and one2s transient retry per logical call. HTTP15s, logical35s and
recipient120s limits were explicit. The18-provider-attempt ceiling counted retries.
No hidden SDK retry, output-validation retry or batch rerun occurred.

Results, n=3 packets from one synthetic case:
- Bank: NEEDS_HUMAN_REVIEW,4.062s. Initial writer and its one retry both returnedHTTP429.
- Cyber: VERIFIED,15.250s. Initial writerHTTP429; retry succeeded; entailment passed.
- Payment-app: VERIFIED,16.844s. Initial writerHTTP429; retry succeeded; entailment passed.

Two of3 verified. Descriptive Wilson95% interval [0.208,0.939];
these recipients share one synthetic case and are not independent samples of
real-world accuracy. This tiny smoke does not establish an accuracy rate.
Mean all packet outcomes12.052s; nearest-rank p9516.844s,
n=3. Two successful packet latencies have mean16.047s.
The fast failed bank makes overall latency unsuitable for a success-latency claim.
No causal performance comparison with earlier runs is made.

Eight actual provider attempts:4 successful SDK responses,4HTTP429 failures.
Three2s backoff events are separately persisted. Observed SDK token usage:
8320 input,1462 output; reasoning unknown (absent).
Failed attempts have no returned usage. Monetary cost remains unverified.
No quota, billing, resource or deployment changes were made.

The JSON report retains all final checks and per-logical-attempt histories.
The exclusive attempts JSONL retains every actual request and backoff.
Two safe writer snapshots are in the synthetic-only drafts JSONL; they remain
explicitly unverified at writer level, while final report checks establish the
subsequent verification result. These outputs may be reused without another
writer request. Do not treat raw writer snapshots as approved sendable packets.

The earlier1/3 baseline and0/3 LOW reports remain unchanged. Availability across
runs is now baseline-bank plus recovery-cyber/payment-app. A composed demo must
carry those run origins; it must not claim this recovery run verified all three.
No further model calls were made or authorized by unused headroom under the cap.

Offline prerequisite proof:178 tests passed (56 packet), Ruff/mypy clean. Tests
cover actual-attempt accounting, persistent ledger order, allowed transient types,
one retry, remaining deadline, cancellation and fabricated-identifier rejection.
