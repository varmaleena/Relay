# Development application deployment execution

17 October 2026. User-approved reliability/deployed-demo checkpoint, not M4 or
production. This record is updated as checks actually run; pending steps are not
success claims. Reviewed scope: infra/plans/dev-application.review.json and
ADR0008. Existing INR1,000 planning target remains an alert target, not a cap.

## Applied foundation

- Enabled required Firestore/Firebase/Auth/Hosting/App Check/reCAPTCHA/Scheduler
  APIs. Initial Firestore listing failed during API propagation; later inventory
  was empty before creation.
- Created `(default)` Native Standard Firestore in `asia-south1`; described actual
  location and type afterward. No existing database was replaced or relocated.
- Linked Firebase to `work-511514`; registered the synthetic dev web app; enabled
  anonymous sign-in. Browser config stays under ignored `.local` until compiled
  as normal public Firebase web configuration. No developer token/key is shipped.
- Registered normal domain-restricted reCAPTCHA Enterprise App Check and enforced
  App Check on Firestore. No debug provider or fake-token cloud exception.
- Applied foundation SHA
  `66c2c096e5e1c94984e056a27ebb9045e1013197a47119a32f191410497d00f1`:
  dedicated API/worker/invoker identities; scoped data/model/signing/topic grants;
  separate private uniform-access Mumbai evidence/export buckets, exact Hosting
  CORS and seven-day lifecycle backstop; job and dead-letter topics.
- Deployed owner-isolation Firestore rules, then updated the release to deny
  expired, missing-expiry, deleting and deleted cases and child/version reads.
  New cases have an internal integer `accessExpiresAtMs`; public `ttlAt` remains
  ISO text. Do not enable native Firestore TTL on that string and assume cascade
  deletion. Bounded domain cleanup is separate from access denial.
- Created the harmless `__health/readiness` object in both private buckets.

An initial shell command incorrectly supplied two copy destinations; it failed
and was corrected to separate exact-object uploads. A removal probe for the
suspected misplaced health marker found no matching object. No case data was
involved. Initial reCAPTCHA CLI domain-list quoting was also corrected before
the successful single key creation.

## Build and release evidence

Application staging fingerprint:
`fe21ca5eaaa3ba9411f68ebcf2fba791254648588ddda8731247b34bc22d2db5`.
The allowlisted context contains 91 runtime/source/font files plus its manifest,
about 1.3 MiB uncompressed. It excludes credentials, source dossiers, tests,
emulators and developer state. All source hashes matched after staging.

Cloud Build `7f1376af-aa7e-4a7d-aa19-b9f4f78ff030`, Mumbai, uses the existing
dedicated `relay-dev-build` identity. Build submitted; success, immutable image
digests and actual Cloud Run release checks are pending at this entry.

## Engineering verification so far

- Main Python suite: 693 passed, seven skips, 86% combined coverage; package and
  service coverage gates passed. This predates the final provenance correction.
- Final packet-agent/service suite after that correction: 85 passed. It preserves
  extracted-evidence reference requirements and tests manual-confirmation anchors.
- Final settings/intake/runtime/readiness regression subset: 88 passed.
- Actual isolated Firestore/Storage rules: 52 passed, zero skips. Initial storage
  emulator setup/hub failures were resolved with an isolated paired hub.
- Ruff, full mypy/TypeScript and contract drift checks passed; three content
  checks passed with the main suite. Linux image execution remains to be verified.

## Actual hosted checks and hotfix

The user explicitly approved public HTTPS invocation of the API after automated
approval review required that specific authorization. Only the API received
allUsers/run.invoker; the worker policy contains only the job-invoker identity.
Firebase/App Check and owner checks remain inside the API boundary.

One-day preview: https://work-511514--relay-review-zamftmre.web.app.
Actual hosted auth/storage r2 passed seven checks: normal anonymous Auth/App Check,
missing credentials401, valid ID without App Check401, independent owner403,
exact-origin CORS, confirmed facts/reload and actual browser signed GCS PUT.
Both owned synthetic cases were deleted with204. No paid model actions occurred.
Artifacts: `.tmp/cloud-browser-auth-r2/result.json` and screenshots.

