# Deadline completion plan

Audit snapshot: 17 October 2026, 22:17 IST (16:47 UTC). User target: finish by
18 October 2026 midnight IST, interpreted as the end of 18 October. Approximately
25 hours 43 minutes remained at this snapshot; this is a scheduling window, not
an estimate that the outstanding work will fit. The competition dashboard's exact
cutoff/time zone and the team's registration/eligibility remain privately
unverified. An earlier official cutoff must take precedence.

The user authorized continuing the remaining phases on 17 October. Earlier
“awaiting M0/M4 approval” text in historical planning files is superseded for
routine implementation. Source review, actual human review, institution contact,
submission/publication and cloud permission boundaries remain distinct. This
read-only audit made no cloud/model requests and changed only this document.

## Evidence and current state

This plan retains T26–T43 from BUILD_SPEC §18.8 and milestones M5–M10 from §11.1.
Read alongside §§5.2,5.10–5.15,7,8.6–8.8,9,12,14.3,15.3–15.5,16–18 and the
original preserved attachments; it does not replace them. Original requirements
and source hashes remain in `docs/sources/`, `SOURCE_MANIFEST.json` and
`TASK_TRACEABILITY.md`. Contracts describe intended interfaces; they do not prove
that every endpoint executes.

Inspected implementation evidence:

- M0–M3: actual text/evidence/classification/planning/packet services, schemas,
  deterministic planner/verifier, ReportLab English/Hindi exports, local registered
  MCP mocks, durable per-recipient progress, version-bound approval/outbox and
  deletion. Historical reliability failures remain open: classification live smoke
  14/20 typology and 15/20 authorization; packet batches 1/3,0/3,2/3 verified;
  composed three-packet fixtures are from mixed runs. Fresh durable primary-flow
  measurement used 14 real calls and produced zero verified packets before the
  narrow confirmed-provenance repair. Offline repair tests passed; this does not
  turn the frozen live result into success.
- Cloud: `DEV_DEPLOYMENT_EXECUTION.md` records deployed API/worker/Firebase preview,
  normal Firebase Auth/App Check, seven actual browser/security/storage checks,
  private worker sweep, queue alias correction and model-call logging. These are
  separate from a successful hosted three-verified-packet run. Consult root's latest
  cloud smoke evidence before claiming the latter; this audit did not rerun it.
- M4: receiver projection/service/console, constrained ReceiverBriefAgent and local
  needs-info loop are implemented. E19 creates a new draft, re-verifies, and needs
  fresh E17 approval. Actual registered MCP hold, bridge preflight and local
  receiver/victim audit mirroring have synthetic integration evidence. A2A SDK
  service files/tests are present and being integrated concurrently; deployed
  authenticated A2A interoperability is not established by file existence.
- M5+: no `services/live_gateway`, live intake agent or browser audio worklet was
  present at this snapshot; the home screen's voice action is disabled. There are
  only India/generic draft YAML packs, no UK/fourth pack. No Pack Studio, Eval Lab,
  Demo Control or Present Mode implementation was found. `eval/` and `present/`
  directories are absent. BigQuery entity/evaluation DDL exists; a linking system
  does not. `scripts/tasks.py` still fails explicitly for synth/eval/report/
  preflight and several deployment/operator targets. Existing contract models,
  source snapshots and API catalog are foundations, not completed features.
- CI has lint/types/build/tests/contract drift, selected emulator rules and intake
  integration checks. It does not yet establish the complete authorization matrix,
  all UC desktop/mobile tests, all-service deployment, load/resilience targets,
  full synthetic evaluation or external comprehension tests.
- Hindi review log explicitly remains machine/engineering drafted, pending a fluent
  reader. India/generic draft status is intentional; no human legal/source signoff
  or publication is inferred.

## Exact remaining task register

Status means implementation at this snapshot, not a prediction. Each row stays in
the completion ledger if time expires. Changes must retain schema-first contracts,
English/Hindi UI, audit, typed outputs, authorization and synthetic-only fixtures.

