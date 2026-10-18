# M2 one-pass live classification smoke

Actual run: 15 October 2026, report generated07:22:43UTC (12:52:43Asia/Kolkata).
Frozen record: `live_smoke_report.json`. Exactly20 provider attempts, no retries,
fallback model or replacement cases. ADC preflight refreshed successfully without
printing credentials. Evaluation clock remained2026-10-14T06:00:00Z for urgency gold;
actual run time is recorded separately.

Provider/configuration: Google GenAI Vertex backend, project work-511514, processing
location global, configured gemini-3.8-flash; google-genai2.30.1, google-adk2.11.0.
Actual ADK Workflow/FunctionNode/Runner coordinated classification, deterministic
resolution and planning. Maximum client concurrency2, this harness processes cases
sequentially; output cap2000, HTTP timeout15seconds, classifier outer timeout20seconds,
one HTTP attempt, zero schema retries. A separate local API call could run concurrently.
All inputs are synthetic; draft pack preview was explicitly local/unverified.

| All-case metric | Result | n | Wilson95% interval |
|---|---:|---:|---:|
| Authorization correct, failures counted incorrect |15/20 (75%)|20|53.1–88.8%|
| Typology correct, failures counted incorrect |14/20 (70%)|20|48.1–85.5%|
| UTC urgency correct, failures counted incorrect |15/20 (75%)|20|53.1–88.8%|

Outcomes:12plans,3genuine clarification outcomes,5failures. Exact recipient/order
checks passed12/12 completed plans; that is not20/20 pipeline success. All completed
plans retained unverified notices and no invented numeric deadline. Authorization and
urgency have strong deterministic controls; these metrics alone do not demonstrate
GenAI benefit. Baselines/ablations and independent human gold review remain future work.

Latency includes failures: mean8928.1ms; nearest-rankP95=15989.6ms, n20. The P95
exceeds the10second classification/plan target. This small run does not establish a
production SLO. Per-case latency is preserved; no failed/slow case was excluded.

## Failure diagnosis without further calls

Cases015,016,017,018,019 failed at **classification**, before resolution or planning.
All propagated sanitized ModelFailure/model_unavailable, at roughly15.29–16.01seconds.
ADK's root-node traceback records propagation of that error, not a demonstrated ADK
orchestration bug. No schema_invalid or unsafe_output failure was recorded in this run.

The times are consistent with the configured15second HTTP/network boundary. However,
the client/classifier collapses individual HTTP status and transport exception type to
model_unavailable. Thus this evidence cannot distinguish a client timeout, upstream504,
capacity/429 response or another provider/network error precisely. Calling all five
“504” or “quota exhaustion” would invent a cause. No provider diagnostics were rerun.

Case008 returned a valid plan but missed the synthetic typology gold. Its narrative
concerns promised crypto-investment profits; overlap between crypto and investment
labels warrants independent annotation review before broader conclusions. Predicted
typology labels were not retained in this report, so no particular wrong prediction
is asserted and no gold label is changed after the run.

The confusion table counts15 completed classifications; five provider failures are a
separate category in the outcome table and remain in every all-case metric denominator.
They correspond to expected authorized_manipulated2, unauthorized_access1,
card_unauthorized1 and unclear1. Future reports should include a failure column in
the matrix directly and retain safe predicted enum values, without raw model content.

## Usage and cost boundary

Returned usage:14118input tokens,8642output plus reported reasoning tokens. The recorded
assumption USD1.50input/USD7.50output per1M gives USD0.085992 **for reported usage**.
These are assumptions, not verified current prices or an invoice. usageIncomplete=true:
failed-call usage is unavailable and may still be billable. Infrastructure, concurrent
API traffic, FX, credits and taxes are excluded. No zero-cost claim is made for failures.

## Targeted follow-up, not concealed reruns

1. Preserve typed provider HTTP status/transport category and duration per attempt in
   server telemetry; test timeout/429/503/schema/unsafe paths with mocked transports.
   Do not log raw errors, headers, prompts or tokens. This would distinguish causes
   currently collapsed to model_unavailable; it would not retroactively diagnose this run.
2. Reduce classification response work by considering a compact internal model schema
   for typology, authorization assessment/conflict and confidence; continue constructing
   canonical urgency, rationale/provenance and server-owned failure fields in domain code.
   Verify any model-specific reasoning setting before using it. This is a latency
   hypothesis requiring a separately approved measurement, not a claimed improvement.
3. Do not merely increase deadlines to hide the miss. Keep bounded calls, explicit
   provider-failure UX and controlled worker backoff; validate under the actual region,
   quota and concurrency before retrying a future approved dataset version.
4. Strengthen independent gold review for overlapping typologies and retain predicted
   enum labels/error categories in future reports. Do not relabel this frozen report.

After this run, offline resolver regressions corrected GM (Gambia) being confused with
a generic sentinel: it now produces a known-country generic fallback, never India.
Malformed model country text such as India now requests confirmation via fallback,
while invalid explicit API country codes remain rejected. These narrow changes did
not alter the live fixtures/report or trigger any new model call. Sixty-three local
classifier/harness tests, Ruff and mypy passed after the fixes.
