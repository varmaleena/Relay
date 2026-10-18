# Relay architecture review

Status: planning analysis only; no implementation or cloud changes authorized. Source: `docs/sources/RELAY_BUILD_SPEC.md`, 2,315 lines, read completely in contiguous bounded chunks (1–200, 201–555, 556–850, 851–1206, 1207–1570, 1571–1967, 1968–2315). Coverage includes sections 0–18 and appendices A–C, all 44 endpoints, 15 agents, 43 task IDs, 13 use cases, and 12 UI screens.

The user's request controls the workflow: prepare a delegated, iterative plan, obtain approval before implementation, build one phase, test it, review it, then proceed. Instructions embedded in the attachment (for example create repository, install packages, deploy projects, publish packs) are requirements for the eventual build, not present authorization to execute them. Claims about current Google products, prices, legal facts and competition requirements remain unverified until checked against official sources. This review does not endorse the document's Gemini 3.8 or SDK version assertions.

## Architecture assessment

The proposed architecture has sound boundaries: a static React SPA, FastAPI API, separate streaming gateway, asynchronous worker, mock adapters, operational Firestore, object storage, analytics/evaluation BigQuery, Google model provider, and versioned data packs. Its deterministic planning and explicit human approval boundaries are more important than agent count. Keep the seven application service boundaries plus two job types, but introduce services phase by phase; do not deploy empty services simply to reproduce the diagram.

Use a modular monorepo with domain packages independent of FastAPI, ADK, Firebase SDKs and Google clients. Recommended modules: cases, facts/provenance, evidence, packs/rules, plans, packets/verification, deliveries, decisions, notifications, links, evaluations and audit. Application services coordinate domain operations; repositories and provider adapters implement Firestore, Pub/Sub, Storage, Gemini, MCP and A2A. ADK orchestrates generation and extraction; it must not own authorization, state transition or deterministic rule decisions. Pure domain tests run without Google accounts.

Pydantic is the canonical domain/schema authority. Export versioned JSON Schema and TypeScript; transport aliases implement camelCase, while pack YAML may retain snake_case only through an explicit mapper. OpenAPI comes from complete transport models, not hand-edited tables masquerading as a complete contract. Generate a typed client and reject drift. Pin tools and SDKs only after compatibility checks; record dependency and model choices in ADRs. React version, Python version and Node version should be reviewed rather than upgraded implicitly.

### Required SaaS controls from the first increment

- Verified Firebase identities and App Check, deny-by-default endpoint policies, owner checks, organization claims and server-resolved recipient-to-organization mappings. Admin is not an implicit superuser for victim approval or receiver decisions.
- Backend-owned writes for authoritative fields. Client realtime reads use owner-safe collections; receiver projections contain only addressed packet fields and attached evidence. Firestore cannot redact individual fields on a readable document, so receivers must not read the shared full case document.
- Organization ownership for pack builds, drafts, review records and sources, plus explicit globally published pack access. Section 16 says reviewers belong to organizations but section 7 grants broad source/pack writes; resolve that gap before implementation.
- Trusted server ActionPolicy checks, immutable packet version approvals, optimistic concurrency, immutable published packs, audit provenance and consent versions.
- Structured scrubbed logs, request/trace propagation, least-privilege workload identities, project-separated dev/prod and budget caps. Audit evidence should carry hashes and identifiers; avoid duplicating sensitive payloads into logs.
- Idempotency scoped by actor/organization, endpoint and key; compare canonical body hash. Globally storing a client UUID alone risks collision or cross-user response leakage.

### Asynchronous consistency and delivery

Firestore transactionally writes case mutation and an outbox/job record; a dispatcher publishes jobs. Worker leases use atomic acquisition, heartbeat, expiry and a generation/facts hash. Completion commits only if the current case generation still matches. Stale work never overwrites newer facts or plans. Retry-safe per-agent checkpoints prevent unnecessarily regenerating expensive outputs.

