# M3 corrective review: user purpose and report handoff

Reviewed 17 October 2026. Authorized corrective scope only; M4 is not started.

## User and useful outcome

The intended primary user is a recently scammed person who needs an accurate
account, a proposed contact plan and recipient reports without repeating the
story. This build is a synthetic-data demonstration. Institution staff are a
separate future M4 user, not an implemented receiver workflow.

The main journey is now Tell us → Plan → Prepare report. Report review offers
copy and PDF download for inspection; self-submission through an official
channel is the intended product handoff. This demo explicitly warns against
filing fictional drafts. Relay cannot confirm submission performed elsewhere.

Optional simulated delivery is collapsed separately and retains recipient,
version, verification and approval guards. Demo updates describe simulated
receipts, not real institution progress. Existing backend contracts are unchanged.

## Changes and why they matter

- Report terminology and the three-step navigation expose the actual output.
- Copied drafts include exact structured fields, transaction references,
  requested actions, citations, footer and draft/demo warnings. A message body
  alone could omit details a recipient needs.
- Recipient-language labels stay consistent when the interface language changes.
- Recorded answers are read-only, with a correction link; missing fields remain
  editable. This matches the existing backend boundary.
- Privacy and consent say access expires after 72 hours. They do not promise
  browser-only storage or guaranteed automatic physical deletion.
- Contact order is described as proposed, with source and unverified labels.

## Verification actually performed

Twenty mocked report/Start browser checks passed, including English/Hindi
desktop/mobile accessibility, exact copied fields, collapsed simulation,
unchecked approval guards and no send operation on copy/download. Desktop money
regression passed; its existing mobile variant is intentionally skipped.
TypeScript, three content checks, formatting and production build passed.
The existing approximately 919 KB JavaScript chunk warning remains.

Screenshots are under `.tmp/ui-review/mocked-review-{en,hi}-{desktop,mobile}.png`
and `mocked-tracker-hi-{desktop,mobile}.png`. Root visually inspected the English
mobile report. This is automated/visual engineering evidence, not a human
usability study. No new model inference, deployment or institution contact was
performed. Earlier live-model failures remain in the phase reports.

## Judge and phase gate

BFSI fit and the durable handoff are defensible. This increment supports UX
clarity; it does not establish measured impact, provider reliability or complete
competition readiness. The deployed whole application, submission materials,
actual eligibility, human review and fresh live-generation gates remain open.
See [user/judge review](USER_AND_JUDGE_REVIEW.md) and
[ADR0007](../decisions/0007-user-first-report-submission.md).

At each next gate assess the user, job, understandable next action, usable
output, real/simulated boundaries, test evidence and official judging criteria.
Then obtain the project owner's approval for the next scope.

Recommended next checkpoint, pending approval: improve and measure reliable
live completion of the primary journey and close the minimal Google Cloud
deployment gate before expanding the optional receiver workflow. Preserve all
remaining source tasks; this recommendation does not silently remove M4 or later
requirements. Human Hindi and outsider comprehension checks remain pending.
