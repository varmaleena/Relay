# Synthetic captured-output evaluation

Dataset: `synthetic-templates.v1` / `01687b303189ec0078dd1f39522a610207d139454aff89b5ae585dfd395e7015`.
Generated: 2026-10-18T06:01:19.684410+00:00. Commit: `uncommitted-offline-eval-foundation`.

This scores supplied captures; it does not execute Relay, a baseline or an ablation.

| System | Mode | Metric | Value | n | Unknown | 95% CI |
|---|---|---|---:|---:|---:|---|
| relay | not measured | — | — | 0 | — |
| baseline | not measured | — | — | 0 | — |
| ablation_rules | not measured | — | — | 0 | — |
| ablation_no_verifier | not measured | — | — | 0 | — |
| ablation_no_pack | not measured | — | — | 0 | — |
| offline_fixture | captured_offline | typology_accuracy | 0.8500 | 20 | 0 | [0.6396, 0.9476] |
| offline_fixture | captured_offline | authorization_accuracy | 0.8000 | 20 | 0 | [0.5840, 0.9193] |
| offline_fixture | captured_offline | entity_f1 | 0.9174 | 118 | 0 | [0.8041, 0.9957] |
| offline_fixture | captured_offline | recipient_recall | 0.8286 | 35 | 0 | [0.6732, 0.9190] |
| offline_fixture | captured_offline | recipient_precision | 1.0000 | 29 | 0 | [0.8830, 1.0000] |
| offline_fixture | captured_offline | order_pair_accuracy | 0.7895 | 19 | 0 | [0.5667, 0.9149] |
| offline_fixture | captured_offline | packet_field_correctness | 0.8571 | 56 | 0 | [0.7426, 0.9258] |
| offline_fixture | captured_offline | forbidden_content_rate | 0.0000 | 17 | 3 | [0.0000, 0.1843] |
| offline_fixture | captured_offline | injection_success_rate | 0.0000 | 3 | 0 | [0.0000, 0.5615] |
| offline_fixture | captured_offline | deadline_correctness | not measured | 0 | 0 | — |
| offline_fixture | captured_offline | packet_faithfulness | not measured | 0 | 0 | — |
| offline_fixture | captured_offline | citation_validity | not measured | 0 | 0 | — |
| offline_fixture | captured_offline | pack_builder_f1 | not measured | 0 | 0 | — |
| offline_fixture | captured_offline | latency_ms | not measured | 0 | 20 | — |
| offline_fixture | captured_offline | cost_usd | not measured | 0 | 20 | — |

## Limitations

- Synthetic template data, not human plausibility reviewed or representative prevalence.
- Draft-pack recipient gold is an engineering expectation, not independently reviewed regulatory truth.
- Unobserved planned attempts remain failures for accuracy/F1/recall/completeness.
- Unknown behavior annotations, latency and usage remain unknown; known-subset values are not full-run totals.
- Wilson intervals describe scored units; repeated attempts/fields are correlated and do not establish independent population coverage.
- F1 and paired differences resample whole cases; baseline fairness needs same cases/model/budget and at least three repeats.
- Deadline, faithfulness, citation and Pack Builder results require separate actual reviewed annotations.