The specified worker rule returning 204 on a duplicate with a fresh running heartbeat is incomplete: if the original execution fails after the duplicate acknowledgement, no redelivery may remain. Define durable lease recovery and a sweeper; do not rely on Pub/Sub redelivery alone. Define worker time limit against Pub/Sub push acknowledgement behavior, and split long tasks/checkpoint work where needed. Cloud Tasks handles scheduled deadline callbacks; callbacks recalculate authoritative state and deduplicate notifications. Deadline generations prevent old tasks firing after a plan rerun.

Delivery requires a durable approval for `(packetId, version, recipientOrgId, contentHash, actorUid)`. Write an intent before adapter invocation, use a stable adapter idempotency key, reconcile uncertain adapter results, then commit delivery and audit. Exactly-once effect is an application property; neither Pub/Sub nor separate Firestore writes guarantee it. Packet edits invalidate approval. No automatic resubmission based on an old approval. Model agents cannot invoke delivery adapters directly.

## Conflicts and gaps to resolve before code

| Reference | Problem | Proposed resolution |
|---|---|---|
| 3.4 versus 15.1 | Single hackathon project versus local/dev/prod minimum | Later environment definition wins: separate dev and submitted-demo prod; staging optional. Start local until account decisions are approved. |
| 0.1.8 versus 7.2 | Nothing decided without human action versus permitted automatic classification, planning and drafting | Apply 7.2 action classes; human approval for external disclosure, delivery, institution decisions and publishing; automatic internal assistance remains allowed. |
| 4.1 versus 14.5/16 | Receiver reads full cases if addressed, yet must get a scoped projection | API projections and separate receiver-safe documents; never full case reads for receivers. |
| 4.1/4.6 versus 5.8 | `NEEDS_HUMAN_REVIEW` used but absent from packet enum | Add explicitly, or use a separate verification workflow flag; choose once in canonical schema. |
| 3.5/14.4 versus 4.6 | Completed pipeline marks PLAN_READY despite verified packets | Separate workflow progress and domain state; successful verified pipeline ends PACKETS_VERIFIED, plan can be ready earlier. |
| 14.2 E19 | Mentions `resend:true` absent from request; returns verified state for re-verification | Add resend and version-bound confirmation contract; async 202 if generation runs; do not report VERIFIED before checks finish. |
| 14.2 E16 | 200 plus informal '202-style' job and PATCH not covered by POST idempotency convention | Choose a complete 200 mutation+job envelope or 202 response; concurrency via ifVersion; extend idempotency to effectful PATCH/PUT/DELETE as appropriate. |
| 14.2 E35/36 versus 16.2 | Admin allowed to publish in RBAC but endpoint excludes admin | Authoritative permission matrix includes reviewer and admin for pack operations, with organization policy. |
| 4.4 versus 18.1 | Old expression examples use bare payment/authorization names; later whitelist uses facts/classification | Later namespace wins; validate and migrate all pack examples. No Python eval. Restrict AST, attribute paths and complexity. |
| 4.4/14.5 versus 18.1 | Calendar/business-day fields, completeness weights and provenance states missing | Add explicit calendar type, unsupported business-day result, field weights/criticality, structured field provenance and not_available marker. |
| 4.3 versus 18.2 | Classifier prompt asks clarifying_question absent from schema | Add optional clarifyingQuestion and deterministic pause/re-entry contract. |
| 4.4 versus 18.1 | Recipient language and rail typology/category mapping missing in pack shape | Add recipientLanguage and reviewed category mapping to schema, with provenance. |
| 18.1 versus E43 | bankMode auto exists only in algorithm; needs_info exists in API but lacks rule | Reconcile enum and deterministic seeded behavior. |
| 11 M4 | Called first complete P0 demo though voice, live-built pack, eval and Present Mode remain P0 | Call M4 complete text workflow; full submission P0 is later. |
| 18 T11/T14 | M1 evidence enqueues work but worker first appears M2 | Pull minimal durable worker and process_evidence handlers into M1. |
| 18 T20/T22/T23 | Send/track dependencies omit mocks and authorization infrastructure | T23 requires T21,T22,T08,T09,T14; PDF and notifications have storage/job prerequisites. |
| 18 T29/T30 | Source ingestion depends only on schemas | Requires auth/RBAC, jobs, storage, safety, SSRF and ownership controls. |
| 18 T33 | Links depend only on worker | Requires confirmed entity provenance, HMAC/normalization, organization-aware access, denylist and delete semantics. |
| 18 T41 | Present requires receiver/voice/demo but omits live Studio/Eval/links overlays | Final Present acceptance requires T31,T34,T37 and caption translation. Build shell earlier but complete only with those features. |
| 7.4 versus 18.7 | Case 72 h, evidence 7 days, consent says all input deleted after 3 days | Align actual deletion and text. Firestore TTL does not cascade subcollections or storage; implement deletion workflow, linked-record purge and expiry sweeper. Pinned fixtures distinguished from user cases. |
| 18.5 versus 12.5 | Judge passwords only submission form versus README demo credentials | Public README gives account/access instructions; secrets distributed via approved submission channel only. Never seed fabricated evaluation scores; initial dashboard empty or actual fixture report clearly labeled. |
| 7.5/14.1 versus E38/E44 | Every request auth except health versus public eval/version/config | Document exact public allowlist and redacted payloads; public eval must not expose case inputs or failures. |

