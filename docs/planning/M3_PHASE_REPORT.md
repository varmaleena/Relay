# M3: packet review and simulated delivery

15 October 2026, Asia/Calcutta. User-authorized scope: T20–T23. M4 remains
unapproved. Local implementation is reviewable; provider reliability, complete
application deployment and finalist readiness are not established.

## What works

The plan opens S5 message preparation and recipient review. Packet generation
uses a bounded writer, trusted structured metadata, deterministic verification,
sentence-level entailment and at most two repairs. Missing required fields stay
missing. Inline confirmation can fill an absent allowed field; it cannot replace
known case facts. Editing creates a new version and re-verifies it. Failed,
stale, unapproved or mismatched versions cannot send.

Approval names the recipient and version. The API persists its content-bound
approval/outbox before invoking an actual registered MCP mock tool. Durable
idempotence, claim tokens, expiry, retry backoff and deletion are enforced. Mock
receipts are simulated. A report submission does not imply a hold, recovery or
institution decision. The current draft rail pack lacks a routing-category
mapping and truthfully returns NEEDS_INFO rather than an invented ROUTED result.

S6 shows packet status, actual mock ticket references, audit events and an inbox.
PDF download is authenticated, signed, short lived and invalidated by edits or
deletion. English/Hindi PDFs have a simulation banner, real text shaping and a
licensed font. Fluent Hindi review and accessible PDF tagging remain open.
Published, sourced numeric deadlines can create deduplicated in-app reminders;
the shipped draft packs cannot produce numeric legal-deadline notifications.

Receiver decisions and genuine receiver information requests remain M4/T25.
E19 cannot answer a nonexistent request and never resends without a fresh E17
approval. This is a local MCP integration; no real institution is contacted.
See ADR0006 for architectural choices and the typed E18 download-contract change.

## Test evidence

The final main suite passed 599 tests with six emulator-dependent skips; those
six checks passed separately against the real local emulator. Combined coverage
was 86%, with packages 90.4% and services 75.0%; both gates passed. Lint, formatting,
Python/TypeScript types, contract drift, build and pip dependency checks passed.
The three web content checks passed. An earlier all-green test run failed its service coverage gate (64.9%);
five meaningful HTTP integration tests subsequently covered 98% of the new
packet router. The gate was not lowered.

The actual Firestore concurrency check failed twice with an exhausted five-attempt
Aborted transaction, including with the worker paused. A pre-fix isolated repro
also passed, so this was intermittent. The fix retries only that specific
contention condition using fresh transactions, bounded attempts and jitter.
Post-fix recorded concurrent runs all passed (10.67, 9.28 and 5.53 seconds).
The final six emulator tests plus five deterministic retry tests passed together.
The retry window cannot cancel an already-running RPC. No validation/domain error
is retried, and the concurrency test was not weakened.

Browser evidence separates two kinds of validation:

- Twelve mocked component checks passed on desktop/mobile, covering unsaved,
  stale and unverified approval blocks, explicit recipient/version confirmation,
  duplicate click protection, PDF URL filtering and inbox updates.
- The actual transport test used real anonymous Firebase Auth, actual API,
  Firestore domain services and registered MCP tools, with explicitly synthetic
  classifier/writer/verifier fixtures and zero provider calls. It passed review,
  named version-1 approval, RECEIVED ticket agreement, clipboard, real PDF,
  reload, inbox persistence, stale blocking after a fact edit and deletion.
  English/Hindi desktop/mobile review had no serious/critical axe finding or
  horizontal overflow. The first attempt stopped on missing headless clipboard
  permission after a successful simulated send; that outcome is preserved.

After testing, the default queue worker was restored and a fresh no-model real sign-in/create/edit/reload/delete smoke passed. Automatic emulator exports were verified. Local file serving is scoped to the app and dependencies: a harmless private-directory probe returned 403 while a dependency font returned 200. The aborted fixture was removed through guarded domain deletion, with its receipt preserved and no pending fixture jobs.

Actual transport artifacts: `.tmp/ui-review/m3-transport-result.json`,
`transport-review-*.png`, `transport-tracker-mobile.png` and
`transport-fixture-message.pdf`. Fixture models are not live model accuracy
evidence. Visual review is not a human language or usability-study signoff.

## Live model results: reliability gate remains open

Each measured run used the same frozen synthetic scenario with three recipients,
the actual packet pipeline and Vertex gemini-3.8-flash. They are separate runs,
not nine independent cases. Every original report is retained.

| Run | Verified / n | Wilson 95% interval | Actual provider attempts |
|---|---:|---:|---:|
| Original | 1/3 | 6.1–79.2% | 7 |
| LOW follow-up | 0/3 | 0–56.2% | 7 |
| Guard fix + LOW + bounded transient retry | 2/3 | 20.8–93.9% | 8 |

These tiny-sample intervals do not establish production accuracy or reliability.
The original successful bank packet took 58.45 seconds. The recovery run verified
cyber/payment-app packets in 15.25/16.84 seconds; its bank packet stopped after two
HTTP 429 responses. That run recorded four 429 failures and three backoffs among
its eight actual attempts. There was no hidden batch rerun, fabricated successful
fallback or timeout increase. A guard incorrectly rejected harmless reference
requests and a punctuated UPI handle; focused regressions fixed both while keeping
fabricated identifiers blocked. Earlier drafts not snapshotted cannot be recovered.

The SDK now preserves typed failure categories and status codes. New synthetic
runs flush per-attempt ledgers, backoffs, repair checks and safe draft snapshots.
The packet-only LOW profile is model-capability checked and shares the SDK's
existing semaphore. Intake/classification defaults stay unchanged, including
their previously recorded M2 latency/reliability gaps. Token usage is preserved
where supplied; incomplete usage cannot support an exact monetary total.

Three origin-verified packet artifacts are available across the separate runs.
`mixed_run_fixture_manifest.json` explicitly labels their composition and hashes;
it is not a 3/3 result from one batch. The reports and limitations are under
`tests/fixtures/packets/`.

A read-only quota inspection completed two pages/372 metrics without mutations.
No fixed Gemini 3.8 bucket was present. Official model documentation says this
model uses supported Standard PayGo usage tiers rather than fixed quota; exact
capacity/acceleration pressure remains unproven. No quota, API or billing change
was made. Full evidence is preserved locally, with a compact hash-linked
`QUOTA_CAPACITY_REVIEW.md` in the fixture directory.

## Review and remaining work

At http://127.0.0.1:5173, complete a synthetic report and plan, open review
messages, prepare them, inspect checks and footer, then explicitly approve a
verified message for simulated delivery. Check its ticket in the tracker. A
model failure should show a retryable failure rather than a falsely verified
document. Provider capacity means a fresh generation is not guaranteed to pass.

M3 source packs are still drafts without invented reviewer signatures. Source,
Hindi and privacy review, full cloud application/Firebase/storage configuration,
production backup verification and broader resilience/evaluation remain open.
The 909.64 KB minified / 272.82 KB gzip JavaScript bundle warning is tracked;
these local tests do not establish submission
deployment or finalist readiness. Stop for user review before M4.
