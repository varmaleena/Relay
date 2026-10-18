# M2 classification and planning: review record

15 October 2026, Asia/Calcutta. Scope T14–T19. Local S4 flow works; model
reliability and latency targets are not yet met. M3 is not authorized.

## Implemented

E10 queues durable planning; E11 exposes job state; E12 reads an owned,
proof-bound plan; E13 explicitly reprocesses. Firestore transactions enforce
owner checks, idempotence, claim tokens, leases, bounded retries and deletion.
Worker pagination prevents deferred jobs from starving later records. New facts,
statements, evidence or catalog changes invalidate prior analysis.

The actual ADK Workflow runs classification, jurisdiction resolution and a
deterministic rule engine. Unknown authorization/country asks for clarification;
transport failures remain failures. Authorized manipulation and unauthorized
access have separate classifications. No funds-location claim is inferred.

S4 displays ordered stations, contact channels, source passages, elapsed time,
draft/unverified notices and stale-plan warnings. No packet or send flow is
implemented. Local draft preview requires configuration gates and an explicit
unchecked checkbox. Both initial packs remain unpublished with blank reviewer
records. Official snapshots and integrity-checked passages are in
`docs/pack-sources/`; source review is pending. No numeric legal deadline is
invented from draft guidance. See ADR0005 for decisions and deviations.

The paired amount/currency editor requires explicit currency and preserves exact
decimal strings. Its no-charge browser regression saves and reloads
`123456789012.12345678 GBP`; an earlier test above the canonical 12-whole-digit
limit was corrected, without weakening credential controls.

## Observed verification

- Main suite: 491 passed, four emulator-dependent tests skipped in that run;
  existing package/service coverage gates passed, combined coverage 86%.
- Separate actual Firestore run: all four M1/M2 integration tests passed.
  With checkpoint and active-third-lease regressions: 15 passed.
- Ruff, formatting, mypy (56 source files), generated/application TypeScript,
  contract drift, three content checks and production build passed.
- One live S4 browser flow passed in 20.4 seconds: real anonymous Auth, one
  confirmed-facts API patch, one E10 request, three India recipients, 1930 and
  portal display, sources, reload, stale warning after edit and deletion.
- English/Hindi UI on desktop/mobile had no serious/critical axe findings or
  horizontal overflow in that flow. Screenshots:
  `.tmp/ui-review/plan-{en,hi}-{desktop,mobile}.png`. Toggling UI language retains
  stored case-language plan prose; this does not establish live Hindi plan quality.
- Real local emulator export succeeded; rotating checkpoints are ignored local
  files. Older unexported cases from the interrupted emulator were not recoverable.

Build reports an 873 KB minified JavaScript bundle (265 KB gzip); profiling and
code splitting remain open. Subsequent focused regressions are recorded in the
checkpoint; these counts describe the commands actually run, not a summed total.

## Live model smoke: target remains open

Exactly 20 provider requests, no schema retries, no hidden reruns or fallback.
Vertex `work-511514`, global endpoint, `gemini-3.8-flash`, SDK google-genai2.30.1
and ADK2.11.0. The urgency evaluation clock is deliberately frozen at
2026-10-14T06:00:00Z; the actual report was generated 15 October.

| Observation | Result |
|---|---:|
| Outcomes | 12 plans, 3 clarifications, 5 failures |
| Authorization correct, all attempts | 15/20; Wilson 95% CI 53.1–88.8% |
| Typology correct, all attempts | 14/20; Wilson 95% CI 48.1–85.5% |
| Urgency correct, all attempts | 15/20; Wilson 95% CI 53.1–88.8% |
| Recipient order among completed plans | 12/12 |
| Mean / p95 latency, all attempts | 8.93 / 15.99 seconds |

All 15 completed classifications had correct authorization; one had a typology
mismatch. Five failures occurred at the classifier model/transport boundary,
around 15–16 seconds. The original generic error did not preserve an HTTP status,
so timeout, 504 and throttling cannot be distinguished from this record. No
schema/unsafe-output/orchestration failure was identified in these five records.
The 10-second p95 target is missed. This small synthetic sample is neither
production accuracy nor an SLO. Failures stay in the denominator.

Reported usage: 14,118 input and 8,642 output/reasoning tokens. USD0.085992 uses
recorded, unverified pricing assumptions; usage is incomplete and excludes
unreported failed usage, infrastructure and FX. Frozen evidence:
`tests/fixtures/classification/live_smoke_report.json`. No additional live
batch is implied by later offline fixes.

## Remaining gate

Review the local UI at http://127.0.0.1:5173 with synthetic details. Reliability
and latency need a separately measured follow-up before claiming their targets.
Human source/legal, fluent Hindi and privacy review remain open. Full application
cloud deployment, project quotas and production backup verification remain open;
the earlier private Cloud Run smoke is not an application deployment. Do not
describe M2 as finalist-ready or proceed to M3 without the user's next phase review.