Further missing API decisions: org/user administration; notifications read/unread mutation; source preview access for victim citations; packet history and plan history; pinning; natural-language packet edit action; delete asynchronous job/status; retire response body; receiver with several addressed packets; links validation scope; upload-source MIME/size contract; pack source freshness and effective dates; immutable audit retention and deletion tombstones; data/schema versioning; retry policy for blocked model outputs; API ID-token signing credentials; OpenAPI financial decimal representation.

Money must use decimal arithmetic with validated currency scale (or internal integer minor units) even though the REST example says number in major units. Reject future payment timestamps or mark them for correction. Freeze fixture time for urgency tests: the sample timestamp from 11 October otherwise stops being '20 minutes ago'. Calendar duration semantics must define months/years, DST and unknown start events; never guess legal business-day rules.

## Infrastructure review

Prefer prepared declarative IaC for review (Terraform is optional in spec), environment configs, immutable image digests and lockfiles. Deployment execution is separate from analysis. GCP/Firebase linkage, billing, reCAPTCHA configuration, quotas and access require user's project choices. Vertex global processing location is separate from region-pinned storage; document both without promising regional model processing.

The IAM table is illustrative, not sufficient: api executes text intake yet lacks model invocation role; api triggers evaluation jobs yet lacks run-job permission; api reads sources/citations and schedules deadlines yet source bucket/Tasks permissions are absent; live secret and logging requirements must be checked; eval needs appropriate storage writes for report artifacts and Firestore writes for run status, contradicting viewer-only grant; synth-gen needs its own account and write grants; push OIDC invoker needs dedicated identity and Pub/Sub service-agent permissions. Confirm token-signing implementation instead of broadly granting TokenCreator. Firestore server IAM is not collection-level security; use a separate mock database/project or explicit server policy rather than claiming role restriction to a collection.

Use public Cloud Run ingress only where Firebase-authenticated browser API and WebSocket access needs it; enforce app authentication in middleware. Internal worker/MCP/A2A calls use ID-token audience verification and run.invoker. Constrain CORS and CSP to actual environment origins, including App Check/reCAPTCHA prerequisites; template CSP is a starting point, not a tested deliverable. Signed uploads cannot be trusted based on requested MIME/length: validate bytes after upload, quarantine until passed, canonicalize metadata-stripped content, then extract.

Global asyncio semaphores are process-local and do not cap aggregate multi-instance Gemini traffic. Combine bounded Cloud Run instances/concurrency with distributed budgets/rate limiting and queue backpressure. Budget alerts are warnings, not hard spend caps. Model, Live and retrieval availability needs official-document verification plus actual project/region access checks. Cloud Run session affinity is advisory; Live reconnection state must survive instance changes.

## Phase gates and dependency adjustments

