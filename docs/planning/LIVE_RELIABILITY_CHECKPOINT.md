# Live primary-flow reliability checkpoint

17 October2026. User-authorized corrective M3 checkpoint plus minimal GCP
preparation; M4 is not authorized. Attached specifications describe requirements,
not permission for unrelated deployment/account changes. This document records
scoped implementation and a separately authorized bounded live measurement.

## Evidence and diagnosis

Reviewed BUILD_SPEC5.7/5.8/18.2/18.3, plan M2/M3 gates, ADR0005/0006/0007,
current packet/intake/classification clients, domain workers and frozen reports.
M2 classification live20-case smoke had12 plans,3 genuine clarification outcomes,
5 failures; authorization15/20,typology14/20. Saved Wilson intervals and latency
remain in its report; generic failures do not prove semantic misclassification.
M3 original/LOW/recovery results were1/3,0/3,2/3 on one repeated synthetic scenario,
not independent cases. Recovery has4 typed HTTP429 failures across8 actual calls;
2s bounded retries recovered cyber/app but not bank. Original untyped errors and
lost early drafts cannot be reconstructed. Identifier false positives were fixed
offline; no forged replacement result was inserted into frozen reports.

The concrete newly diagnosed service defect was all-recipient buffering:
PacketService kept successful results only in RAM and committed after every
recipient completed. A None result raised immediately, discarding earlier useful
work and preventing later recipients from being tried. Repeating the job could
pay to generate earlier successful reports again. The independent recipient
model harness did not expose this API/domain failure mode.

Provider availability is a different issue. The15October read-only quota snapshot
covered372metrics/2pages; no fixed3.8Flash model bucket was found. Documented model
options excluded fixed quota. HTTP429 is consistent with capacity/resource or
usage-tier pressure; exact mechanism is unproven. Generic30000/min configuration
was not measured utilization. No quota/billing escalation is justified by this.

## Smallest implemented reliability change

Each safe generated recipient report now commits in its own guarded transaction.
The transaction rechecks claim/state/lease, actor/case, input/facts, plan, pack and
catalog proof before adding packet/version/notification/audit records. Typed model
failure or120s recipient timeout records that recipient failure and permits other
recipients to be attempted. A later failure does not erase committed progress.

An explicit retry reuses an unchanged generation checkpoint only when its plan,
input/catalog/pack/facts revision, packet version and actual content hash still
match the stored proof. It does not create another version or notification.
Edited/version-changed or tampered checkpoints reject reuse409; existing edit and
reverify paths remain authoritative. This conservative limitation may require a
new plan before generation resume after edits; it is not silent overwriting.
Required recipient coverage gates PACKETS_VERIFIED. A verified subset remains
PLAN_READY. NEEDS_HUMAN_REVIEW remains non-sendable and no approval is fabricated.
Deletion, lost claims, stale sources and existing approval/delivery guards remain.
PDF writes/download capabilities now use separate export_storage, defaulting to
the original store locally; version/edit/delete checks remain unchanged.

Focused offline proof:23 packet-service tests passed, covering first/middle/last
recipient failure, retain/resume, no duplicate version/notification, restarted
expired lease, changed proof rejection, stale earlier checkpoints after catalog
change, delete during later generation, and separate export PDF capabilities.
Ruff/mypy passed. These are not provider or human-usability results.

## Exact separately authorized live smoke

- One fresh synthetic India/UPI/INR45000/Test Bank/phone/authorized-manipulated
  scenario; known canonical facts entered directly. No intake-model claim.
- Actual ClassifierAgent through ADK/PlanningService if successful within budget;
  no silent fixture substitution. Explicit local draft-pack preview; sources
  remain unverified. Three recipients:bank,cyber,payment-app.
- Actual PacketService against an isolated Firestore-emulator case, not the
  independent per-recipient pipeline harness. General worker must be paused so
  only these exact job IDs can spend this measurement's budget; restore afterward.
- One shared cap of18 ACTUAL provider attempts across classification, original
  packet job and at mostone explicit resume. Retries/schema attempts also count.
  Concurrency1;15s HTTP, packet35s logical and120s recipient limits unchanged;
  writer2500/verifier2000 output bounds; existing packet-only LOW profile and one
  typed transient retry with2s backoff. No new retry policy or model substitution.
