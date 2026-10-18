# Relay victim web application — M1

Implemented surfaces: S1 Start/consent, S2 text intake and editable facts, S3 evidence
reading/confirmation. The Flow Rail displays the broader workflow without pretending that
later planning, delivery or institution actions exist. Voice is visibly unavailable until M5.

React18/TypeScript/Vite use shared generated E1–E11 contracts. TanStack Query owns remote
state; Zustand owns the active route/session view. No canned backend responses or successful
submission animations replace actual API work. Model responses and extraction values come
from the real backend. All model/token/debug details stay out of the victim interface.

Local auth uses real Firebase anonymous Auth emulator tokens, guarded to loopback and
`demo-relay-local`. App Check has no emulator; the backend's explicit local bridge handles
that documented limitation. Deployed configuration requires an explicit HTTPS API URL,
actual Firebase project/app registration and reCAPTCHA Enterprise App Check; `getToken`
refreshes App Check credentials on every call. No static identity or invented token exists.

Copy `.env.example` to `.env.local` for an explicitly configured local standalone UI, or
use the root `python -m scripts.dev` unified stack. Vite variables are public configuration.
The backend, emulators and worker must actually run before the consent/create flow succeeds.

```
npx vite --config apps/web/vite.config.ts
npx tsc -p apps/web/tsconfig.json
npx vite build --config apps/web/vite.config.ts
node --test apps/web/tests/content.test.mjs
npx playwright test --config apps/web/playwright.config.ts
```

Ordinary browser tests exercise no-charge Start/consent/layout/accessibility and model-free
create/delete transport. The real inference test is explicitly opt-in:

```
RELAY_LIVE_E2E=1 npx playwright test --config apps/web/playwright.config.ts
```

PowerShell sets `$env:RELAY_LIVE_E2E='1'` before the command. A single desktop live run
creates one synthetic case, sends one message and extracts one synthetic receipt (two
bounded calls), then reviews the same case in desktop/mobile English/Hindi without duplicating
inference charges. It checks fact correction, evidence confirmation, reload persistence,
non-owner denial and actual deletion. Never enable this test against a real customer system.
The unified stack uses live Google inference; no API responses are mocked by these tests.
Set `PLAYWRIGHT_BROWSERS_PATH` to the installed test-browser cache where required.

Self-hosted Atkinson/Literata/Devanagari fonts, high-contrast ledger tokens, semantic controls,
48px main targets, keyboard dialog focus restoration, focusable scrolling regions and reduced
motion support implement the specified accessibility foundation. Automated axe and token
contrast checks supplement required human screen-reader and readability review.

The Hindi dictionary was drafted through actual Gemini inference; translations/REVIEW.md
retains provenance and explicitly pending fluent human review. Synthetic cases only. UI
consent/privacy text is a demo draft, not counsel-approved legal wording.

Firestore subscriptions coalesce interim writes and REST polling is bounded; authoritative
writes always go through the API. Unsupported files and failures remain visible. Unconfirmed
or low-confidence extracted details are not automatically confirmed. Explicit confirmation
calls the backend and edits carry fact revisions. Unsent text may stay in session storage;
credential mentions are conservatively excluded from draft persistence. Deletion clears the
case's browser query caches/draft, and the backend controls durable cascading deletion.

Screenshots are review artifacts under `.tmp/ui-review`, excluded from cloud source uploads.
The root phase report records tests actually run and remaining manual gates. Build performance
is not an asserted production SLO: the Firebase SDK bundle currently merits later performance
profiling; no aspirational latency numbers are displayed as measured results.
## Final browser evidence — 14 October 2026

Final unified-stack run: 4 tests passed, 2 intentional duplicate-run skips. The live test
used one text intake call and one synthetic receipt extraction call. Real issued Firebase
anonymous authentication, API requests, worker processing and persistence were used;
responses were not mocked. The same case passed confirmation, bank correction, reload,
separate non-owner denial and actual deletion back to Start.

Desktop/mobile English/Hindi Start and Intake views passed automated checks for no serious
or critical axe findings and no page overflow. Consent Escape/focus return was verified.
Eight screenshots: `.tmp/ui-review/{start,intake}-{en,hi}-{desktop,mobile}.png`.

Earlier aborted runs remain part of the root phase record: an ambiguous upload control
name and an inaccessible scroll region were fixed; a final delete was rate-limited before
mutation. Status reads are now coalesced, and the backend's owner deletion/privacy control
is independent of the normal read budget. The final complete run passed after restart.
No aspirational latency or human review is claimed from these tests.

## Multi-turn regression

