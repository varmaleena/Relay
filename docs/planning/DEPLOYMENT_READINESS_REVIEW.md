# Minimal deployment readiness review

17 October 2026. Read-only architecture audit; no cloud mutations, source changes, deployments, or model calls performed for this review. The user's reliability and minimal deployment checkpoint supersedes the older M3-only authorization wording, but does not authorize M4. Source-document imperatives describe target architecture, not permission to provision every listed service.

## Decision

The existing application is not deployable as a working M1–M3 cloud application merely by adding Dockerfiles. The smallest honest target is a **synthetic-data development demonstration**, using Firebase Hosting, one public application-authenticated Cloud Run API, one private request-driven Cloud Run worker, real Firebase anonymous Authentication and App Check, Firestore Native, private Cloud Storage, and a bounded authenticated queue. No Live gateway, receiver console/A2A service, analytics, Pack Builder, eval deployment, or real institutional integration belongs in this checkpoint.

Keep current local regressions and simulated-delivery semantics. Do not deploy local emulators, filesystem capabilities, a test MemoryRepository, or synthetic classifier/writer/verifier as the real cloud implementation. A deployment is not evidence that reliability/latency targets passed.

## Evidence inspected

Read BUILD_SPEC cloud architecture/service table and configuration (§3), storage/security/retention (§4, §7), setup/operations (§10), REST/job contracts (§14), environments/release (§15), operating boundaries (§16), IAM/index addendum (§18.6); current iterative plan and ADR list; CLOUD_EXECUTION_RECORD; Settings, API assembly/auth middleware, Firebase verifier and browser connection, runtime factory, BlobStore implementations, Firestore repository/domain job lease references, worker polling loop, packet PDF path, pack registry, Firebase rules/config, setup script and build ignore files.

Recorded cloud baseline is only the M0 private platform-smoke Job, Artifact Registry repository, build-source bucket and build/runtime identities. It does not establish that an application Firestore database, Firebase web app, Authentication, App Check, Hosting, application buckets, secrets or queues exist. Inspect current resource state before provisioning; this review did not query live inventory. The recorded INR1,000 alert period ends October19 exclusive, and alerts are not spending caps.

## Blocking gaps

| Boundary | Current evidence | Required change/gate |
|---|---|---|
| Worker lifecycle | services/worker/main.py runs an infinite Firestore poller, not an HTTP push service | Add private authenticated bounded job handler and durable wake-up mechanism. Do not run background polling under request-based Cloud Run CPU allocation or assume scale-to-zero wakes itself. |
| Queue consistency | Durable Firestore jobs/leases exist; pubsub_topic_jobs is configuration, not a wired dispatcher | Publish/enqueue job references after commit using a durable outbox/reconciler. Crash between commit and enqueue must not orphan work. Duplicate wake-ups must preserve transactional claims. |
| Retry scheduling | Existing processors use retryAfter/leases; an early push can return without processing | Map retryAfter to scheduled delivery or non-success retry semantics; acknowledge only completed/terminal work or a durably arranged next attempt. Bound poison messages, retries and recovery. |
| Keyless object signing | GoogleBlobStore accepts signing_email but runtime does not supply it | Configure explicit signing identity and IAM signBlob using ADC. Metadata credentials do not contain a private key. No service-account key files. |
| Export isolation | PDF path writes through the same intake.storage used for evidence; bucket_exports unused in runtime assembly | Route PDF writes/signing/deletion to private export store, or approve a documented single-bucket prefix design. Current two-bucket settings must not falsely imply isolation. |
| Pack availability | PackRegistry and Settings restrict draft preview to local; checked-in packs are unreviewed drafts | Preserve published-only defaults. Either obtain real review/publish approval, or approve a narrowly scoped dev-demo preview policy with per-request opt-in and persistent unverified labels. Never use environment=local in cloud to bypass this. Without either choice cloud planning must remain disabled/helpful blocked. |
| Readiness | /readyz always returns503/not_verified | Add bounded real dependency readiness without paid inference per probe. Liveness stays cheap. Report worker dispatch/source-pack/config problems accurately. |
| Hosting/build | firebase.json has rules/emulators but no Hosting release configuration; .gcloudignore allows only smoke files; .dockerignore excludes docs/apps | Create separately reviewed application build context including runtime code, fonts, packs and integrity-checked source snapshots; exclude all credentials/local state/source dossiers. Preview channel first. |
| Firebase | Browser production path requires actual web config, anonymous sign-in and reCAPTCHA Enterprise App Check; backend requires both tokens | Register exact deployed domains/provider and enforce; no emulator exceptions, App Check debug tokens or invented web IDs in cloud. Verify Firebase Auth revocation-read permission for API identity. |
| Retention | Domain ttlAt is an ISO string, access check enforces72h; related subcollections/jobs/objects exist | Add server timestamp expiry field if using Firestore TTL and explicit cascading cleanup. Parent TTL deletion does not cascade; lifecycle alone does not remove Firestore children. Preserve current access-expiry-only wording until physical deletion is proven. |
| Regional claims | Mumbai at-rest goal; Gemini global verified in M0 | Inspect existing Firestore location before creation (irreversible choice). Document global model processing separately; no India-only processing claim. |