| ID / deps | Remaining implementation | Acceptance and real/simulated boundary |
|---|---|---|
| **T26 / T12,T09** M5 | Implement Live gateway, IntakeLiveAgent, four fast tools, browser capture/playback AudioWorklets, captions, mute/end, interruption and resume. Resolve actual configured model/backend support first; installed `AsyncLive.connect` is only SDK evidence. | Real authenticated English/Hindi spoken input produces confirmed facts comparable to text; first-action warning first turn; minimum facts enqueue exactly once. First-frame Auth+App Check within5s, owner binding, PCM16 input16kHz/output24kHz verified against chosen model, bounded frame sizes, heartbeat20s/two misses, max600s, three sessions/user, safe resume max3 backoffs and visible text fallback. Measure first-reply p95<3s with n; never claim it from a single clip. |
| **T27 / T26** M5 | Extend existing text distress detection to voice/tool/caption flow; stop collection and deadline pressure, preserve saved case, verified support-only resource lookup and safe emergency/trusted-person fallback. Implement injection classifier where required and test streamed output safety design. | EN/HI/Hinglish distress cases stop questions/tools and persist flag/audit; no invented hotline or clinical advice. Demonstrate cancellation/interruption and secrets volunteered aloud. Raw audio cannot be called safe-before-play merely because a later transcript filter passed; record the actual buffering/gating experiment and residual risk. |
| **T28 / T18** M6 | Author UK reference/gold pack from current official instruments, including scope, exceptions, reporting channels, forms, source passages/review records; add explicit country-switch UX with invalidation. | Same facts under explicit India/UK selection produce appropriate differing recipients/order/forms/deadlines/language with resolvable source refs. Never apply unauthorized rules to authorized manipulation. Draft preview remains visibly unverified; production publication needs real named review. No current UK phone/window is guessed from prior notes. |
| **T29 / T04** M6 | Implement E29–E31 source upload/URL ingestion, immutable raw snapshot/hash and bounded passage index. | Reviewer-only; allowed domains, HTTPS/port policy, DNS and every redirect checked against private/loopback/link-local/metadata targets; rebinding-resistant transport;25MB cap, MIME PDF/HTML/text, PDF/parser limits, scripts stripped, no active rendering. Passage IDs/page/offset/hash resolve. Vertex Search is optional only after residency/cost decision; deterministic passage index is the permitted fallback. |
| **T30 / T29** M6 | Implement PackBuilder five separate structured passes and Critic, durable jobs/progress, E32–E36 review/edit/publish/retire. | Real configured Gemini extracts only supported items with passage IDs and evidence offsets, separately judges SUPPORTED/PARTIAL/UNSUPPORTED/CONTRADICTED, preserves conflicts/ambiguity; never invents recipients/windows/remedies. Publish requires authenticated human decision and complete review; accepted unsupported items stay unverified. Immutable versions and explicit retire; no model self-signoff. |
| **T31 / T30** M6 | S9 five-step Studio, split source passage/rule view, verdicts, Accept/Edit/Reject, version diff, review identity and publish gate. | Reviewer/admin actions enforce server roles; all source/rule links work; unverified items visible; keyboard/English/Hindi UI, no raw debug. Actual human review is recorded, not simulated by the agent. |
| **T32 / T30,T17** M6 | PackBuilder gold comparison by field type, false accepts/critic counts; choose fourth regulator source and pre-build same-source fallback. | Live-built fourth pack actually extracted, reviewed and used for a case; measured precision/recall/F1 with n/CI vs independently reviewed gold. Hold out its cases until built. Rehearsal fallback labelled replay/pre-built and never represented as live construction. Source/reviewer selection requires real people. |
| **T33 / T14** M7 | Normalize entity roles, HMAC via Secret Manager, sightings/denylist/link/cluster computation in BigQuery/worker, ClusterExplainerAgent. | No raw identifiers in BQ/logs. Exclude amount/reference/time/currency/bank/app/claimed identity and official-channel denylist. Use specified type weights/time factors, possible>=.60/likely>=.85, cap.99 and components>=3; seeded six-case ring recovered with negative controls and measured n/CI. Explanation2–4 sentences uses types/counts/time/case refs only and human-confirmation warning; no claim of criminal-network detection. Delete removes sightings and derived links/clusters. |
| **T34 / T33,T24** M7 | Receiver S8 related-case panel and E25/E26 related/not-related validation. | Only authorized recipient-scoped linked projections, no cross-org victim disclosure; case/type pointers and confidence shown as possible links; explicit human decision/audit, replay safe. “Six reports” is a seeded synthetic ring, not six real victims. |
| **T35 / T19,T17,T28** M8 | Versioned synthetic generator/ScammerSim and Playwright fake-app screenshot templates, gold records and dataset card; target>=300 cases across three reference plus held-out live-built pack. | EN/HI/Hinglish,11 typologies,four authorization types,noise/missing/conflicts,crops,transcript subset; fictional banks/apps only. Gold tuple roles and recipients/fields correct; random10% plausibility review by a person recorded. Dataset version/hash, generator/model/prompt, split/leakage/limits documented. True-audio eval is optional, voice product is not. |
| **T36 / T35** M8 | Fair GuidanceBaseline same model/facts/budget, Rules/NoVerifier/NoPack ablations, fixed parser/judge prompts, red-team>=40, metrics and confidence intervals, repeat nondeterministic systems>=3/case. | Entity microF1,typology/authorization/confusion,recipient precision/recall/order,deadline correctness,completeness,faithfulness/citation validity,forbidden/injection rates,latency/cost,PackBuilder precision/recall/F1. Wilson proportion CIs/bootstrap F1; retain timeouts/missing usage in denominator, no imputation of success. Independent100-sample human faithfulness audit;20random paired baseline outputs. Full evaluation needs a separately measured cost/attempt plan; do not launch thousands of calls under an assumed INR1000 hard cap. |
| **T37 / T36** M8 | Eval Lab S10,E37–E40, reports/export, slice/failure gallery, bounded admin smoke run and working make eval/report/redteam targets. | Every displayed result has system,dataset version,date,n,95%CI,model/prompt/build identity; distinguish offline vs live. Baseline/ablation columns present with “not measured” rather than fake zeros. Public demo read-only; execution admin-only; failures scrubbed synthetic-only. make eval full produces actual report; UI alone does not satisfy evaluation. |
| **T38 / T13,T21,T24** M9 | Complete axe/contrast/jargon/parity checks on every new route; manual keyboard/screen-reader/200%zoom/reduced-motion checks and fluent Hindi review. | WCAG2.2AA target: no serious/critical axe issues, semantic landmarks/live regions/captions,48px victim targets, visible focus, errors linked inputs. Real Hindi reader logged across victim copy/captions; code key parity is not human review. Existing mocked screenshots are not hosted usability evidence. |
| **T39 / T24,T25** M9 | Complete role×E1–E44 matrix, all new contract/emulator/e2e tests, scans, load and fault/resilience tests; CI gates. | Cross-owner/org/admin misuse,stale/duplicate/version/delete race/expiry,SSRF and source injection; retries bounded/no duplicate sends. k6:50victims,10voice,5builders,ramp2min+hold5min,error<1%,backlog<=60s,noOOM,p95 reported. Given current single-instance/concurrency/model budget, first separate fake-provider infrastructure load from billable-model load; neither proves the other. No quota increase or large model load implicit in local test authorization. |
| **T40 / T23** M9 | Admin/demo-only S11,E41–E43,idempotent seed/reset/scenario loading, mock behaviors,timer speed,readiness and preflight command; operator/demo accounts/runbook. | Never reset other user's cases or enable controls with DEMO_MODE=false; four scenarios plus six-case ring and actual measured eval fixture. Cache mode explicitly REPLAY; live path works separately. Preflight checks services/models/config/seed/MCP/Live reply/eval report; separate cheap readiness from a budgeted inference probe. Generated passwords live in secrets, not repo/logs; judge credentials shared through approved submission mechanism. |
| **T41 / T24,T26,T40** M9b | S12 split real victim+receiver Firebase apps/in-memory identities, five-stage Flow Rail, deterministic narration/scenes/operator panel, last6step strip, captions/English translation. | Two genuine scoped sessions follow the same approved delivery; LIVE/REPLAY badge always accurate. Hindi live transcript plus labelled English translation preserving identifiers; no screenshot/replay passed as live. Controls cover text fallback,language,country,scenarios,mock behavior; rehearsal from clean reset under3min screen time, no raw data/blank states. |
| **T42 / T41** M9b | Recruit three outsiders, run five-second tests on S1,S2,S4,S5,S6,S7,S12 and silent final-video test; fluent Hindi captions/manual accessibility. | >=2/3 correctly state purpose+next click on each screen;>=2/3 correctly describe five-stage silent flow. Record consented observations/date/failures, fix and retest. Agents/browser tests cannot fabricate participants or results. |
| **T43 / T37,T42** M10 | <3min1080p captioned live demo,~14slideEnglish deck PDF,README/architecture/runbook/security/dataset docs,dated manual baseline log,repo/license/secret-history cleanup,submission URLs. | Functioning Google Cloud URL/phone+clean-browser check,actual live section,public accessible video/repo/deck,BFSI,eligibility/team/cutoff verified by human. All figures match exact reports; safety/replay/institution simulation explicit. Three takes where feasible, no edits hiding systemic failures. No invented external baseline transcripts,legal signoff,testimonials,impact/time savings or selection probability. |

