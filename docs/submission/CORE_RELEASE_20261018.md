# Core development demo release

18 October 2026. Stable demo: https://work-511514.web.app . This is a
development prototype, not a production or legal-guidance release.

## Deployed and observed

Restricted build 7276c6e1-9eaa-4ba6-b2a8-deee3820742f, 159 allowlisted files,
fingerprint 810d3e5daf6073373c3389cd20d6e877a0715bf891c0b099361fceaea9f256f7.
API relay-dev-api-00012-hoz and private worker relay-dev-worker-00009-buv
passed tagged probes and received 100% development traffic. Hosting published.
Serving preflight passed; its full-spec gate remains unknown.

The real hosted browser test ran 06:22:35–06:24:37 UTC (11:52:35–11:54:37 IST).
It used normal anonymous Firebase authentication and App Check, real API,
Firestore jobs, model transport and signed Cloud Storage. No responses were
mocked. Three UI actions requested intake, planning and report generation.
The resulting three reports were VERIFIED with 23, 32 and 31 checks respectively,
all passing. A signed export returned PDF bytes. Both synthetic cases were
deleted with HTTP 204. No delivery was approved or real institution contacted.

Security checks rejected missing credentials, missing App Check and a different
owner. Reload retained confirmed facts. Signed evidence PUT passed; evidence
processing was intentionally not enqueued by this smoke.

Evidence: ignored .tmp/cloud-browser-core-r5/result.json and synthetic-report.pdf;
.tmp/preflight-core-r5.json; .tmp/core-rollout-r5.json. Focused core regression:
91 passed in 92.14 seconds using a fresh workspace temp directory. The prior
attempt had 50 passes and 41 fixture setup errors because Windows denied the
default temp folder; no product assertion failed in that attempt. Python/TS,
Ruff and generated contract checks passed.

## Limits and phase gate

This is one synthetic scenario in one live run, not an achieved availability,
accuracy or latency target. Earlier hosted failures and quota errors remain in
the evidence history. Provider attempt count was not measured by the browser.
The run does not validate Hindi, physical microphone use, general scenario
coverage, human comprehension or institution acceptance. Automated verification
does not establish human legal review.

The primary user is a person organizing a scam incident. The job is to confirm
facts, review a source-linked draft plan, and prepare a report for self-submission.
Copy/PDF does not file a complaint. Receiver, bank, police and rail results remain
simulated. Source guidance remains visibly unreviewed draft content.

Voice, sources/Studio, UK pack and linking flags remain false in this release.
Eval Lab and Demo Control components/backend increments are not mounted as
completed hosted features. M5–M10 still have integration and human gates;
this release does not mark every milestone complete or promise finalist selection.
Official competition eligibility, exact cutoff and submission acceptance must be
confirmed in the owner's portal. No fresh judging-criteria verification is claimed.

Next: human rehearse the core flow, record the demonstration, review deck/README,
verify repository/video visibility and submit through the competition portal.
Preserve this known working release while preparing remaining artifacts.