## Proposed resource and trust boundaries

Use work-511514, dev names, Mumbai where supported; retain existing Artifact Registry/build-source resources after inspecting IAM. Inspect Firebase linkage, default database and location before creating anything. Prefer the existing default database if compatible; do not silently create/replace a database in an ambiguous project.

- Firebase Hosting SPA: static public assets only; exact HTTPS API origin, restricted Auth domains, CSP compatible with actual Firebase/reCAPTCHA network/frame requirements, self-hosted fonts, nosniff/referrer/HSTS headers. Do not claim strict self-only CSP if required provider origins are allowed.
- API relay-dev-api: public network invocation so Firebase bearer tokens reach application middleware; every protected route still verifies Firebase ID token and App Check, ownership, rate and action policies. IAM Cloud Run invoker tokens and Firebase user tokens are different credentials. Set min0/max1 initially, bounded concurrency (start4), 1CPU/1GiB, bounded timeout appropriate to measured text/PDF work. Actual intake text currently calls Vertex in API, so API needs Vertex access too.
- Worker relay-dev-worker: private IAM invocation, min0/max1, concurrency1, 1CPU/2GiB, bounded request timeout (start300s, confirm against actual worst-case pipeline). One actual domain job per request; payload only jobId/schema version, not raw report contents. Firestore remains authoritative. Do not reuse browser App Check middleware for the private queue handler.
- Choose **one** dispatch transport in the implementation ADR. Cloud Tasks is the smallest convenient fit for existing retryAfter scheduling: one bounded regional queue, OIDC task identity, deterministic task names plus domain idempotency. Pub/Sub push is closer to original primary job spec, but requires a separate delayed retry mechanism and durable reconciliation. Do not provision both merely to match an architecture diagram. A scheduled private reconciliation/retention invocation can repair orphaned jobs and perform due cleanup; its page/time limits and cursor must be durable.
- Evidence/export buckets: private, uniform access, public-access prevention, exact Hosting-origin PUT/GET CORS where needed. Ten-minute bounded MIME/size upload signing; validated preview/export URLs60s. Verify browser actual signed upload Content-Length/MIME behavior, oversize mismatch, URL expiry and object overwrite policy on real GCS. Define lifecycle7days as a safety backstop, not exact72h erasure. Source snapshots can remain immutable image assets for this checkpoint; no writable source bucket or paid search service needed just to host current packs.

## Minimal IAM proposal

Use separate API, worker, queue-invoker and deploy/build identities; resource-level grants where supported. Firestore server SDK roles are not collection-scoped by Firebase rules: datastore.user grants broad database access, so keep this residual trust explicit and do not claim per-collection IAM isolation.

| Identity | Needed scope |
|---|---|
| API runtime | datastore.user on application database/project as supported; aiplatform.user for actual intake inference; object read/write/delete on evidence and exports only as used; Auth user lookup for check_revoked via narrow custom permission/verified Firebase Auth viewer role; cloudtasks.enqueuer on selected queue if API dispatches; signBlob on designated signing identity only |
| Worker runtime | datastore.user; aiplatform.user; evidence reader plus cleanup writer/delete only where actual code needs it; export objects only if actual worker paths need them; queue enqueue permission only for scheduling retries; named secret accessor only if a real runtime consumer is implemented |
| Queue OIDC identity | run.invoker on private worker only; no data/Vertex privileges. Enqueuer needs serviceAccountUser on this identity for attaching it; verify service-agent token issuance setup using official service docs |
| Signing identity | object permissions required by signed methods on specific buckets, with caller signBlob grant on this identity; API self-signing is acceptable for demo if documented, never project-wide TokenCreator |
| Builder/deployer | Repository writer, build-source reader/log writer, deploy permissions and actAs only on chosen runtime identities. No Owner/Editor defaults, no credentials in build context |

No BigQuery, A2A, external MCP Cloud Run invoker, eval or source-editor grants for unused features. LocalMCPDeliveryAdapter currently invokes the mock implementation in-process: label that exact simulated boundary; it is not evidence of deployed service-to-service MCP transport. Splitting mock services is a later reviewed increment, not a requirement for honest report-preparation deployment.