## Execution order through the deadline

Use parallel ownership with one contract/integration owner. These are work windows
and stopping points, not promised completion durations. Preserve runnable artifacts
and test evidence at each increment; keep the latest passing deployed revision.

| IST window | Integration lane | Independent work that can proceed |
|---|---|---|
| 17Oct22:20–18Oct01:00 | Close current M4/A2A/needs-info API+UI regression, hosted primary-flow measurement and deployment/rollback evidence. Resolve Live model capability blocker with a tiny explicitly capped probe if authorized. | Implement T26 gateway/state/audio contracts with fake provider tests; T29 secure source ingestion; T35 dataset/gold scaffolding; start README/deck outline and arrange actual reviewers/outsider slots. |
| 18Oct01:00–07:00 | Integrate T26/T27 authentic voice slice and text fallback. In parallel integrate T28/T29→T30 builder/critic/review state. | T33 deterministic HMAC/linking and tests; T36 metric/report framework and fixed baselines; T40 admin seed/reset/preflight. Human source selection/review starts as soon as concrete passage/rule artifacts exist. |
| 18Oct07:00–13:00 | Integrate Studio/live fourth-pack path and UK switch; integrate linked-case panel. Freeze dataset/gold before any headline run. | T37 Eval Lab consumes actual report schema; T41 dual-session presentation and narration; T38/T39 new-route security/accessibility/regressions. Run only explicitly bounded measured model batches with all failures retained. |
| 18Oct13:00–18:00 | Release candidate: end-to-end desktop/mobile, isolated roles, hosted voice/text,source review/publish,fourth pack,full loop and preflight. Freeze numbers/assets. | Real Hindi/source reviews and T42 outsider tests; fix comprehension failures; complete report/failure gallery/runbook and script outline. Record unresolved targets honestly. |
| 18Oct18:00–21:30 | Capture actual live takes, build/render/check deck PDF and captioned video; verify public links from a clean browser/phone. | Final dependency/secret scans and regression checks for fixes only; finalize README,architecture,baseline limitations/results appendix and controlled demo credentials. |
| 18Oct21:30–23:00 | Submission packaging/buffer; confirm dashboard fields/team/theme/URLs. Prefer this over using the last minute for feature changes. | Correct broken links/caption/asset mistakes; preserve deployed rollback and synthetic reset path. |
| 18Oct23:00–cutoff | Reserved upload/link/access buffer; human submits and confirms receipt before the actual dashboard cutoff. | No assumption that midnight submission succeeds; no automated submission without explicit authorization. |

