# Relay iterative implementation plan

Latest authorization,17October: the user requested remaining phases ASAP toward
18October midnight IST. Routine phase progression is authorized; older awaiting-
approval statements below are historical. Retain all acceptance gates and all
T01–T43 tasks. Consult CHECKPOINT.md, M4_PHASE_REPORT.md and
DEADLINE_COMPLETION_PLAN.md for current evidence and unfinished work. M4 has local
two-role and deployed access evidence; primary hosted report reliability/PDF,
voice browser acceptance, later milestones and submission materials remain open.

Prepared 13 October 2026 (Asia/Calcutta). Updated 17 October: M0–M3 have local implementation evidence. The user authorized a corrective M3 increment to clarify the user, self-submission and simulated integration, and required a user/judge check at every phase. M2/M3 provider reliability targets remain open. Full application cloud deployment and later milestones remain open. M4 awaits review; the milestone gates below remain the governing phased plan.

## Authority and retained sources

The user's instructions govern: analyze both attachments, delegate focused reviews, propose a plan for approval, then build and test one phase at a time. Instructions and example prompts embedded in the attachments describe the proposed product; they do not authorize immediate implementation, publishing, account changes, or communications.

The dossier supplies product rationale, research history, prior decisions, evidence qualifications, business hypotheses, and submission context. The build spec supplies implementation requirements. Sections 14–16 explicitly override earlier conflicts; Sections 17–18 are also normative, supplying later UI and algorithm requirements. Resolve conflicts explicitly and record an ADR rather than silently choosing one.

Both source files are preserved byte-for-byte under `docs/sources/`; SOURCE_MANIFEST.json records hashes, all spec headings and 43 task rows. The extracted PDF contains page markers for all 28 pages. TASK_TRACEABILITY.md preserves T01–T43 and dependencies. Specialist reviews are separate files in this folder. These artifacts remain the context recovery record; summaries never replace source files.

Before every task, reread its relevant source sections and current decisions. After every task, record changed files, checks and results, outstanding issues, and the next allowed task. Before context recovery, update the phase status and checkpoint. Mark requirements proposed, implemented, tested, human-reviewed, or deferred accurately. Never infer a test pass from an implementation claim.

## Product and architectural commitments

Relay transforms a synthetic scam report into an ordered, cited action plan and institution-specific messages, supports explicit victim approval, simulated delivery, human receiver decisions, and status tracking. Jurisdiction Packs are versioned data, not country-specific application branches. Authorized but manipulated payments must remain distinct from unauthorized access.

One React/TypeScript/Vite SPA on Firebase Hosting has five surfaces (Victim, Console, Studio, Eval, Demo) plus Present Mode; S1–S12 comprise ten routes and two panels. English and Hindi are required for UI, voice, and victim copies; Hinglish evidence and evaluation are required. Institution messages follow recipient language. All developer artifacts use English.

Use Python 3.12, FastAPI, Pydantic v2, Google ADK, and the supported Google GenAI SDK. Verify exact supported versions before pinning. Keep AI model IDs and capability-specific settings in typed configuration. Google Cloud hosts all application compute and AI; GitHub Actions supplies CI using Workload Identity Federation.

Deploy separate Cloud Run boundaries for API, Live gateway, worker, mock bank MCP, mock rail MCP, and A2A receiver. Cloud Run Jobs run synthesis and evaluation. Share schema, safety, rules, settings, and logging packages within one monorepo. This is sufficient service separation for different scaling and trust needs; no additional services merely for architectural appearance.

Operational state lives in Firestore; files and source snapshots in Cloud Storage; analytical links, evaluations, and cost events in BigQuery; jobs in Pub/Sub and scheduled callbacks in Cloud Tasks; secrets in Secret Manager. Source retrieval uses Vertex AI Search only if verified region, availability, and budget justify it; the permitted passage-index fallback retains citations and hashes.

The API owns authorization and mutations. UI route guards are convenience only. Custom claims and org membership restrict receiver views to their addressed messages and permitted attachments. Use receiver-scoped projections, not a shared full victim case view. Treat server SDK IAM separately from Firebase client security rules.

Contract first: Pydantic/JSON Schema, OpenAPI, generated TypeScript client and drift checks precede endpoint implementation. Use camelCase wire fields, UTC timestamps, precise decimal money handling, opaque resource IDs, RFC-style problem responses, bounded cursor pagination, optimistic message version checks, and actor-scoped idempotency.