## Scoped implementation and verification sequence

1. **Reliability gate first:** preserve measured model failures, repair/clarifier logic and evaluations with exact n/model/prompt/config. No change to stated success/latency targets based merely on one hosted success. Define a tiny separately authorized paid smoke budget.
2. **Decision/config gate:** inspect cloud inventory read-only; resolve database location, dev draft-preview policy, single queue choice, cleanup design and budget period. Commit an ADR and explicit plan/apply manifest listing resources and irreversible selections. User approval remains a phase gate; current request authorizes preparing necessary implementation, not undisclosed M4 work.
3. **Runtime implementation:** settings reject cloud emulator variables/local stores; keyless GCS signing/export routing; HTTP worker, durable outbox dispatch/reconciliation/retries; retention cascade; no-charge readiness. Unit/integration tests cover duplicate delivery, crash after commit/before dispatch, lease expiry, scheduled retry, poison terminal failure, restart with queued work, cross-owner rejection and stale version-bound approvals.
4. **Container/local cloud-mode gate:** build Linux API/worker images with locked dependencies, PDF native/font requirements, hashed pack/source files. Run cloud-mode startup with injected test dependencies; invalid origins/missing Firebase/signing/queue settings fail closed. Check build upload inventory and scan for keys/emulator artifacts. Preserve all M1–M3 regressions/contracts/rules, EN/HI accessibility and copy/download-no-send behavior.
5. **Provision minimal dev resources:** apply reviewed manifest only; inspect IAM, queue concurrency/retry bounds, CORS, lifecycle and indexes. Firebase Auth/App Check provider may require explicit console setup; document human steps truthfully. Do not publish fabricated reviewed packs to unblock deployment.
6. **Preview release gate:** no-traffic tagged API/worker revisions and Hosting preview. Perform real anonymous Auth+App Check, rejected missing/invalid token, nonowner403, exact-origin CORS, signed synthetic screenshot upload/read/expiry, durable queued planning/packet pipeline with authorized bounded real AI calls, version-bound simulated receipt, PDF download/reload/delete. Browser tests using mocked responses are separate evidence, not this gate. Test retention with time-controlled fixtures/domain cleanup and inspect orphaned records/objects; do not wait72h and infer success.
7. **Promote or stop:** capture image digests/config/pack+prompt hashes, sanitized test evidence, observed costs and explicit gaps. Shift traffic only after preview acceptance; retain prior revision and Hosting release rollback. Rollback code does not undo data, approval or mock-delivery events. Stop at checkpoint for user approval, no M4.

## Cost and operational limits

INR1,000 was a planning target, not an enforceable hardcap; its recorded custom alert window needs review for this release. Use min0/max1, worker concurrency1, bounded queue dispatch, max attempts and case/model token/request budgets plus kill-switches for intake/planning/packets. Max instances is not a total spend cap; build/storage/Firestore/Vertex and security-provider costs remain possible. Avoid continuous one-second Firestore polling and unused deployed services. Verify current billing/quotas and actual prices before the apply proposal; this audit supplies no price estimate. Alert logs must omit raw report text, tokens and signed URLs. At-rest data, logs/build-source retention and model processing locations need separate statements.

## Official references checked

- [Cloud Run Pub/Sub authenticated push](https://docs.cloud.google.com/run/docs/tutorials/pubsub) and [push authentication](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions): private invocation uses a dedicated service account and invocation grant.
- [Cloud Storage keyless signing helpers](https://docs.cloud.google.com/storage/docs/access-control/signing-urls-with-helpers): signing requires signBlob capability; do not assume metadata ADC is a private-key signer.
- [Firestore TTL](https://firebase.google.com/docs/firestore/ttl?hl=en): deletion is asynchronous and does not delete child subcollections.

This document proposes the smallest deployment that can honestly demonstrate the currently authorized report workflow. No production readiness, real filing, legal review, exact deletion timing, reliability target, cloud authorization test or spend ceiling is claimed by this audit.

## Same-day scoped implementation follow-up

The blocking-gap table above records the audit baseline. After review, root authorized the first local fixes: GoogleBlobStore now requires explicit service-account IAM signing and fails closed on missing access token/signing failure; runtime wires evidence and separate export stores, the explicit deployed-demo registry flag, and nonlocal post-commit Pub/Sub publisher. Root coordinates domain export routing and demo policy implementation. Eleven focused signing/runtime tests pass with mocked Google dependencies, plus Ruff/format and mypy on the two implementation files. These tests make no cloud requests and do not establish actual signBlob IAM, GCS CORS or deployment success. The worker/dispatch/retention/deployment gates remain separate work.