`tests/multiturn.spec.ts` reproduces the reported three-turn sequence in a new synthetic
case. It is independently opt-in with `RELAY_MULTITURN_E2E=1`; use the `--grep three-turn`
filter to avoid unintentionally enabling other live tests. It sends three intake messages,
checks INR45,000 and the recipient after the second and third messages, protects a manually
confirmed bank correction, reloads the report and deletes only that newly created test case.
The user's existing case is never opened or changed by the regression.

Default execution has been verified to skip both viewport entries without inference charges.
On 14 October 2026 the authorized unified-stack run passed the desktop regression in
20.6 seconds; the mobile duplicate was intentionally skipped. All fact, manual correction,
reload and deletion assertions passed. The second reply asked about continuing contact;
the third said the details were ready to check. Neither repeated an amount question.
The run sent exactly three UI intake requests. Underlying SDK attempts, including any
schema repair, are not counted by this browser test.

Evidence: `.tmp/ui-review/multiturn-corrected-desktop.png` and the synthetic-only
`.tmp/ui-review/multiturn-synthetic-transcript.json`. TypeScript compilation, Vite production
build and regression-file formatting also passed. This bug-fix scope added the test and
this record; it did not change frontend application source.
# M2 planning interface — local implementation

S2 now provides an explicit, minimum-facts-gated planning action. The request uses
E10/E13 and a resumable E11 job; S4 reads E12 and displays ordered contacts, rule/source
references, official snapshot passages, draft/general/unverified labels and a stale
guard after a facts edit. Planning and draft-preview availability come from public
configuration. Draft preview requires an unchecked-by-default per-request choice.
No message review, delivery or simulated institution response was added in this phase.

Routes support `/case/:id/plan`, reload and browser history. Payment authorization
can be corrected explicitly alongside country and other facts. Source links allow
HTTPS without embedded credentials. Operational elapsed time is visibly distinguished
from sourced legal deadlines. Session-only job/screen data are cleared on deletion.

Local verification: TypeScript, production build and three bilingual/content checks
pass. No-charge desktop/mobile Start/consent axe tests pass; the live planning test
is skipped unless `RELAY_PLAN_E2E=1`. Its definition uses confirmed fact edits and
one explicit processing request in a new synthetic case, then checks source passages,
English/Hindi desktop/mobile axe, reload, stale state and deletion. Provider attempts
are not inferred from UI request count. Actual live planning evidence is pending root
backend readiness and scoped execution authorization. Build bundle is 869 KB (264 KB
gzip); the existing bundle-size warning is not a performance claim.

## Money editing correction

Amount and currency share one visible form. An unknown currency stays unselected;
saving requires both values explicitly. The transport retains exact decimal strings,
and formatting uses BigInt plus the original fraction without numeric float conversion.
The model-free browser regression checks explicit GBP and an exact 12-integer-digit,
eight-decimal-place value that loses precision as a JavaScript number, including reload. This test makes no
model requests. A first run used an invalid 16-integer-digit fixture and received an
expected 422. Canonical money allows at most 12 whole digits; the conservative card-shaped
13–19 digit filter also remains intentional. The corrected live transport result follows.

For the S4 live gate, setup now uses one authenticated real E4 confirmed-facts patch
in a new synthetic case rather than nine separate edits. The plan action remains a
single explicit browser click; no API response is mocked and rate limits are unchanged.

## Completed M2 browser gate — 15 October 2026

The corrected model-free money test passed: missing currency blocks save; explicit GBP
and `123456789012.12345678` survive the real PATCH, readback and reload exactly; opening
the currency editor retains the paired amount; deletion succeeds. Its mobile duplicate
was skipped. The initial invalid 16-whole-digit fixture received 422 before correction;
this was not a backend acceptance failure and no credential filter was weakened.

The live S4 regression passed in 20.4 seconds with exactly one explicit UI processing
request. Setup used real Firebase anonymous authentication and one real E4 patch with
confirmed provenance. No response was mocked. Three stations, 1930, the listed HTTPS
portal and a source entry were present. English/Hindi shell on desktop/mobile had no
serious/critical axe findings or page overflow. Reload, stale state after a bank edit,
and actual deletion back to Start passed. Provider SDK retry count is not inferred from
that one UI request; elapsed browser duration is not a plan-latency benchmark.

Four reviewed screenshots: `.tmp/ui-review/plan-{en,hi}-{desktop,mobile}.png`. The Hindi
shell is localized; plan prose and channel names generated/stored for an English case
remain English on a language toggle. Source passages retain original wording. Fluent
Hindi and source review remain pending. Visual polish noted repeated unverified notices
and a repeated plan heading; neither is claimed resolved by these screenshots.

## Post-gate presentation cleanup

