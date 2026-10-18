# Infrastructure foundation status

## Reviewed minimal application checkpoint (17 October)

The older M0-only paragraphs below describe that historical smoke plan. Root has now
verified the default Firestore database in Mumbai and is configuring real Firebase
Authentication/App Check. The additive application plan is separate:

```powershell
python -m infra.scripts.deploy_app
python -m infra.scripts.deploy_app --apply --reviewed-plan-sha EXACT_SHA --artifacts .tmp/app-infra-UNIQUE
python -m infra.scripts.deploy_app --phase triggers --worker-url https://relay-dev-worker-REVIEWED.a.run.app
```

Planning makes no cloud calls. Apply requires the regenerated exact hash, probes existing
resources and rejects unexpected probe errors, mismatched location/security and public
worker IAM. An existing matching resource is skipped; additive IAM and explicit bucket
configuration updates can safely repeat. Choose a new local artifacts directory on each
apply; it contains only reviewed lifecycle/CORS JSON. No database creation/build/runtime
deployment or model invocation occurs in this script.

Foundation resources are dedicated API/worker/job-invoker identities, two private buckets,
seven-day lifecycle backstops, exact work-511514 web.app/firebaseapp.com CORS origins,
two Pub/Sub topics and scoped IAM. Both API and worker publish durable job wakeups.
Trigger phase needs the actual deployed worker URL, a private worker policy, the standard
Cloud Scheduler service-agent role and deployer actAs on the job-invoker account. It creates
authenticated push with600s acknowledgement, bounded retry/DLQ forwarding and a10-minute
private repair/retention sweep. DLQ subscription retains undelivered messages for inspection;
no automatic poison-message replay is provided. Review trigger hash separately after deployment.

Runtime deployment is a separate root-reviewed command using immutable image digests and
validated environment configuration: API1Gi/concurrency4, worker2Gi/concurrency1, both1CPU,
min0/max1 and timeout600s, dedicated service identities. API is network-public but enforces
real Firebase ID tokens/App Check; worker remains IAM-private. Never add an allUsers worker
binding. Source upload must use scripts/stage_cloud_build.py's fresh allowlisted directory,
not this checkout; smoke .gcloudignore remains unchanged. Firebase Hosting preview and
real synthetic Auth/AppCheck/GCS/job/PDF/delete smoke gates precede promotion.

INR1,000 remains an alert target, not a cap. Lifecycle is asynchronous, not a claim of exact
72-hour physical deletion. Model/global processing and Mumbai storage are different boundaries.

The current executable plan is restricted to `work-511514`, dev, Mumbai `asia-south1`.
It prepares only the private M0 platform-smoke Job. Full application resources remain
tracked in `plans/foundation-resource-registry.json`; their prepared BigQuery DDL is not
executed by the smoke plan. No database creation or production environment is included.

Initial read-only inspection found an active project, open INR billing and disabled Firestore/Run
APIs. A disabled Firestore API prevents reliable database inventory; do not infer that no
database exists. Enable/list/review the existing database before deciding its location.

Review and application commands:

```
python infra/scripts/setup.py --model DISCOVERED_GEMINI3_ID
python infra/scripts/setup.py --model DISCOVERED_GEMINI3_ID --apply --reviewed-plan-sha EXACT_SHA
```

The first command performs no cloud calls. It emits all command arrays and a hash over
configuration and the five-file build inputs plus `.gcloudignore` packaging policy. Applying
requires the exact reviewed hash; changed inputs invalidate it. Existence probes skip
existing resources, validate repository format/bucket location and fail closed on permission,
API, network and unexpected errors. IAM changes are additive. Job deploy does not execute
it; one separate reviewed `gcloud run jobs execute ... --wait` supplies the live-model check.
No direct shell string evaluation, deletion, public invoker, credential keys or future app
resources occur. No smoke provisioning was executed by the infrastructure agent.

The smoke plan has two identities: runtime `relay-dev-smoke` with only the predefined Vertex
AI user role, and builder `relay-dev-build` with Artifact Registry writer on the dev repository,
Storage object viewer on the source bucket and Logging log writer at project scope. Build
logs go to Cloud Logging. The source bucket blocks public access and uses uniform access.
Only explicit source upload by the authenticated deployment user is allowed; the runtime
has no access to evidence, database or source bucket. Cloud Build service agents retain their
Google-managed service roles; no default compute identity gains an application role.

The INR1000 target in `budget.guard.json` is an alert target, never a hard spend limit. Root
activated project-filtered billing alerts before paid execution; see the cloud execution record. No unrelated project or
external recipient is added. The smoke Job has one task, parallelism one, no retry, 120-second
execution timeout, 1 CPU/512 MiB, one bounded 256-output-token request and no schedule.
It incurs no idle compute while not running. Registry/source storage and deliberate builds
can still incur costs; alerts lag charges and do not shut down spending. Root selected the alert operating window 13 October inclusive through 19 October exclusive.
The competition submission cutoff remains unverified; this operating window does not establish it.

## Client security rules

Firebase client rules are independent from backend Admin SDK IAM. All case, fact, packet,
delivery, source, pack and audit mutations go through authenticated server endpoints.
Victims read their own cases; anonymous Firebase provider is the only role-claim fallback.
Receivers read only `receiverViews/{orgId}/cases/{caseId}` and its scoped projections.
Reviewers read their organization's sources/drafts; publishing goes through the API.
`publishedPacks` contains public redacted projections, never private review metadata.
Notifications allow owners to update only `readAt` to the request server timestamp.

Storage SDK uploads are denied. Future signed upload URLs require expiry, quarantine,
byte validation and server IAM. Scoped receiver previews also go through the API. App Check
is configured/enforced independently; rules tests do not establish cloud App Check setup.

```
npx firebase emulators:exec --project demo-relay-rules --only firestore,storage "npm run test:rules"
```

Use the demo-only emulator project; local Firestore8095/Storage9299 use synthetic test records.
41 rule tests passed against actual emulators, including a repeat after patched tooling.
Exact CLI dependencies have tested overrides grpc-js1.14.6/basic-ftp6.2.3/chokidar4.0.3;
these remove high advisories and the vulnerable braces watcher chain. Five moderate CLI-only
advisories remain documented by npm audit; the high/critical CI gate passes.