The actual private scheduled sweep returned204. The first real Pub/Sub terminal
fixture returned400 because Google includes documented duplicate snake_case
metadata fields. The fix accepts only those bounded known aliases and rejects
conflicts; 43 worker tests passed. No job payload validation was weakened.

Safe actual-model-call diagnostics were added without prompts, outputs, raw
errors, credentials or signed URLs. 150 focused logging/agent tests passed.
Cached build `21802734-f2cb-4df7-9590-96c100ec84ba` succeeded; stage fingerprint
`39004ddbc3aa052085e70925aef3295e6471b7ff67f6abea0e473109aef55026`.
API digest `sha256:626133ca99b053ed6455587399d3a76f1ad1a2d7cfa0e46e627cb82936b96156`;
worker digest `sha256:499577544b6312d58a32eeb02024417fc1634cd7cb0f0189e804c147d9101395`.
Tagged dependency probes passed before promotion to API00005-hef and worker00003-tov.
Service and revision scaling ceilings are one; min instances zero.

## Bounded hosted model-smoke plan

Under the approved checkpoint and existing budget target, run one fresh synthetic
case with the actual hosted browser/API/Firestore/queue/model pipeline. Permit
one intake turn, one explicit draft-plan request and one report-generation
request, no automatic UI retries or delivery. Manual canonical facts are entered
before the intake turn, so this is not an unbiased extraction-quality test.
The upload is a signed transport check; E7 extraction is intentionally not queued.

Existing implementation limits apply unchanged: intake at most two schema
attempts, classifier one; three recipients, at most three writer/verifier rounds
with one bounded packet transient retry per call. This gives a conservative
theoretical ceiling of39 upstream attempts for these actions; logical deadlines
can stop earlier. No new18-attempt claim is made for this separate cloud run.
Use safe model.call events to count observed calls in the test time window and
record any concurrent activity/ambiguity. Do not infer usage for failed calls or
claim a hard monetary cap. Stop on failed plan or bounded report timeout; retain
partial statuses and typed failures. Cleanup only this run's owned cases/jobs.

The full harness requires three VERIFIED reports with passed checks; three tabs
alone are not success. Export PDF bytes, reload and deletion are separate checks.
No provider result was recorded at that historical plan entry. N=one case/three correlated
reports cannot establish accuracy, impact or a production latency target.

Readiness probes do not perform model inference or verify queue delivery. They
label queue/model configuration separately from serving dependency reads.

## M4 rollout and corrective hosted check, 17 October

The first hosted full run produced three verified reports but failed its overall
gate: browser polling stopped after429 and PDF was never reached. The run is
preserved in `.tmp/cloud-browser-full-r1`. Worker model.call INFO logging was not
configured in that image, so its upstream attempt count is unknown. The API intake
record included a504; manual facts make this no extraction-quality benchmark.

M4 build `ec3f10a3-a238-4b73-bc22-7e2ba93d56da` succeeded from restricted110-file
stage fingerprint `c0a945cabbce16385150cfe16ce5345da97dffac829043fd26da22c0fed0c2e5`.
API00007-qus and worker00005-mog were probed before traffic promotion. The private
A2A00001-sdc permits only API/worker service identities as service-level invokers;
unauthenticated A2A/worker returned403, authenticated health and AgentCard200.
Seven hosted user/auth/storage checks passed again, with cleanup204 and no model
calls. Staff authentication succeeded, but the queue was temporarily unavailable
while its Firestore index was building; retain that failed gate until rerun passes.
Rules/indexes deployed successfully; index deployment does not mean READY.

The existing preview was updated and extended through20October. Bounded GET429
retries, revised report refresh and worker diagnostic initialization are included.
The source recovery-promise hardening and new voice/source code postdate this
snapshot and are not deployed in r3. Voice remains unavailable.

