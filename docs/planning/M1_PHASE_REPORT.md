# M1: intake and evidence — phase review

Date: 14 October 2026, Asia/Calcutta. Scope: T10–T13 and minimal evidence worker
support pulled forward from T14. Status: local implementation verified and ready
for user review. Full application deployment and finalist readiness remain open.

## Working review build

Open http://127.0.0.1:5173 on the development machine. The API runs on port 8000,
Firebase Auth emulator on 9099 and Firestore emulator on 8095. Local cases and
identities belong to `demo-relay-local`; actual Vertex Gemini inference uses
`work-511514` with `gemini-3.8-flash` at the `global` processing endpoint. Storage
is an ignored local signed file store. This URL is a local review link, not the
competition's deployed submission URL. Synthetic data only; model calls incur usage.

Implemented: English/Hindi consent and anonymous sessions; safe first-action guidance;
text intake with model-extracted facts; editable confirmed facts with revision checks;
real signed uploads; MIME/decode/page/size/hash validation and quarantine; durable
extraction jobs with leases and bounded retries; evidence confirmation/edit/unrelated
decisions; reload persistence; owner isolation; deletion cascades and privacy limits.
Future classification/planning is explicitly unavailable (E10 returns 501).

## Verification

| Check | Actual result |
|---|---|
| Complete Python regression | 376 passed, one opt-in emulator test skipped in the ordinary run |
| Separate actual Firestore emulator test | 1 passed; replay, restarted repository durability, stale revision conflict and deletion |
| Coverage gates | Packages 89.5%; services 75.5%; combined packages/services/agents about 85% |
| Python lint/format/types and dependency consistency | Passed; 69 files formatted, mypy 45 source files, pip check clean |
| Contract export drift and TypeScript | Passed; generated contracts and complete web app |
| Web content/translation shape/contrast tests | 3 passed |
| Production web build | Passed; one 855KB minified bundle warning remains for later performance work |
| Final real browser run | 4 passed, 2 intentional duplicate-inference mobile skips |
| Desktop/mobile English/Hindi accessibility | No serious/critical axe findings; overflow checks passed |
| npm high/critical audit gate | Passed; 5 moderate Firebase CLI transitive advisories remain |

The final browser flow used real emulator-issued anonymous tokens and two deliberate
live model calls, with no mocked API: consent → case → text facts → confirmed bank
correction → synthetic PNG receipt → signed PUT → worker extraction → UPI confirmation
→ reload → separately issued nonowner denial → deletion → Start screen. Earlier
aborted runs remain part of the development record; they were not reported as passes.

The initial browser run found a rate-limit problem: polling exhausted the normal
30/minute budget before deletion. The backend now counts each request once, reports
precise retry delay and uses a separate bounded deletion allowance. A regression
proves owner deletion succeeds after the read budget is exhausted while a nonowner
is denied. Frontend subscriptions also coalesce redundant case refreshes.

Visual review found harmless warning text being redacted by the credential scrubber.
English/Hindi trusted warning punctuation was corrected; the scrubber was not weakened.
Worker tests verify active-lease/backoff deferral, expired-work resumption, isolation
of malformed/failed jobs, and no raw error contents in logs. API tests verify bounded
64KiB declared/chunked JSON bodies, upload's independent limit and secret-key privacy.

## AI evidence and open quality gaps

The [saved agent smoke](../../tests/fixtures/intake/SMOKE_REPORT.md) contains 20
distinct synthetic text receipts: 19 schema/source-validated outputs and one HTTP504.
Only 10/20 matched all three expected raw-field tuples exactly. No normalized
accuracy or complete entity F1 was measured; those results must not be invented.
The reported successful-call token estimate is about USD0.1524, excluding unknown
failed usage, other diagnostics, infrastructure, exchange rates, credits and taxes.
The browser PNG success is a functional multimodal check, not an OCR benchmark.

Before finalist readiness, remaining work includes the subsequent approved phases,
reviewed source-grounded guidance, simulated handoff with human approval, reliable
deployment, broader normalized and multimodal evaluation, and submission artifacts.
The Hindi dictionary is a Gemini-assisted draft pending fluent human review; axe
does not replace screen-reader/usability testing. Visual secret flags are conservative
controls, not a comprehensive DLP claim. Full cloud Firebase/GCS signing/quotas and
readiness remain pending; `/readyz` still honestly returns 503 for unverified cloud
dependencies. ADK orchestration is planned in the workflow increment, not claimed
as implemented by current direct SDK intake.

## Review steps

1. Open the local UI, select English or Hindi, and read the consent.
2. Use a made-up narration, for example: “Synthetic demo: I am in India. I paid
   INR 45000 by UPI twenty minutes ago to safe.verify@fakebank. A fake Test Bank
   security caller contacted me by phone. I made the payment myself and contact
   has stopped.” Do not enter real identifiers or credentials.
3. Check and correct extracted facts. Upload the saved synthetic receipt at
   `.tmp/ui-review/synthetic-receipt.png`, then confirm or edit a detail.
4. Reload to check persistence, switch language, and delete the report.

Screenshots: `.tmp/ui-review/{start,intake}-{en,hi}-{desktop,mobile}.png`.
Implementation decisions: [ADR0004](../decisions/0004-intake-runtime-and-model-boundaries.md).
The original source documents, hashes and all 43 tasks remain preserved. M2 awaits
the user's phase review; no classification/planning approval is inferred from this
implementation report.

## User-review correction: multi-turn omission

The user supplied a three-message case in which INR45000 and a UPI recipient were
stated, but omitted from persisted structured facts. Later currency-only input could
not recover omitted data because the agent saw only the latest text and known facts.
This valid partial omission was not deterministically reproduced in a three-call
diagnostic replay; no Money-schema failure is claimed. The new history-aware v2
prompt receives six bounded, sanitized prior user statements and original arrival
times. It can recover explicit missing facts while confirmed corrections remain
protected; model failures now explain retry/manual entry.

Verification: 148 targeted intake/privacy/safety regressions passed. The exact
three-message live browser replay passed in a fresh synthetic case: INR45000 and
recipient were present after messages2/3, no repeated amount question occurred,
confirmed bank correction/reference/reload/deletion passed. It used three UI
requests; underlying SDK attempt count was not measured. The user's existing report
was left unchanged. [Diagnostic record](../../tests/fixtures/intake/HISTORY_REGRESSION_REPORT.md).
