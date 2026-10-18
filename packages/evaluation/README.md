# Read-only evaluator evidence

`EvaluationService(root, public_eval=False)` exposes only the immutable
`offline-fixture-v1` report. Its fixed repository-relative path and pinned SHA256
are a catalog entry, not a user-controlled file lookup. A changed or missing
artifact fails closed with a redacted 503. No capture files, source text, raw
predictions or credentials are exposed. Replacing this entry requires an explicit
code/catalog review; running a new evaluation does not publish it automatically.

E37 list and E39 sanitized failures require a verified reviewer/admin actor.
E38 requires the same actor unless the parent explicitly enables `public_eval`;
the main API's Auth/App Check middleware must exempt only that exact known report
GET when enabled. The list and failure gallery remain authenticated. E40 checks
admin authorization and returns 501 because no bounded execution job is wired.
No evaluator/model job is silently simulated.

The report is an offline canned evaluator self-test, with n=20 planned attempts.
Relay, baseline and all three ablations remain `not_measured`, n=0. Per-metric n,
value and confidence bounds are copied exactly from the report. They are never
summed across metrics, correlated repeats or systems. Missing latency/cost and
unmeasured citation/deadline/Pack Builder results remain null/not measured.
The typed `captureReport` projection retains model/prompt/config/build and data
hash provenance, metric statuses, uncertainty methods and limitations. Failure
pages show only fixed synthetic case IDs and bounded known reason codes;
expected/actual values and input references are withheld.

Parent integration: instantiate the service with the application source root,
mount `create_evaluation_router(service)` only under its feature configuration,
and explicitly stage only the allowlisted report file. Add optional typed
`captureReport`, `runId` and `executionMode` fields to canonical `RunReport` and
regenerate contracts before using the router. UI must label the offline fixture
and show product systems as not measured.

This serves reviewers/judges inspecting what has actually been measured. It
supports reproducibility/transparency, without claiming model quality, population
impact, human usability or a complete M8 evaluation gate.

The parent explicitly deferred mounting this router in the core deployment.
Canonical additive RunReport fields and generated contracts are implemented;
they do not enable the feature. Validation: 12 evaluation API/domain tests and
22 preflight tests passed together (34 total), including actual FastAPI response
validation, roles, public opt-in, immutable artifact tampering, pagination,
withheld failure content and admin-only 501 execution. These are offline tests,
not cloud or model evaluations.