At each window boundary publish actual completed/tested/deployed items and open
gates. Do not reset failed model metrics to make the schedule look complete. If
critical work slips, preserve it as open and continue the strongest truthful
submission path; the table is not permission to silently omit later tasks.

## Minimum submission path and claim discipline

The shortest defensible package is a working hosted primary journey plus deployed
URL, public repository, English explanatory deck and strictly-under-three-minute
captioned video, with exact current limitations and real measurements. A partial
submission can be prepared if necessary, but it does not satisfy the full build
specification and must not be called “all phases complete.” Technical eligibility
and competitive quality are separate from completeness.

The minimum full-spec demo path still includes: authentic EN/HI voice/text and
multimodal evidence; confirmed facts→cited plan→three verified recipient reports;
explicit victim send; scoped simulated receiver decision/needs-info loop; UK
switch; fourth pack built live from official passages with real human review;
seeded possible links; Eval Lab with baseline/ablations,n/CI; Present Mode and
comprehension evidence; clean preflight and submission assets. Those are acceptance
gates, not existing achievements. No financial recovery is demonstrated by any
simulated ticket/hold.

Only the specification's explicit cut list is available, in order: third language,
true-audio evaluation, Terraform, DLP integration, keyboard shortcuts, additional
PDF styling, cluster graph visualization. EN/HI product voice, underlying linking,
source review,verifier,citations/provenance,simulation labels,human approvals,
Eval Lab with n/CI and live-built-pack moment remain required. Cutting a graph
means keep an accessible linked-case list; cutting PDF styling does not remove
working bilingual export. Any additional deferral must be explicitly recorded as
an unmet requirement, never erased from traceability.

