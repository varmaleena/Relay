# Synthetic dataset and evaluator card

Version: `synthetic-templates.v1`. Seed: `20261018`. Created 18 October 2026.
Dataset hash: `01687b303189ec0078dd1f39522a610207d139454aff89b5ae585dfd395e7015`.

This is an offline engineering corpus, not observed fraud, human-reviewed legal
gold, product-impact evidence or a representative estimate of scam prevalence.
No model generated these templates. No provider was called for the evaluator
fixture report. The original live intake, classification and packet reports under
`tests/fixtures/` remain separate, unchanged historical evidence, including their
failures and missed latency targets.

## Composition and generation

The default 528 cases cover the complete Cartesian product of four jurisdiction
slots, three language labels, eleven typology scenarios and four authorization
types. Each jurisdiction has 132 cases, each language 176, each typology 48 and each
authorization type 132. There are 318 text cases, 158 text-plus-screenshot templates,
and 52 simulated voice-transcript cases. Voice transcripts are text only, with no
audio or speech-recognition measurement.

The jurisdictions are India, UK, generic fragmented, and a live-built-pack slot.
The 132 live-built-pack cases are held out, have no recipient gold, and the runner
refuses to evaluate them until a real pack/gold version is prepared. The remaining
396 are eligible engineering cases. Current pack-file hashes are embedded in the
dataset; changing a pack requires a deliberately regenerated dataset version/hash.
No source material is quoted or regulatory obligation invented by the generator.
Recipient expectations reflect the current draft engineering routes only; they
are not signed legal truth. No numerical deadline gold is supplied.

Noise counts: 106 clean, 184 typo, 106 missing-reference, 105 crop/low-quality, 27 conflicting-
authorization. Conflict cases are restricted to unclear authorization so the four
authorization classes remain balanced. There are 76 hostile-evidence text variants
(including held-out cases). These have explicit expected refusal-to-follow-evidence
behavior; a real red-team outcome still needs captured outputs and an identified
behavior scorer. Their existence is not a measured injection-resistance result.

All banks, contacts, merchants and transaction references are fictional. Contacts
use reserved `.invalid` domains. Entity gold contains normalized(type, value, role)
tuples for victim, scammer, merchant and unknown roles. Case IDs, seed, stable hash,
source-pack hashes and a deterministic review sample are recorded. No real names,
account credentials, PINs, OTPs or card numbers are generated.

Hindi and Hinglish labels currently describe short authorization narration
fragments within surrounding English scenario/evidence templates. They are draft,
mixed-language engineering material, not a validated natural Hindi benchmark.
Full factorial combinations can be implausible; no real-world distribution claim
is made. Templates are repetitive and may leak simple patterns. Crops are mild;
there is no claim of difficult OCR coverage. Hard-coded template labels are not
model answers, but scenario wording can make the intended typology obvious.

## Screenshot evidence

`render_screenshots.mjs` renders local HTML into PNGs using Playwright, with a
fictional app skin, rotated cards, optional blur and a small bottom crop. Network
requests are blocked.158 PNGs and corresponding per-case gold files were actually
rendered under ignored `.tmp/eval-screenshots-v1/`; their SHA-bound manifest is
tracked at `datasets/v1/rendered-screenshot-manifest.json`. Generated PNGs are not
committed; rerun the command below to reproduce them. The dataset's original
`imageAssetStatus:template_only` is unchanged; use the rendered manifest to verify
which local assets exist. Compression randomization and broad device/font variety
remain unfinished. A first rendered image was visually inspected; this does not
establish image quality across all 158 or model extraction accuracy.

## Human review and split discipline

No person performed the required 10% plausibility/language review. `manifest.json`
contains a seeded 53-case sample and explicitly says pending. No legal reviewer,
Hindi reviewer or review signature is inferred. Evaluation cases are not model
training examples, but templates are not a robust hidden benchmark. The held-out
live-built pack slot must not be used as if its gold already existed.

## Evaluator and confidence intervals

`captures.py` defines strict bounded Pydantic capture records: system, execution
mode, model/prompt/config identity, dataset hash, cases, budget, declared repeats,
and actual attempt outcomes. Captures may record completed, failed or timed-out
attempts. Missing planned observations are synthesized only as missing failures,
never as successful model results. Unknown cases, duplicate attempts, invalid
completed/failure payloads, held-out cases and dataset drift are rejected.

Classification accuracy, entity micro-F1, recipient recall, pairwise order and
known expected field correctness retain failed/missing observations in their
relevant denominators. Recipient precision uses actual predicted recipients; an
empty set has no precision denominator. Field correctness is not full packet
completeness/faithfulness, and extra hallucinated fields require a separate audit.
Recipient/type strings in paired samples are allowlisted; failure galleries expose
only synthetic case IDs, static reasons and safe error categories, not raw inputs,
provider errors or credentials.

Proportions use Wilson 95% intervals. Entity F1 uses seeded percentile bootstrap of
whole case clusters, keeping repeats together. Paired authorization differences
also resample whole paired cases. Fairness checks require matching declared cases,
model, budget, mode and repeats; a comparison claim requires at least three
actually observed repeats per case. Metadata matching is not an independent audit
of how a caller executed its model. Wilson units can be correlated across fields,
recipients and repeated attempts; these intervals do not prove independent
population coverage.

Latency and supplied USD cost use only actually known measurements, with unknown
counts visible. Failures with known latency remain in the latency distribution.
Missing usage is not zero cost and no full-run cost is inferred. Behavior metrics
require an identified scorer; unscored/failed attempts are unknown, never safe
successes. Deadline correctness, sentence faithfulness, citation validity, gold
Pack Builder comparison and human faithfulness audit remain not measured.

`reports/offline-fixture-v1` scores 20 deliberately canned evaluator-test attempts:
17 completed, 2 synthetic timeouts and 1 missing observation, including an intentional
wrong authorization/entity tuple. These are calculator regression results, not
Relay or provider quality. Relay, baseline and all ablations are explicitly not
measured. No general guidance baseline, real ablation execution, fixed judge/parser
prompts, three-repeat model study, 100-sentence human audit or comparative product
claim was completed by this increment. Normalized paired samples also do not
replace the required 20 free-text side-by-side human review examples.

## Reproduce

From the repository root (Windows uses `.venv/Scripts/python.exe`):

```text
python -m scripts.evaluate synth --output eval/datasets/v1
python -m eval.offline_fixture eval/datasets/v1/cases.json eval/fixtures/offline_capture.v1.json
python -m scripts.evaluate score --dataset eval/datasets/v1/cases.json --captures eval/fixtures/offline_capture.v1.json --output eval/reports/offline-fixture-v1 --commit-sha YOUR_ACTUAL_COMMIT
node eval/render_screenshots.mjs eval/datasets/v1/cases.json .tmp/eval-screenshots-v1
python -m pytest tests/unit/test_evaluation_foundation.py -q
```

Set `PLAYWRIGHT_BROWSERS_PATH` to the installed local browser bundle when needed.
These commands make no cloud or model calls. Baseline/ablation quality must come
from separately budgeted, actual recorded executions; the scorer does not invent
or run them. Do not present this card as completion of all T35/T36 requirements.
