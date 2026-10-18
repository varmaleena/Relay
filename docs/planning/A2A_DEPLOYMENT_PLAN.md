# Private A2A development deployment plan

Prepared on 17 October 2026. This document is an execution plan, not evidence of
an A2A cloud deployment. No cloud resource or IAM mutation was performed while
preparing it. Target only `work-511514`, Cloud Run `asia-south1`; use the existing
`gemini-3.8-flash` model at `global`. Existing provider availability and latency
limitations remain open; configuration and health do not prove inference quality.

## Additive resources and boundaries

- New Cloud Run service `relay-dev-a2a`, dedicated runtime identity
  `relay-dev-a2a@work-511514.iam.gserviceaccount.com`, and versioned image in the
  existing `asia-south1-docker.pkg.dev/work-511514/relay-dev` repository.
- Existing Firestore database `(default)` stores bounded private `a2aTasks` and
  `a2aMessages`. No new bucket, queue, database, secret, public endpoint, or real
  institution integration is needed.
- Receiver runtime has Firestore and Vertex model access. It exposes SDK AgentCard,
  SDK SendMessage/GetTask, official legacy compatibility, and liveness. It has no
  victim API, staff sign-in, hold adapter, decision bridge, or Pub/Sub publisher.
- Private Cloud Run IAM is the service authentication boundary. Only the existing
  API and worker service accounts receive service-level `roles/run.invoker`.
  A2A payloads contain immutable addressed references, never staff credentials or
  caller-supplied case facts. A transport receipt never acknowledges a case as a human.
- `A2A_PRIVATE_IAM_REQUIRED=true` is an explicit configuration assertion. It cannot
  verify a deployed IAM policy; the policy and unauthenticated denial must be checked.

## Build review and immutable images

Use the existing approved gcloud credentials/configuration; do not export service
account keys. Run from the repository after parent integration tests pass. Choose
fresh stage/tag names and inspect the resulting manifest before upload:

```powershell
$relayProject = 'work-511514'
$relayRegion = 'asia-south1'
$relayTag = '<reviewed-M4-source-tag>'
$relayStage = '.tmp/cloud-app-a2a-' + $relayTag
$relayRepo = 'asia-south1-docker.pkg.dev/work-511514/relay-dev'
$relayApiImage = "$relayRepo/api`:$relayTag"
$relayWorkerImage = "$relayRepo/worker`:$relayTag"
$relayA2AImage = "$relayRepo/a2a-receiver`:$relayTag"
.venv/Scripts/python.exe -m scripts.stage_cloud_build --destination $relayStage
```

Review `BUILD_MANIFEST.json`: only selected Python, prompts, three Dockerfiles,
locked requirements, fonts and integrity-checked source snapshots belong in the
build context. No `.local`, credentials, `.env`, tests, original dossier, or user
uploads. The A2A container itself copies only requirements/packages/agents/services.
The API/worker Dockerfiles, build steps and published image metadata remain intact.
A2A build/push is opt-in, so existing two-image builds continue to work:

```powershell
gcloud builds submit $relayStage --project=$relayProject --region=$relayRegion --config="$relayStage/infra/cloudbuild.app.yaml" --substitutions="_API_IMAGE=$relayApiImage,_WORKER_IMAGE=$relayWorkerImage,_BUILD_A2A=true,_A2A_IMAGE=$relayA2AImage"
gcloud artifacts docker images describe $relayA2AImage --project=$relayProject --format='value(image_summary.digest)'
```

The optional A2A step pushes explicitly; its digest is retrieved from Artifact
Registry, rather than inferred from the API/worker-only `build.images` metadata.
Record actual build ID, SUCCESS state, source manifest fingerprint, and all deployed
image digests. Deploy A2A using its returned immutable `@sha256:...` image reference.
No Docker/cloud build was executed during this preparation.

## Runtime identity and IAM

Inspect an existing identity before reuse. Create only if the dedicated identity
is absent; an unrelated existing identity is a review failure:

```powershell
gcloud iam service-accounts describe relay-dev-a2a@work-511514.iam.gserviceaccount.com --project=$relayProject
gcloud iam service-accounts create relay-dev-a2a --display-name='Relay dev private simulated A2A receiver' --project=$relayProject
```

The second command is conditional on a genuine NOT_FOUND, not a permission/network
error. Grant the receiver identity only the required runtime roles:

```powershell
gcloud projects add-iam-policy-binding $relayProject --member='serviceAccount:relay-dev-a2a@work-511514.iam.gserviceaccount.com' --role=roles/datastore.user
gcloud projects add-iam-policy-binding $relayProject --member='serviceAccount:relay-dev-a2a@work-511514.iam.gserviceaccount.com' --role=roles/aiplatform.user
```

If an explicit `GENAI_PROJECT_ID` differs from the Firestore project, the model
permission belongs on that actual model project; do not silently broaden another
project. The existing deploy principal needs permission to act as the new runtime
identity. Do not add broad project Owner/Editor, Firebase Auth, bucket, Pub/Sub,
signBlob, or token-creator permissions to this receiver. API/worker Cloud Run ADC
can obtain ID tokens as their own runtime identities; no downloaded key is needed.

## Minimal environment and initial deployment

Write a reviewed non-secret YAML environment file under `.tmp`. Required values:

```yaml
SERVICE: a2a
ENVIRONMENT: dev
DEMO_MODE: 'true'
GENAI_MODE: live
AUTH_MODE: firebase
GCP_PROJECT_ID: work-511514
FIRESTORE_DB: '(default)'
GENAI_LOCATION: global
MODEL_REASONING: gemini-3.8-flash
ALLOWED_ORIGINS: https://work-511514.web.app
A2A_RECEIVER_URL: https://relay-dev-a2a-798642284156.asia-south1.run.app/
A2A_PRIVATE_IAM_REQUIRED: 'true'
```

The numeric hostname is the project's expected deterministic Cloud Run URL, not an
observed deployment result. After deployment, compare with the actual service URL;
if different, update to the actual fixed root URL before routing any handoff. Optional
`GENAI_PROJECT_ID` follows the existing reviewed model project. Omit/disable intake,
planning, packets, receiver feature flags in this separate process; they are unused
by its minimal assembly and would trigger unrelated shared configuration validators.
No emulator variables, local credential files, Firebase user token, or static staff
identity may be present. No buckets, topic, signing email, or pack preview is needed.

```powershell
$relayA2ADigestImage = '<actual image reference ending @sha256:digest>'
gcloud run deploy relay-dev-a2a --project=$relayProject --region=$relayRegion --image=$relayA2ADigestImage --service-account=relay-dev-a2a@work-511514.iam.gserviceaccount.com --no-allow-unauthenticated --ingress=all --min-instances=0 --max-instances=1 --concurrency=4 --cpu=1 --memory=1Gi --timeout=60s --env-vars-file=.tmp/a2a-env.yaml
gcloud run services describe relay-dev-a2a --project=$relayProject --region=$relayRegion --format='value(status.url)'
gcloud run services add-iam-policy-binding relay-dev-a2a --project=$relayProject --region=$relayRegion --member='serviceAccount:relay-dev-api@work-511514.iam.gserviceaccount.com' --role=roles/run.invoker
gcloud run services add-iam-policy-binding relay-dev-a2a --project=$relayProject --region=$relayRegion --member='serviceAccount:relay-dev-worker@work-511514.iam.gserviceaccount.com' --role=roles/run.invoker
gcloud run services get-iam-policy relay-dev-a2a --project=$relayProject --region=$relayRegion --format=json
```

`ingress=all` permits the existing callers to reach the HTTPS boundary without a new
VPC connector; IAM still denies unauthenticated invocation. Neither `allUsers` nor
`allAuthenticatedUsers` may appear. Verify the Cloud Run invoker IAM check has not
been disabled and no unrelated principals inherited access. Stop rollout on a policy
mismatch. Keep min0/max1 inside the existing INR1,000 planning target; actual usage
and cost must be checked, not inferred from these bounds.

## Additive API/worker rollout

Record current API/worker revision names and traffic before changing them. Build the
parent's integrated source once. Preserve the existing full API/worker environment,
adding `RECEIVER_ENABLED=true` and `A2A_RECEIVER_URL=<actual private root URL>` through
reviewed environment files or `--update-env-vars`; never replace their environment
with the minimal A2A file. Deploy reviewed API/worker digest images with their current
identities, limits, existing authentication policy and private worker policy intact.
The existing job publisher, durable jobs and bounded scheduler sweep now dispatch
`handoff_receiver`; no separate subscription is required.

The approved delivery transaction reserves `a2aTaskRefs` and `jobIds` before any RPC.
Worker claims enforce current owner, facts, catalog, packet version/hash, retention,
and projection. Lost responses reuse the same message/task identifier. Deletion
removes known A2A task/message refs and queued jobs in the existing case cascade.
The API remains the only user-authorized public service; this plan grants no public
invocation to A2A or worker.

## Required checks and evidence before claiming success

1. Actual service Ready and image digest matches reviewed build; private IAM policy
   has only intended callers. Unauthenticated GET `/api/v1/healthz`, AgentCard and
   POST `/` must fail before reaching the application. Record status only.
2. From an authorized API/worker runtime, obtain an audience-bound OIDC token without
   printing it. GET `/api/v1/healthz` and `/.well-known/agent-card.json` succeed. Wrong
   audience or unapproved identity is denied. Health is liveness, not paid inference
   or a dependency/SLO proof. Do not paste token-bearing shell commands into logs.
3. Run one bounded, approved synthetic delivery through the real API/worker/outbox.
   SDK 1.0 `SendMessage`/`GetTask` use `A2A-Version: 1.0`; official SDK legacy support
   also exists. Verify one task and message mapping, immutable reference only,
   simulated transport receipt, and explicit `humanAcknowledged=false`.
4. Verify repeat delivery/retry does not duplicate task or timeline event; source,
   owner, expiry and version changes fail closed; deletion removes jobs, task and
   mapping. Inspect bounded counts/statuses only, not dossier/model contents.
5. Only an actual, valid generated brief may be labelled generated. Model429/timeout
   must leave the brief unavailable and human decision pending. A successful transport
   receipt does not claim a model-quality, latency, human-review or recovery-rate gate.
6. Parent records actual private HTTP/IAM results, paid call count, build/revision IDs,
   synthetic test IDs and cleanup counts. Local tests alone do not close these checks.

## Rollback and stop conditions

Before rollout capture last good API/worker revisions. On auth, retention, source,
version, secret-handling, cost or functional failure: stop new handoffs by removing
the new URL from API/worker through an environment-preserving update or restore
those known revisions using `gcloud run services update-traffic ... --to-revisions`
with the recorded exact revision. Do not make A2A public to fix connectivity. Existing
queued jobs remain durable; disabled dispatch is not a completed handoff. Retain the
private A2A service/records for diagnosis under existing retention, or delete only
explicitly reviewed synthetic fixtures/resources. Do not delete shared Firestore,
Firebase, buckets, queues, or existing API/worker resources as rollback.