The user's existing authorization covers one corrective hosted full run under the same earlier39-attempt
theoretical ceiling and unchanged implementation timeouts: one intake, one plan,
one generation, no automatic mutation reruns or delivery. Preserve both outcomes;
test signed PDF, reload and deletion explicitly. This is an engineering regression
after a specific polling repair, not a replacement reliability dataset. A failed
run will not be rerun without a concrete diagnosed correction.

Actual corrective r2:17:11:32.450Z–17:13:12.674Z. Job reached succeeded; all three
reports NEEDS_HUMAN_REVIEW with16checks/onefailed, so full gate FAILED and PDF was
not attempted. Both owned cases deleted204. Eight observed SDK calls: intake and
classifier succeeded; packet writer three succeeded and three failed (two504,
one429). No VerifierAgent call was observed. API GET429 count zero, demonstrating
the repaired polling path for this run. Exact failed check IDs were not captured
before deletion; the harness now records them for future diagnosed runs. A
missing newly extracted victim-statement reference is under offline reproduction;
do not claim it as the proven cause of this historical run.

All11 deployed composite indexes subsequently became READY. Hosted staff sign-in
and authenticated/App Check-scoped empty queue then passed200, with zero inference.
Earlier staff failures remain in `.tmp/cloud-browser-auth-m4/staff-r2-failure.json`.

## Statement-provenance repair release r4

Offline reproduction produced the exact16-check/one-provenance-failure mechanism
for each recipient when a new unanchored caller identity follows manual facts.
Message ingestion now binds new statement leaves to the actual saved user turn in
the same transaction; confirmations and legacy unknown origins stay unchanged.
This proves a defect/repair, not the deleted historical r2 failed check identity.
See PACKET_STATIC_PROVENANCE_DIAGNOSIS.md. Five new and15 existing focused tests
passed. No verifier check was removed or downgraded.

Full offline run:960passed/oneOSsymlinkskip/oneobsoleteE19assertionfailed. The
assertion was corrected to distinguish malformed422 from valid-but-no-request409;
that full HTTP flow then passed in isolation. Application Ruff and mypy100files
passed. Later voice provenance/resource tests are separate overlapping runs.

Cached build `a4e97e47-8998-4a17-ae37-8fa0277aa3c6` succeeded from125-file stage
`75dfddd26eb2cf6e4973a9e9b5635d9fe2f7e71b3739e9f2fa11e66f84b0cba1`.
API00009-maz and worker00007-dex passed tagged dependency/private-denial checks
before promotion. Voice/source flags stay disabled. Live caption follow-up and
source-upload timeout postdate this snapshot and need a later build before use.

One further corrective hosted run is covered by the existing authorization after
this concrete reproduced repair, with the same three UI actions, bounded existing
SDK attempts, no delivery, and cleanup. Preserve failed check IDs this time.
No repeated inference without diagnosis; this is not a clean accuracy benchmark.

Actual r3:17:48:19.116Z–17:49:41.172Z. Full gate FAILED: generation job failed.
The final canonical list inspection was rate-limited (three API429s in the run),
so reportQuality=[] is unavailable inspection, NOT proof no drafts were stored.
Eight SDK calls observed: intake/classifier succeeded, two writer/verifier pairs
succeeded at transport, and another writer had two429s. Verifier transport success
does not prove packet verification; the cases were deleted204 before recovery.
The provenance repair allowed entailment calls in this window, but it does not
retroactively prove the historical r2 failing check. No PDF was attempted.

The harness now honors Retry-After on bounded safe final GETs, records terminal
job error/progress and failed check IDs, and can check a verified partial report's
PDF while retaining strict full-gate failure. Packet429 backoff is changed from2s
to8–10s jitter, still at most two upstream attempts and35s overall; other transient
backoffs remain2s. Nine targeted retry/cancellation checks pass. This is a proposed
capacity mitigation, not a measured reliability improvement, and postdates r4.
Official guidance recommends smoothing/retrying capacity failures:
https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429 .
No further live full run is scheduled here. The next check isolates PDF transport
with explicitly synthetic model fixtures; it cannot establish live AI quality.
