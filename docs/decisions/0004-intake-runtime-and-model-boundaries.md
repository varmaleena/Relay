# ADR 0004: M1 intake runtime and structured extraction

Date: 14 October 2026. Status: accepted for M1; production deployment remains pending.

## Decision

M1 implements only T10–T13 and the minimal durable evidence worker pulled forward
from T14. E10 returns an explicit 501 until M2. Intake and evidence agents use the
pinned Google GenAI SDK with configured verified Gemini model IDs. The planned ADK
workflow orchestration belongs to the later workflow increment; current intake is
not represented as an ADK deployment.

The review stack separates Firebase identity/data project `demo-relay-local` from
Vertex inference project `work-511514`. Identities are real anonymous tokens issued
by the Firebase Auth emulator and checked by Firebase Admin, including revocation.
The emulator adapter is allowed only in local mode, with a demo project and exact
loopback host. Firebase has no App Check emulator; only this guarded adapter omits
App Check. Deployed authentication continues to require ID token and App Check.
An emulator environment variable cannot silently divert production authentication.

Cases, revisions, idempotency reservations and jobs use Firestore transactions.
Confirmed manual facts cannot be overwritten by later model output. Evidence is
validated and quarantined before extraction; promotion requires strict extraction
validation and completed conservative safety inspection. A worker claims jobs with
leases and bounded retry/backoff, skips active leases, and isolates job failures.
This single-consumer local runner is not a claim of production queue scalability.

The M1 user review exposed valid partial extraction omissions across a short
conversation: amount and recipient could be absent even when stated, and the
next currency-only answer could not recover them from structured known facts.
Intake now supplies only the current victim's six most recent user statements,
up to 16,000 scrubbed characters, with original server arrival timestamps.
Assistant text and client-provided history are excluded. The history is untrusted
source data; it can fill missing facts about the same payment but cannot override
confirmed facts or become instructions. Relative times use the source statement's
timestamp, rather than the time of a later reply. `intake_text.v2` identifies this
behavior; the prior v1 remains preserved. Extraction failures explain retry/manual
entry instead of silently posing an ordinary missing-field question again.

Local evidence capabilities use a persistent random signing key, owner/path/mode
binding and expiration. Uploads still require the owner's identity. A short-lived
signed preview GET is public so an image element can fetch it, but the handler
validates capability, case state and matching evidence path. These URLs are bearer
capabilities and must not enter access logs; the runner disables API access logging.
The local file store is prohibited outside the local environment. GCS is the
deployment adapter; workload signing IAM and cloud storage verification remain
deployment gates. No preview is exposed while evidence remains in quarantine.

## Provider schema compatibility

Actual full canonical Pydantic schema requests failed with HTTP 400 using both
synchronous and asynchronous SDK calls. A simplified native JSON Schema succeeded.
The provider projection resolves references and omits selected schema metadata,
optional spans, optional-null unions and server-owned arbitrary provenance maps.
Changing these together establishes compatibility, not which keyword caused failure.

The projection does not replace the canonical domain schema. Local Pydantic
validation still enforces bounds and types; deterministic allowed-entity, text-source
and secret checks apply; provenance is assigned by trusted application code. Invalid
output does not become a plaintext fallback. Production schema changes require a
new capability smoke and recorded decision.

## Verification and limitations

The [agent smoke report](../../tests/fixtures/intake/SMOKE_REPORT.md) records 20
distinct synthetic text receipts: 19 validated responses, one HTTP 504 and 10 exact
three-field raw matches. No normalized accuracy or entity-F1 score was measured.
The browser integration additionally exercises a synthetic PNG receipt. These checks
do not establish broad OCR, Hindi comprehension, visual DLP or legal correctness.
Fluent Hindi review, full-cloud application verification and broader reviewed gold
datasets remain open. Raw model content, credentials and signed URLs are excluded
from routine logs. Only synthetic data is permitted for the demonstration.