The plan card now uses a distinct "People to contact" heading instead of repeating
the page title. Identical warning code/text pairs display once with all affected rule
IDs retained in an expandable detail; distinct warnings and all source citations remain.
This cleanup was verified with TypeScript, content checks and production build only;
the saved live screenshots predate it. No additional processing/model request was made.
Case language is selected at creation. Toggling interface language preserves the saved
plan's original language and provenance; live Hindi-case plan generation remains a later
validation gate rather than being inferred from Hindi interface screenshots.

## M3 review and tracker implementation

S4 links to the message review screen. Preparing messages is a separate explicit action
using E45; opening or reloading a route never starts generation or sends a message.
S5 provides recipient selection, plain-language and institution copies, required-field
editing with explicit unavailable markers, message edits bound to ifVersion, and Save
and check. Checks, citations, attachment names and the exact footer remain visible.
Approval requires the named recipient and exact current version in a confirmation modal;
unverified, stale, dirty, pending or distress states block the action. A synchronous
click latch prevents duplicate confirmation requests; network retries are explicit and
retain their idempotency key. A send error refreshes current state instead of claiming
delivery. Copy and PDF are explicit actions. PDF capabilities require the configured
API origin and packet-storage path or HTTPS storage.googleapis.com, plus an unexpired
timestamp. External sharing and natural-language message editing remain hidden.

S6 shows typed stored status, actual simulated receipt references/status/missing items,
audit updates and an inbox with read markers. Cursor pagination retains earlier events;
historical pages use explicit refresh rather than multiplying background polling.
There is no automatic acknowledgment, bank hold, recovery or invented receiver request.
Answering a receiver request remains M4 because no such request exists in M3.

The explicitly mocked component suite passed 12 desktop/mobile tests: blocked approval
states; named version-bound confirmation; repeated click suppression; PDF host rejection;
edit/version/recheck/fresh-confirmation behavior; notification read state; English/Hindi
review and tracker accessibility. No serious/critical axe findings or page overflow were
found in those fixtures. Screenshots named `mocked-review-*` and `mocked-tracker-*` under
`.tmp/ui-review` are mocked component evidence, not domain/model/delivery proof. Actual
authenticated domain-fixture browser validation awaits the root's backend gate. No M3
model generation was invoked by frontend testing. Hindi labels are authored engineering
copy with key/interpolation checks; fluent review and live Hindi messages are pending.

## M3 real transport gate — 15 October 2026

The opt-in `messages.transport.spec.ts` gate passed against the workerless local stack.
The browser created a new case with real Firebase anonymous authentication and consent.
`scripts/seed_m3_browser_fixture.py` required the exact loopback demo emulator and a fresh,
empty case, then used actual Intake/Planning/Packet services and durable jobs. Classifier,
writer and verifier were explicitly synthetic fixtures; canonical fields came from the
actual metadata builder. No approval or delivery was seeded, and no provider was called.

The browser read three saved messages, confirmed the named recipient and version, and
called the real approval endpoint. The actual MCP mock returned a RECEIVED receipt.
Copy succeeded with explicit headless clipboard permission; the downloaded file began
with `%PDF-`. English/Hindi review shell on desktop/mobile passed serious/critical axe
and overflow checks. Tracker displayed the same reference, inbox read state survived
reload, an actual fact edit blocked sending an unsent stale message, and deletion returned
to Start. The test took about 1.3 minutes including a deliberate 61-second pause with all
polling unloaded so the unchanged rolling read limit could expire. This is not a latency
benchmark. The first attempt stopped after a real demo receipt because clipboard permission
was missing; the interface accurately showed failure. No credential filter was weakened.

Evidence: `.tmp/ui-review/transport-review-{en,hi}-{desktop,mobile}.png`,
`transport-tracker-mobile.png`, `transport-fixture-message.pdf`, `m3-transport-result.json`.
These prove real transport with synthetic model stages, not live-AI verification quality.
The final test case was deleted. The first aborted fixture was subsequently matched by
its recorded receipt and exact classifier/contact/bank/verifier markers, then removed
through the domain delete cascade. Its receipt is preserved in
`m3-aborted-clipboard-receipt.json`; the deleted ID is recorded only in the private local
`.tmp/m3-fixture-cleanup.json`. Cleanup confirmed zero queued/running fixture jobs.
Other cases were not changed. Private emulator recovery auth state was removed.

After this gate, canonical field keys were replaced with friendly labels. Missing demo
routing mappings display "Demo routing setup is incomplete" rather than a task to provide
an internal key. Raw receipt data remains unchanged in the domain/audit. Two focused mocked
desktop/mobile checks pass for English/Hindi wording; transport screenshots predate this
wording cleanup. The earlier 12 mocked component checks remain distinct evidence.