## Recommended next independent coding slice

Assign **T26A: authenticated Live gateway protocol and thin tool boundary** as the
next isolated slice, while T29 source ingestion runs independently. Suggested
ownership: `services/live_gateway/**`, new `agents/live/**`, focused protocol tests;
coordinate common Settings and frontend AudioWorklet contracts with their owners.

First deliver the fake-provider transport proof: first-frame Firebase/App Check
verification, case owner/session binding, bounded JSON/binary/audio frames,
heartbeat/timeout/session caps, cancellation/end/mute, opaque owner-bound resumption
state, safe errors/logs, four deterministic tool adapters and exactly-once
processing request. No provider secrets/audio/transcripts in logs and no audio
storage by default. Heavy extraction/planning never runs inside a Live tool.
Use existing server-owned fact validation; a model cannot set confirmed provenance
or approve/send. Typed schemas/state tests precede a browser microphone and one
measured capability smoke. Keep voice disabled with a clear text fallback until
actual configured model access and capture/playback are demonstrated.

Live capability/region/model-specific parameters require current primary-source
verification at implementation time. The local catalog did not establish a Live
model entitlement, and legacy2.x models are disallowed by this project. Do not
hardcode a guessed3.x Live model or replace Gemini Live silently with browser
speech recognition. Safety-before-play is a measured design question: document
what buffering/transcript alignment actually guarantees and what it cannot.

## Critical risks and decision records to keep current

1. **Provider reliability and cost:** real429/499/504/timeouts and missed latency
   targets already exist. Bounded retries and durable progress improve recovery,
   not capacity. Count actual attempts including retries; record reasoning usage
   where supplied and missing failed-call usage honestly. INR1000 is a planning
   target, not a billing-enforced cap. Full300×five systems×three repeats can be
   thousands of calls before per-recipient writer/verifier overhead; compute an
   explicit budget before execution and report a smaller measured run as smaller.
2. **Source and language truth:** no published reference packs or human Hindi
   review currently proven. Agents can assemble review artifacts immediately;
   they cannot sign for a reviewer. Generic/India draft preview remains distinct
   from reviewed production routing. Resolve required-unavailable field warning
   semantics from §18.1 explicitly: current required checks can still block;
   optional unavailable answers have tested support, not universal waiver.
3. **Cloud topology versus local capability:** current mocks use registered MCP
   tools in-process. This is real SDK invocation but does not satisfy deployed
   streamable-HTTP private bank/rail service interoperability by itself. A2A files
   do not establish network IAM or deployed handoff. Live,BigQuery,source/pack
   storage,monitoring/OTel,cost metering and eval jobs need actual evidence.
4. **Trust boundaries under concurrency:** new worker jobs,resume handles,
   publications,receiver requests and links must preserve actor/org/version/hash,
   deletion,TTL and catalog proofs. No bypassing App Check/IAM to make the demo
   easier; no caches labelled LIVE. Private worker/A2A and server IAM differ from
   client Firebase rules.
5. **Human time and recording:** external participants,fluent Hindi review,
   regulator/source review,counsel/workflow/name checks,eligibility and final
   submission require real people. Arrange these now around concrete artifacts,
   not after coding ends. A failed human test remains failed until retested.
6. **Release reliability:** versioned preview URLs can expire, demo credentials
   can be unavailable,public repo/video links can be private,and new cloud
   revisions may omit later local code. Freeze a release manifest/source hash,
   tested config,actual URLs and rollback before recording; verify each again
   before submitting.

No unit test pass is a human usability result; no model catalog entry is a Live
session; no demo dataset is a population impact study; no source citation is a
reviewer's signature. Report exact achieved scope at the deadline.