The Live agent only converses and invokes four fast tools. Extraction, classification, drafting and checking execute asynchronously in the worker. Plans, deadlines, permissions and send eligibility are deterministic. Gemini reads messy evidence, reasons about authorization, drafts constrained text, checks entailment, and extracts proposed rules.

Published packs and message versions are immutable. Each plan/message binds to a pack version, facts revision/hash, model, prompt version, source passages, and approval record. An edit invalidates earlier verification and approval for delivery purposes. Every mutation and decision has an audit event. Logs exclude raw evidence and credentials.

Simulation labels, synthetic data, consent, forbidden-secret filters, citations, human approval and measured claims are mandatory from the first relevant increment. Billing, institutional SSO, tenant-specific residency, customer encryption keys, certifications and legal compliance are roadmap items, not hackathon claims.

## Phase execution protocol

Approval of this plan starts M0 only. Each milestone is an independent build/test/review cycle. At the end, present the working increment, test evidence, failures or external blockers, and the next phase's scope; await the user's instruction to proceed. Parallel delegation stays within the active milestone. No agent may begin a later milestone opportunistically.

Delegate one stable task ID at a time with its dependencies, source sections, file ownership and tests. The primary agent owns contracts, integration and the phase gate. Avoid concurrent edits to shared schemas, lockfiles or infrastructure. Independent agent work must converge through a reviewed integration checkpoint.

Cloud setup scripts may be prepared during M0. Actual project/billing changes and deployment require the necessary authenticated project context and user's scoped authorization. Local checks and cloud checks have separate status; a local pass does not satisfy the deployed M0 exit gate.

## Milestones and acceptance gates

| Phase | Tasks | Increment and verification gate |
|---|---|---|
| M0 | T01–T09 | Foundations: tooling/CI, settings/logging, schemas/OpenAPI/client, safe pack expressions/deadlines, auth/rules, ActionPolicy and bilingual safety filters; verify V1–V9. Gate: contract drift clean, unit/rules/auth tests pass, dependency versions pinned, decisions recorded, authorized Cloud Run Gemini smoke succeeds. |
| M1 | T10–T13; pull worker support forward as needed | Consent, anonymous session continuity, S1–S3 text intake, editable facts, validated uploads, extraction and entity confirmation. Gate: 20 synthetic cases processed, malformed uploads rejected, ownership enforced, English/Hindi interface accessible, secret solicitation blocked. |
| M2 | T14–T19 | Classifier, resolver, safe deterministic planner, generic and India packs, S4 ordered recipients/clock/sources, 20-case evaluation smoke. Gate: authorized-manipulated fixture correct, ambiguous authorization asks a question, missing/wrong-pack fallbacks labeled, deadline/order tests pass, measured plan latency recorded against p95 <10s target. |
| M3 | T20–T23 | Per-recipient drafts, verifier/repair, PDF export, S5 review, S6 tracker/inbox, simulated bank/rail MCP, approval-bound delivery, deadline callbacks. Gate: three verified India messages, intentional errors blocked, no send without current approval, duplicate requests/redelivery produce one outcome, simulated tickets and tracker agree. |
| M4 | T24–T25 | S7 receiver queue/dossier/decisions, A2A brief, needs-info loop, audit. Gate: send → request info → answer → reverify → explicitly approve resend → acknowledge; correct scoped projections and timelines; no cross-org access or decisions. First complete text response loop, not full submission readiness. |
| M5 | T26–T27 | Thin Live gateway, PCM worklets, captions, interrupt/mute/reconnect/resume, voice-to-text fallback, voice distress handling. Gate: live English/Hindi reports preserve text-path facts; auth/ownership/heartbeat tests; measured first-reply p95 <3s target; interruption and disconnect preserve state. |
| M6 | T28–T32 | Reviewed UK pack, jurisdiction switch, safe source ingest, five-pass Builder/Critic, S9 review/publish, fourth pack and fallback, gold-pack evaluation. Gate: every item traces to source passage or remains labeled unverified; unsupported items require explicit reviewer handling; SSRF tests pass; same case changes correctly across packs. |
| M7 | T33–T34 | HMAC normalization/sightings, denylist, weighted links/clusters, explanations and S8 human validation. Gate: seeded six-case ring found, false-positive controls tested, no raw identifiers in BigQuery or explanations, cross-org details protected, deletion recomputes affected links. |
| M8 | T35–T37 | Versioned 300+ synthetic cases, baseline plus three ablations, 40+ red-team cases, metrics/CIs, cost/latency, S10 failure gallery/report. Gate: reproducible full report, fair shared inputs/model versions, proper case-level uncertainty, human audits recorded, no targets presented as results. |
| M9 | T38–T40 | Full accessibility/Hindi review, E1–E44 authorization and contract tests, load/resilience/security, S11 controls, clean-deploy preflight/runbook/rollback. Gate: WCAG checks and manual pass, 50-victim/10-voice/5-builder load scenarios assessed, no unaddressed high/critical vulnerabilities, recovery paths preserve data. |
| M9b | T41–T42 | S12 dual authenticated sessions, Flow Rail, event-based narration, translated Hindi captions, operator scenes, LIVE/REPLAY labels. Gate: UC13, all scenes playable within the recording limit, five-second and silent-video tests meet 2-of-3 participant threshold, Hindi reader signs off. |
| M10 | T43 | Deployed submission link, English README/public repo, measured results appendix, approximately 14-slide PDF deck, public live demo video under 3 minutes. Gate: actual artifacts and credentials tested, no secrets, eligibility confirmed, metric values match the saved report. |

