# M1 intake/evidence validation report

Date: 14 October 2026. Scope: T12 only, no M2 classification/planning/delivery.

## Local checks

- 58 synthetic agent unit tests passed; Ruff and mypy passed for `agents/`.
- Twenty hand-authored synthetic cases contain ten English and ten Hindi narrations,
  each with a known generic English receipt. Fake fixtures test intake partial deltas,
  required facts, safe first action, and evidence shape/source consistency.
- Additional tests cover distress bypass, credential redaction before prompting,
  injection annotation, malformed schema retry/fallback, forbidden MIME, multimodal
  byte framing, sensitive/incomplete-image safety rejection, provider projection,
  client concurrency semaphore, and model deadline handling.
- Windows sandbox `asyncio` initialization blocked on its local socketpair; tests ran
  with explicit escalation for local socket access. Test models remain fake; this is
  not an external network or real-model test pass.

## Actual live evidence smoke

Configuration: Gemini `gemini-3.8-flash`, ADC-backed Google GenAI SDK 2.30.1,
project `work-511514`, model processing endpoint `global`, no tools or retrieval,
2000 output-token cap, at most two concurrent calls, 20-second outer deadline,
15-second HTTP timeout, one HTTP attempt, zero schema retries. Input is synthetic
English text receipts; selected reply language includes Hindi. This does **not** test
Hindi screenshot OCR, microphone audio, broad multilingual robustness or real data.

The successful one-case probe plus nineteen remaining distinct cases form the run.
No failed case was rerun or replaced to improve results.

| Measure | Observed result | n | Wilson 95% interval |
|---|---:|---:|---:|
| Cases returning schema-valid and text-source-checked output | 19/20 (95%) | 20 | 76.4%–99.1% |
| Cases containing all three exact required raw tuples | 10/20 (50%) | 20 | 29.9%–70.1% |

Case `SYN-INTAKE-002` failed with HTTP504. The test recorded and surfaced that
failure without retry; it is part of the denominator. Latency SLOs are not established
by this smoke. Failed-request usage is unavailable, not assumed zero cost.

Returned usage totals from successful calls: 15,758 input tokens and 17,165 output
plus reported reasoning tokens. A conservative calculation using the recorded global price assumption
(USD1.50 per million input, USD7.50 per million output/reasoning) yields USD0.1523745
for those **reported** tokens. It excludes unreported failed-call usage, diagnostics,
infrastructure, exchange rates, credits and taxes; billing remains authoritative.
The source is the official platform pricing page linked in PLATFORM_VERIFICATION.md.

The UI dictionary translation was a separate authorized call: 112 keys, 1,827 input
and 2,174 output tokens, no reported reasoning tokens. It remains a draft pending
fluent human review. Automatic checks preserved keys/types/array lengths/placeholders.

## Metric definitions and interpretation

`schema_and_source_validated_cases` means Pydantic accepted the bounded output,
entity types were allowed, every extracted raw value was a substring of the supplied
text, and deterministic secret/output checks passed. It does not prove all claims
are entailed, all visible facts were extracted, or images are safe.

`all_three_required_raw_tuples_present` requires exact `(entityType, rawValue)`
matches for transaction reference, synthetic payee UPI ID, and scalar amount in the
fixture. A case passes only if all three tuples appear; a failed request fails this
case-level metric. The gold contains only these three required tuples, while valid
outputs commonly contain six entities. Thus this is **not complete entity F1**.
The strict scalar-amount match may penalize currency-bearing raw amount strings;
this is a plausible format issue, not a proven cause, because raw model results were
not retained in this bounded report. Do not rename this score to normalized accuracy.

For a subsequent approved evaluation, define normalized matching before running:
UPI IDs are trim/lowercase; references trim whitespace while preserving identifier
case; monetary values are exact `Decimal` plus explicit currency code; timestamps
are timezone-aware UTC; phones use country-aware E.164; roles match independently.
Gold and predictions then compare typed normalized tuples. Amount normalization must
retain currency and avoid floating-point equality. The canonical M8 F1 includes
entity type, normalized value, and role and requires complete independently reviewed
gold. **No normalized score was measured in this run**; do not infer one from the
raw tuple result or regenerate a claimed result without another approved run.

## Structured-output integration decision for the root ADR

Direct canonical Pydantic `response_schema` and full `response_json_schema` requests
returned HTTP400 with the provider's generic invalid-argument message. A full
synchronous request also failed, excluding an async-only transport explanation;
simple native JSON Schema was accepted. The successful integration uses the native
`response_json_schema` field with an explicit provider projection: resolve `$ref`s,
omit defaults/titles/additional-property controls/length and numeric bounds, remove
optional spans and server-owned arbitrary provenance maps, and remove optional-null
unions. The model is not trusted with those omitted constraints: **canonical local
Pydantic validation, bounded lengths/counts, allowed entity types, secret rejection,
source checks and trusted provenance assignment still enforce them**.

Changing several representation features together demonstrated compatibility, not
which individual keyword caused the service rejection. Do not claim all omitted
keywords are universally unsupported. The projection is isolated in `provider_schema`
with a unit test; future SDK/model changes require schema-capability smoke and a
versioned decision before restoring additional provider constraints. No plaintext
unvalidated-output fallback, model downgrade or 2.x model was introduced.

The evidence model also returns internal `sensitiveContentDetected` and
`safetyScanComplete`. Secret detection or incomplete image/PDF inspection rejects
evidence before durable promotion, even when no secret entity is extracted. These
flags are conservative controls, not comprehensive visual DLP guarantees; screenshot
handling retains backend quarantine, decode/page/size checks and synthetic-only rules.

## Records

- `cases.json`: immutable hand-authored inputs/expected fixture responses.
- `live_smoke_report.json`: merged distinct-case results, n, intervals, prompt and
  dataset hashes, token/cost estimate and incomplete-usage marker.
- `live_smoke_supported_json_probe.json` and `live_smoke_remaining.json`: constituent
  actual live reports. Earlier diagnostic reports preserve schema failures.
- `hindi_translation_draft.json`: first-pass UI translation; human review pending.

This is M1 integration evidence. Full evaluation, safety claims, regression thresholds,
and performance targets require the later planned datasets, baselines/ablations,
multimodal tests, and human review. No reported target is substituted for a result.
