# M0 cloud execution record

Date: 13 October 2026, Asia/Calcutta. Project: `work-511514`.

The user authenticated CLI and Python ADC, then delegated the budget and region choice. Root selected a lean Mumbai dev/demo setup with a ₹1,000 planning target. This is scoped to M0 and does not authorize a production release.

Verified: project active, billing enabled, ADC refresh succeeds, quota project matches. Runtime APIs were initially disabled. Root enabled Cloud Run, Cloud Build, Artifact Registry, Vertex AI, IAM/IAM Credentials and Billing Budgets APIs, retaining existing logging/storage APIs.

Created alert budget `ac424a5a-5ac9-4438-8e1f-3d83ee3f6f0e`, filtered to this project, INR1,000, thresholds 50%/80%/100%, custom period October 13 to October 19 exclusive. This is the selected demo operating period, not evidence of an exact organizer cutoff. Default billing-account IAM notification recipients are retained. Alerts can lag charges and do not stop spending.

The cloud build upload was inspected with `gcloud meta list-files-for-upload .`: only `.dockerignore`, `requirements.lock`, `infra/cloudbuild.smoke.yaml`, and `services/platform_smoke/{Dockerfile,main.py}` are included. Workspace credentials, SDK files, documents and other application files are excluded by explicit `.gcloudignore` rules.

Publisher-model discovery initially failed with HTTP404 on v1. The documented catalog API uses v1beta1; discovery then succeeded with 28 models including `gemini-3.8-flash`. Model listing is metadata, not proof of generation access.

Initial reviewed plan hash: `045f848ce45adce7f93653836d52d945440fabed7306cbc6fd827b7b2342043c`. Strengthened bucket validation produced final hash `0c54eebef33d23adeb5e9e89eccf763ecd42d78b4c40019b11807d869c44fb31`, retained in M0_SMOKE_REVIEWED_PLAN.json. Applied operations created `relay-dev-smoke` and `relay-dev-build` service identities, Docker repository `relay-dev` in Mumbai, and `gs://work-511514-relay-dev-build-source`. Bucket inspection confirms ASIA-SOUTH1, uniform access true and public-access prevention enforced. Runtime has the Vertex AI user role; builder has repository-scoped writer, bucket-scoped viewer and project log-writer permissions.

Apply stopped before build because the absent-image probe returned the CLI's exact “Image not found” wording with usage help, outside the initial absence allowlist. A narrow first-line/help-tail fix and regression tests now pass; unexpected tails still fail closed. Root directly submitted the same reviewed build operation, without changing its resource scope.

Build `5b05d758-ddaa-4223-8867-b9ef9a694fb1` completed SUCCESS in asia-south1. The private `relay-dev-platform-smoke` Job deployed Ready, using the reviewed hashed image tag and dedicated runtime identity. Job IAM inspection returned no public bindings. One execution `relay-dev-platform-smoke-4tvlf` completed successfully: succeededCount=1, Completed=True. Its sanitized structured log reports `event=platform.smoke`, `model=gemini-3.8-flash`, `success=true`. This confirms the response marker; no model text or tokens were logged. No second model execution or automatic retry was performed.

The deployed connectivity gate is passed. No application database, Firebase setup, evidence/export/source buckets, queues, secrets, analytics datasets or production services were provisioned. These retain explicit status in the foundation registry. AI processing through global is distinct from Mumbai at-rest storage and has no Indian processing-residency guarantee. Readiness of the future application is not implied by smoke success.
