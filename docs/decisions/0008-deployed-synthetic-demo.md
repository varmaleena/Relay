# ADR 0008: bounded deployed synthetic demonstration

17 October 2026. The user approved the reliability and minimal Google Cloud
deployment checkpoint. M4 and real institution integrations remain out of scope.

The deployed dev demonstration may explicitly opt into unreviewed draft packs
with both ALLOW_DRAFT_PACK_PREVIEW and DEPLOYED_DEMO_PREVIEW. This exception is
restricted to dev, DEMO_MODE=true, Firebase authentication and GCS storage. The
request still explicitly opts into draft planning. Staging/prod reject the
exception; it does not publish a pack or invent human review. Source verification,
visible unverified notices, fictional-data warnings and approval guards remain.

Use separate API/worker Cloud Run identities, private authenticated worker
requests, Firestore durable jobs and Pub/Sub post-commit wakeups. A bounded private
scheduled sweep reconciles missed publish, deferred retries and expired leases.
Publication failure cannot undo a committed job. Duplicate processing remains
guarded by domain leases and version/input proofs. No continuous cloud poller.

Evidence and PDF exports use separate private buckets and explicit IAM keyless
signing. Source snapshots remain immutable checked image assets. No unused
BigQuery, voice, receiver or separate external mock services are claimed deployed.

Deployment is a development demo, not a production release. The existing INR1,000
planning target and Mumbai at-rest preference remain; global model processing
does not establish India residency. Full cloud-browser authorization, signed
storage, queue recovery and deletion must be verified before declaring readiness.
