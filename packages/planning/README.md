# Deterministic planner (T16)

`compute(pack=..., facts=..., classification=..., now=..., language="en",
source_passages={"sourceId:passageId": "snapshot passage"})` returns the canonical
`Plan`. It is synchronous, has no model calls or network/storage mutations, and is
ready for the worker/API workflow. The caller owns authenticated pack selection,
facts revision binding, audit and persistence. Retired packs fail closed.

Rules use the existing bounded AST interpreter. All recipient and sequence expressions
are compiled before evaluating, including rules which ultimately do not apply. UNKNOWN
recipient conditions exclude the recipient with a notice; UNKNOWN sequencing conditions
do not set an order. Recipients and channels come exclusively from the selected pack.
The engine rejects duplicate IDs, unknown recipient references, missing channels and
more than 300 planning rules.

Ordering is explicit sequence number, then source-bound deadline urgency for high/critical
cases, then fixed recipient-type priority and recipient ID. Multiple matching sequences
use the lowest number; ties retain their rule references. Earliest numeric deadline wins
for display, with hard/soft and rule ID breaking ties; every applicable deadline retains
its rule reference. Other deadlines can be inspected from the bound pack. Operational
classification urgency never becomes a legal time window.

Numeric deadlines require a reviewed/published pack, a verified rule and nonempty resolved
passages whose source IDs belong to that pack. Human-review classification suppresses
numeric timing. Draft/unverified rules retain notices and resolvable citations, but no
date or verified-channel claim. Business calendars always produce unsupported_in_v1.
Missing/future anchors, malformed durations and DST gaps/ambiguities produce a warning,
not a guessed date. Calendar arithmetic uses the pack time zone and outputs UTC.
Status wording is coarse; null duration never becomes a made-up numeric countdown or
an inferred ASAP instruction. The source remains available for its exact wording.

Implementation choice for review: fixed English/Hindi templates replace the optional
LLM explanation step in spec 5.6. This prevents rationale/source text from generating
extra recipients, deadlines or instructions, and avoids paid calls for deterministic
planning. Recipient names are displayed verbatim from the pack; free-text sequencing
rationales and deadline consequences are not interpolated into actionable prose.
Hindi templates are authored engineering copy and still require fluent human review.
The root should record this choice in the M2 ADR; no human source approval is fabricated.

Plan IDs hash all supplied inputs including passage content hashes and generation time;
identical inputs produce identical results. Semantically equivalent reordered pack
documents keep the same step order but may produce a different content-bound plan ID.
The engine treats resolved passage inputs as registry snapshots, not fresh legal review.

Verification on 14 October 2026: 29 synthetic unit tests passed, planner line coverage
98%, Ruff and mypy passed. Tests cover exact recipient selection, tri-state conditions,
malicious expressions, stable ties, rationale injection, UTC/calendar/month/DST timing,
deadline boundaries, drafts/missing citations, business calendars and human-review guards.
No cloud/model invocation, latency benchmark, legal correctness or human review is
claimed by these tests.