- Flush each actual attempt/backoff to unique ledger, safe synthetic writer
  snapshots only; no credential/raw-error/general-runtime prose logging. Save
  initial/resumed job outcomes, retained IDs/proofs/hashes and actual timings.
- Stop at cap, persistent provider failure or failed plan; no hidden rerun,
  borrowed live-artifact fixture or real institution contact. The INR1000 figure
  remains the user's planning target; missing usage/cost remains unknown.

Acceptance: one fresh case's reports are either visibly checked or explicitly
failed; partial progress survives and a permitted resume invokes only missing
recipients. A3/3 same-case result may be reported only if actually obtained in
this measured flow. Otherwise retain the failure with its exact typed cause.
Record n=1case/3correlated packets; do not infer production accuracy or latency
SLO from it. Cloud deployment, Hindi human review, pack publication and M4 remain
separate gates. Automated checks are not user comprehension validation.


## Actual authorized primary-flow measurement (frozen)

Report: tests/fixtures/packets/primary_live_flow_report.json and its input,
per-attempt JSONL and safe synthetic writer snapshots. One fresh case, actual
live ADK classifier, actual Firestore-emulator domain workers, no intake-model or
HTTP/browser/authentication-flow claim. No fixture classifier fallback occurred.
Classification succeeded as authorized_manipulated. Fourteen actual provider
calls were used across initial generation and one explicit resume; total observed
wall time163.359s. The initial job retained bank/cyber drafts (progress2/3);
resume retained their exact IDs/version/content hashes/generation proofs and
added payment-app (progress3/3). This proves durable partial progress in the
measured service path, not successful report verification.

All3 reports remained NEEDS_HUMAN_REVIEW:0/3 verified. Canonical manual facts
stored source=confirmed with reference=null; two directly matched fields
(payment.timestamp/payment.method) failed the deterministic provenance check.
Other wire-format leaf origins used camelCase (transactionRef/victimBank and
amount.value/currency), which previously fell through to generic path origins.
This was a server provenance-contract mismatch, not missing user information or
an unsupported model fact. Writer repairs could not repair server-owned origins.
There were7 typedHTTP504 and2HTTP499 failures; the ledger's http_other rows do
not retain499, but sdkFailures safely preserves that exact status. Root cause of
HTTP499 is not inferred from its status. No entailment-model request ran because
the deterministic provenance check stopped it. No production reliability target
was achieved. These3 correlated packets from one case are not an accuracy sample.

The measured worker identity/parent and no-running-jobs checks passed; suspension
and resume both completed. The synthetic case/reports remain in the emulator;
only this measurement's queued/running jobs were stopped in cleanup. A separate
read confirmed0 pending jobs for its own case. No other cases were altered.
The restored worker retained old in-memory code and needs an ordinary controlled
restart after integration before it serves the new implementation.

## Offline fix after the frozen measurement

anchor_confirmed_facts deep-copies canonical case facts, normalizes path aliases,
and anchors missing server-confirmed origins to the persisted case ID, facts
revision and exact path. Composite amount/identifier fields are confirmed only
if every component is confirmed. Mixed/incomplete origins fail closed; extracted
origins keep their evidence reference/confidence and are not converted into
confirmed facts. PacketService._context supplies server case/revision values.
The case fact document is not rewritten and no model supplies provenance proof.

The packet pipeline now stops futile writer repairs for required-field, origin
or other server-metadata blockers. It still permits the bounded existing semantic
repair loops and retains strict evidence, safety and approval checks. Neither
change retroactively converts the frozen3 drafts into verified reports.

After these runtime changes85 focused agent/service tests passed39.75s. One
additional targeted test then passed through the actual PacketService,
PacketPipeline and deterministic verifier with real server-confirmed canonical
facts and fixture writer/entailment outputs: all3 reports verified offline,
exactly6 fixture model calls, no stored-fact rewrite, no delivery. This is offline
contract proof, not a second paid result. Ruff and mypy passed.

No legacy draft migration or further inference was performed. Existing pre-fix
unverified drafts need a new plan/fresh generation through supported flow; their
historical metadata/versions are not silently rewritten. New cloud cases use the
anchored context. The unused4 calls under the old ceiling are not authorization
for another run. Any cloud primary-flow smoke needs its own bounded documented
plan under the current checkpoint; deployment success and content verification
must be reported separately. M4 remains outside scope.