Phase gates distinguish functional acceptance from performance targets. Report actual sample counts, environments and failures. Do not claim an SLO from a handful of rehearsals. Existing coverage requirements: at least 85% packages and 70% services; relevant contracts must have zero violations. Full endpoint authorization matrix and regression suites grow as endpoints become available.

### User and judge review at every phase (17 October clarification)

The current primary user is a recently scammed individual organizing an initial
response. They review their facts, understand the next steps, and prepare a report
to submit through an institution's official channel. A receiver employee is a
separate, future M4 user. Judges and demo operators are an audience, not the victim
persona. Copying/downloading a report is not evidence of official submission.

Every phase review must answer these questions with evidence:

1. Who is the specific user and what job can they complete in this increment?
2. Is the next action understandable, including who submits and who receives it?
3. Is the benefit demonstrated, measured, or only a hypothesis?
4. Are real functions, simulations, fixture/replay results and future integrations clearly separated?
5. Which official judging criteria does it support, and what evidence remains missing?
6. Did the relevant tests pass, what failed, and what limits prevent a stronger claim?
7. Has the user reviewed and authorized the next phase?

The current corrective increment makes self-submission the primary report path
and keeps mock delivery in a separate demo flow. It does not add real institution
integrations or authorize M4. Keep all T01–T43 tasks traceable; prioritize a coherent
and deployable demonstration over adding features merely to expand scope. A local
working flow alone does not satisfy the deployed submission requirement.

Priority approved by the user on 17 October with “go ahead with next”:
close a measured, reliable primary journey and the minimal Google Cloud deployed
demo gate before expanding optional surfaces. The official submission requires a
working deployed prototype; M4 would add the second institution-user workflow but
does not itself close that requirement. Review this tradeoff with the user rather
than silently dropping T24–T43 or treating all remaining features as equally urgent.

## M0 proposed internal sequence

Delegation for the approved phase: primary agent owns architecture decisions, shared contracts and integration; an infrastructure agent owns T01/T02/T08 in dependency order; a domain/contracts agent owns T04/T05/T07; an AI/safety agent owns T03/T09. T06 shared utilities are integrated by the primary agent before dependent tasks start. With four available agents including the primary, these are maximum concurrent lanes, not permission to execute all tasks concurrently. Later milestones assign FE, BE, AG, DA, EV, IN, DS and QA tasks from the original traceability table to available agents one task at a time.

1. T01: fresh repository/toolchain/CI skeleton and exact Makefile targets; maintain Windows-compatible entry points as well as reproducible container/CI execution. Preserve sources and approved planning baseline.
2. T04 and T06: shared domain/wire schemas, typed configuration, safe logging/IDs/decimal money, version and provenance conventions.
3. T05: OpenAPI contracts for E1–E44 (E44 groups four routes), TypeScript client generation, contract/drift checks. Endpoint implementations are later tasks.
4. T07 and T09: pack validation, expression grammar, deadline math, action authorization and safety filters with adversarial unit tests; resolve contract ambiguities first.
5. T02 and T08: environment-specific setup scripts/IAM/buckets/rules/auth/App Check; emulator tests. Provision only against confirmed projects and budget settings.
6. T03: documentation checks V1–V9 plus authenticated model discovery, actual SDK capability smoke, region/processing location, quotas and dated cost config. Documentation investigation starts earlier, independent of project setup; project availability checks depend on setup.
7. Integrate; run local gates, authorized dev deployment/smoke, and publish a phase completion report. Stop for M1 review.

