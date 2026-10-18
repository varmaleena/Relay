# Read-only serving preflight

18 October 2026. The operator uses this command to detect a broken serving
deployment before showing the demo. It does not replace the complete T40 pre-demo
checklist or establish a production readiness gate.

Run `python -m scripts.preflight --api <explicit-origin> --web <explicit-origin>
--output .tmp/preflight.json`. The parent task wires the same command through
`make preflight`. Allowed origins are loopback or the exact approved
work-511514 API and Hosting domains. Other project domains, credential-bearing
URLs, arbitrary paths, redirects and proxy configuration are rejected or ignored.
Only five public GET requests occur, each with a bounded timeout and response
size: API health, serving readiness, version, public configuration and Hosting.

Local checks compare generated contracts without writing them and validate the
explicit India/generic/UK source catalog. Saved phase-report presence is recorded
as an unvalidated artifact, never a passed acceptance test. Local integrity checks
do not claim that cloud configuration contains the same source build.
The known dataset and `eval/reports/offline-fixture-v1` report are also checked
only for presence. This is an offline evaluator self-test artifact, not measured
Relay/baseline/ablation performance or proof that a browser loaded an eval report.

The JSON report separates `servingChecksPassed` from `fullSpecGate: unknown`.
Enabled features are not exercised; disabled features are explicitly disabled.
Model configuration is not inference availability. Queue delivery, private
worker/A2A, seeded cases, mock adapter behavior, Live reply, evaluation report
loading, human language review and submission artifacts remain `not_checked`.
No auth token, private object path, response body or raw exception is written.
There is no reset, deployment, inference, test send or data mutation. Exit 1 means
a critical cheap check failed; exit 2 means invalid arguments. Exit 0 means only
these serving/integrity checks passed.

This supports the technical implementation judging criterion by making the
operator's next action clear, while retaining the boundary between availability
and demonstrated user value. Actual model reliability, Hindi/microphone testing,
outsider usability, load/resilience and full rehearsal evidence remain separate.

Validation: 21 injected-transport tests passed, including forbidden origins,
disabled features, unready/configuration-only dependencies, response bounds,
redacted failures, output confinement and a nonzero failing CLI result. Ruff
passed. No actual service/model requests were made by this test run.
The actual local read-only contract and catalog checks were also run: generated
contracts matched and all three explicitly registered draft packs passed source
integrity. This is not deployed-source or human-review evidence.
