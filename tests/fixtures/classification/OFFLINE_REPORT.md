# M2 offline ADK smoke

20 synthetic natural-language scenarios, configured facts, independent expected
labels/order and hand-authored fixture model responses. No real model calls were
made. This is pipeline/fixture consistency, **not measured AI classification accuracy**.

Actual pinned ADK Workflow/FunctionNode/Runner invoked classifier → resolver → planner;
PackRegistry verified the saved source snapshots/passages. Both constructor and
per-request local draft preview were explicitly enabled; all plan rules remain
unverified and no human pack review was fabricated.

The latest `offline_smoke_report.json` records20cases:16planned,4clarification;
authorization/typology/UTC-urgency fixture consistency20/20 each with n20 and Wilson
95% interval83.9–100%; exact recipient/order checks16/16. Mean/p95 latency and n
are the actual local fixture timings, not production latency or a Gemini SLO.
The report includes dataset/prompt hashes, raw confusion counts, outcomes/failures,
per-case checks and explicit fake-mode/claim-boundary labels.

Low classifier confidence no longer repeats who initiated an already recorded
payment: known self-approval asks what the person claimed/why money was requested;
known non-approval asks what activity was discovered; unknown authorization asks who
initiated. English/Hindi safety regressions cover these cases. Model failures remain
distinct degraded states with no redundant fact question.

First integration exposed ADK session.state being a dict rather than an object with
to_dict. Root corrected that adapter; the initial20AttributeErrors are preserved in
`offline_smoke_failed_state.json`. The earlier technical-label-input run is preserved
in `offline_smoke_technical_inputs.json`; current natural narratives avoid leaking
typology label strings into future model inputs. No live batch is authorized by this
script; its model client is deliberately FixtureClassifierClient.

60 local tests (56 classifier/resolver and4 harness) passed. Ruff and mypy passed for
classification/harness code. Tests needed Windows asyncio local socket access and a
workspace pytest temp directory because the preexisting system pytest folder denied
access. Root migrated the initial deprecated SequentialAgent wrapper to the current
ADK2.11 Workflow and FunctionNode graph; the current run has no deprecation warning.
No warning was suppressed or relabeled a deployment success.

The current India draft has bank/cyber/payment-app (last only for UPI). The helpline
phone and portal are channels on the same cyber recipient, rather than duplicate
institution steps. Gold order was updated before this run and remains unverified
pack-policy consistency, not a legal correctness claim.

All four expected-unclear cases now have genuinely missing transaction-specific
authorization, including the ambiguous multiple-payment case. Expected uncertainty
no longer depends on the fake client's confidence setting. Natural narratives and
independent gold are never forwarded as expected labels to a live model.

At the offline checkpoint, the explicit `--live --project ... --location ... --model ...`
branch had not been executed. One subsequently authorized batch is now preserved in
`live_smoke_report.json` and described honestly in `LIVE_REPORT.md`. It requires exactly20cases, refuses an
existing report target, caps calls at20, uses one HTTP attempt and zero schema retries,
sets max output2000 and client concurrency cap2. Model failures stay in denominators;
no fallback client/rerun occurs. The clock stays frozen at2026-10-14T06:00:00Z for
urgency gold while actual run time, hashes, provider/SDK/model/version and usage are
recorded separately. Missing provider token usage is labeled incomplete, and cost
is only an estimate excluding infrastructure/FX/unreported failures. Actual execution
required the root's separate authorization, which was obtained for that single batch.