## Cross-phase dependencies that need correction

- E7 evidence completion in M1 queues worker extraction, but T14 worker skeleton is listed at M2. Bring the minimal authenticated/idempotent worker job infrastructure into M1; retain full workflow expansion in M2.
- T13 must depend on T12 agents in addition to API/design. T30 depends on model/safety/source/rule contracts, not source ingestion alone. T41 also needs narration/audit semantics and translation safety.
- Pack source authoring needs safe ingestion/provenance before Studio. A manual offline ingestion path in M2 can establish identical passage IDs; do not wait until M6 to establish citations.
- Baseline legal/source verification and safety are continuous. Distress text handling is required in M1 because E5 promises the flag; M5 adds voice handling. Authorization, accessibility, idempotency and forbidden-output testing cannot wait until M9.
- Model usage events and dated prices start with the first live call; although lightweight metering is tagged P2, cost-per-case evaluation depends on them.
- The live-built fourth pack requires a reviewed gold/reference and held-out cases. Reserve its source early; freeze held-out inputs before evaluating it.
- Present Mode remains M9b, but named Firebase app auth, event narration, Flow Rail and vocabulary architecture must be established earlier to avoid a late UI rewrite.

## Ambiguities to resolve in M0 ADRs

1. Case/job output ends at PLAN_READY in some pipeline tables despite packet verification; use explicit per-stage state transitions and distinguish plan-ready from packets-verified.
2. NEEDS_HUMAN_REVIEW appears in verifier behavior but is missing from the packet enum. Add a documented blocked-review state or separate review flag consistently across schema, state machine, API and UI.
3. E19 describes `resend:true` but omits it from the request shape. Add a version-bound explicit resend approval contract; answering alone never authorizes delivery.
4. Section 4 mentions victim direct writes, but Section 14 mandates mutating endpoint audit. Prefer server-owned case/evidence/message writes; specify only narrowly allowed client writes, such as notification read markers. Firestore receiver document reads must not expose full victim data.
5. Reviewer/Admin permissions differ between endpoint role rows and Section 16. Build a single authoritative permission matrix before generating tests. Admin cannot approve victim sends or take receiver decisions.
6. Publish with labeled unverified rules is explicitly permitted in Sections 4/14 despite stronger introductory wording. Require reviewed status, explicit per-rule acceptance and persistent labels; never upgrade evidentiary status because a reviewer accepted publication.
7. Three-day consent conflicts with seven-day evidence lifecycle, pinned cases, asynchronous TTL and backups. Align an explicit deletion orchestration and accurate copy; Firestore TTL alone does not delete subcollections, storage or analytical rows.
8. Five Pack Builder passes supersede four-pass diagrams. Add missing schema fields: clarifying question, not-available required fields, business-day unsupported flags, org recipient mapping, rail typology mapping and mock `auto` behavior.
9. Wire camelCase and snake_case YAML/internal examples need aliases and tested adapters. Decimal money must round-trip exactly even when the external shape says JSON number.
10. Safe expression examples use unqualified payment paths while the later grammar allows facts/classification paths. Canonicalize expressions under a versioned grammar; never allow unrestricted attribute access.
11. Worker duplicate handling acknowledges a fresh running lease; crash recovery must not lose jobs after early acknowledgement. Choose lease/outbox/watchdog or durable task execution and test it.
12. Local process semaphores do not enforce quotas across Cloud Run replicas. Add deployment-level concurrency/token budgets and explicit distributed admission where required.
13. Evidence raw values are needed operationally, while linked analytics remain HMAC-only. State this distinction accurately and exclude victim identifiers from cross-case linking unless deliberately permitted and tested.
14. Simulated A2A acknowledgement cannot impersonate a human decision. Label machine receipt separately from receiver-authorized actions.
15. Live captions may arrive after audio is played. A post-caption filter cannot enforce prevention of unsafe audible output. Test buffering until transcription is checked or a constrained text-first speech path before committing to the Live safety/latency design. Never persist raw audio by default; scrub volunteered secrets from transcripts before durable storage.
16. Uploads need a quarantined validation stage before promotion to durable evidence. Secret-containing images/PDFs cannot be handled adequately by a text regex alone; specify rejection/deletion and conservative limits rather than claim guaranteed detection.
17. Required IAM grants need derivation from actual operations: API text inference, Tasks scheduling, eval-job invocation and source reads; eval status/report writes; synthesis identity; push invocation and token-signing permissions. The illustrative role table is incomplete and must be tested for least privilege.
18. Pack builds/sources/review drafts need organization ownership and reviewer isolation. Define globally readable published content separately. Cross-case links may reveal another org's case existence; disclose only policy-authorized references and types.
19. API coverage gaps require explicit contracts: notifications read markers, source citation previews, message/plan history, org/user management, pinning, natural-language message edits and deletion status. Add only required operations with traceability; no undocumented endpoints.
20. Evaluation repeats are not independent cases: bootstrap and compare at the case level, report undefined/unsupported metrics honestly, separate citation resolution from entailment, and show upper bounds even with zero observed safety failures. A 20-case accuracy smoke changes by five points per error, so a three-point threshold needs a deterministic regression interpretation rather than a statistical claim.
21. Freeze a synthetic reference clock for fixtures so the October 11 sample remains reproducible. Reject or clarify future timestamps. Demo timer acceleration cannot change authoritative deadline semantics.