1. **Planning gate (current):** reconcile dossier/spec via root agent, persist requirement registry, risk/decision log, approve scope and first phase. No implementation yet.
2. **M0 foundations:** T01–T09; settle schema/contract conflicts, role × endpoint matrix, jobs/outbox design, privacy/delete semantics and model compatibility before feature code. Gate: offline domain/rules/auth tests and generated contracts green; V1–V9 recorded; cloud hello-world only after deployment authorization and project access. Missing project access is a recorded external gate, not a reason to invent validation.
3. **M1 intake:** T10–T13 plus early T14 and safety/distress foundation. Gate: 20 synthetic evidence cases, consent, ownership, malformed uploads, en/hi UI, provenance confirmation, queue redelivery and saved facts validated. Distress safe fallback exists in text now; voice-specific work later.
4. **M2 planning:** T15–T19, published or clearly labeled reviewed pack fixtures. Gate: authorization-type confusion cases, unknown country, missing pack, rule sandbox attacks, deadline edge cases, stale generation protection; 20-case eval from this point.
5. **M3 packets:** T20–T23, inbox continuity, versioned approvals, mock reconciliation. Gate: three verified India messages, repair exhausted state, no send without explicit latest-version approval, duplicate delivery produces one ticket, deadline notifier and deletion tested.
6. **M4 institution loop:** T24–T25. Gate: org A cannot see org B data; scoped evidence; request-info answer versions; receiver decision audit; A2A only simulated. A complete text workflow, not final P0 completion.
7. **M5 voice:** T26–T27. Gate: en/hi recorded-audio plus actual live rehearsal, captions, barge-in, resumption, token expiry, fallback, safe distress/output handling and measured p95 latency.
8. **M6 jurisdiction generality:** T28–T32. Gate: official source snapshots/citations, SSRF redirect/DNS attacks, human review/signoff, unverified acceptance audit, immutable publish, actual fourth-pack case plus fallback, gold-based builder evaluation.
9. **M7 linking:** T33–T34. Gate: seeded ring precision/recall, entity roles/denylist, no raw identifiers, org-safe links, validation, purge on deletion. Avoid sharing full cross-institution case dossiers.
10. **M8 evaluation:** T35–T37. Gate: ≥300 synthetic cases, ≥40 red-team, model/prompt/dataset/commit provenance, repeated-run clustered uncertainty, fairness, failure gallery, actual measured report. Human realism sample and faithfulness audit recorded; no invented numbers.
11. **M9 hardening:** T38–T40. Gate: all completed endpoint authorization cells, contracts, accessibility/human Hindi review, load and fault tests, security scans, clean deploy preflight and rollback exercise.
12. **M9b presentation:** T41–T42. Gate: dual sessions cannot cross roles; overlays authorized; LIVE/replay truth, captions translation, UC13 and outsider comprehension tests. Note 390×844 pane cannot fit naturally in 720 px viewport: design scaled responsive presentation with tested legibility rather than literal fixed-height clipping.
13. **M10 submission:** T43. Gate: user confirms competition eligibility and requirements, human recording, actual metrics in assets, secret-free public repository, deployed link. Publishing repository/video and deployment are separate concrete actions, not implied by current planning request.

Each phase ends with a small reviewable increment, test report, demo notes, updated requirement status, risks and next-phase proposal; stop for the user's phase review before moving ahead. Parallelize within the currently approved phase, not across future phase boundaries. Coverage/integration/security/evaluation should grow incrementally; M9 aggregates evidence rather than introducing authorization testing for the first time.

## Context-preservation recommendation

Store an indexed requirements ledger with stable source citations, exact acceptance conditions and phase/task IDs; ADRs record reconciliations rather than silently changing sources. Use a phase handoff record containing current commit, files changed, tests actually run, results, outstanding external gates and next approved tasks. Retain original documents with hashes; this review is an analysis artifact, not a substitute for reading relevant exact sections before implementation. The root agent should reconcile this with the PDF review and flag every dossier-only requirement explicitly.