22. Show both required-field count and weighted completeness accurately; `7 of 8` is not necessarily a score of 0.875 under Section 18 weights. Treat 11 named typologies plus `other` as 12 enum values. Freeze whether the 40 red-team cases are part of or additional to the 300-case dataset.
23. Keep speculative win probabilities, self-scores, prize descriptions, discarded ideas and qualitative manual baseline observations as dossier history. Do not turn them into measured product claims or fabricate verbatim transcripts. The approximately 30-second new-country video segment must not imply a minutes-long replay was live; rehearse actual timing and disclose edits/waits appropriately.
24. Victim jargon restrictions conflict with earlier message labels and technical packet footers. Separate recipient documents, victim plain-language copy, and judge technical drawers through explicit audience namespaces; retain required provenance without putting banned terminology in victim instructions.

Detailed specialist findings in ARCHITECTURE_REVIEW.md, AI_EVALUATION_REVIEW.md and PRODUCT_DOSSIER_REVIEW.md are part of this proposed planning baseline, including additional API decisions, retry budgets, reliability, UX and evaluation controls. The product review contains the full dossier page ledger and UC1–UC13 mappings. Unresolved items remain visible until an ADR closes them.

## Verification and human checkpoints

V1–V9 cover actual available model IDs, supported SDK/ADK versions, Live formats/capabilities, MCP/A2A APIs, Model Armor, retrieval availability, storage versus model processing locations, official jurisdiction facts, and observed project quotas. Source documents are evidence to investigate, including claims labeled Official; none substitute for current official documentation and authenticated project checks.

Named human reviews are required for legal/regulatory pack publication, Hindi UI/captions, workflow realism, consent/privacy/terms, trademark/domain, eligibility and outside-team comprehension tests. These can proceed alongside independent engineering. Do not fabricate reviewer names/signatures, baseline transcripts, metrics, or evaluation seed reports. A seed report must come from an actual run or be clearly marked fixture data.

Proposed defaults: Relay remains a working title; English/Hindi only; local/dev/prod minimum with staging P1; asia-south1 storage subject to availability verification; retrieval implementation behind an interface; no Terraform/DLP/billing/SSO unless later justified. Do not silently choose or create a paid project.

## Competition timeline and scope

Checked organizer pages on 13 October 2026: https://aibuildercup.com/index.html and https://aibuildercup.com/Faqs.html. The official site lists team formation through 14 October, not the dossier's 11 October; prototype submission is 18 October. Exact cutoff/timezone and registration status must be confirmed in the user's dashboard.

The full specification is ambitious for roughly five calendar days. Retain every requirement, but do not promise full completion by the deadline. Prioritize one reliable complete text loop, then required voice, pack generality, measured evaluation and understandable live presentation. Only exercise the specified cut list explicitly: third language, true-audio evaluation, Terraform, DLP, keyboard shortcuts, PDF styling, cluster graph. Never silently drop simulation labels, provenance, verifier, human approvals, evaluation with n/CI or the live-built pack. M4 is the first end-to-end text demo; it is not the complete P0 submission because voice, live pack building, Eval Lab and Present Mode remain.

## Next action awaiting approval

Approve this phase structure and M0 scope. Implementation remains unstarted until approval. Before actual cloud integration, obtain project IDs/access, budget expectations and confirmed region; no secrets need to be pasted into chat. Later human/source approvals are separate gates and will be requested only when their concrete review artifacts are ready.
