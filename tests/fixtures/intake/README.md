# M1 synthetic intake fixtures

`cases.json` contains 20 hand-authored synthetic narrations (10 English, 10 Hindi),
paired with generic Test Bank text receipts and explicit expected fields. All names,
identifiers, amounts, references and transaction times are invented. Receipt text is
English; Hindi narrator input and selected response language do not establish Hindi
OCR or image reading quality. Receipts are text-only, not screenshots.

FixtureModelClient returns these hand-authored expected responses in explicit fake
mode. Passing deterministic fixture tests is implementation evidence, not measured
model accuracy. Expected tuples are only a subset of visible receipt information;
strict raw-field matching can penalize an amount returned with its currency prefix.
It must not be reported as complete entity F1, screenshot accuracy, or fraud detection.

`live_smoke_supported_json_probe.json` and `live_smoke_remaining.json` together record
the 20 distinct-case live extraction run on 2026-10-14. Nineteen cases produced valid,
source-checked output and one returned HTTP504 without retry. Diagnostic probe files
preserve earlier schema integration failures, rather than overwriting failure history.
Failed requests with no returned usage are not assumed free. Model-cost estimates
exclude infrastructure, exchange rates and unreported usage; billing remains the
authority. Full evaluation with synthetic dataset versioning, all systems/ablations,
multimodal inputs and human audits belongs to M8.

`hindi_translation_draft.json` is a Gemini-generated first-pass UI dictionary (112
keys, source file apps/web/src/locales/en.json), model gemini-3.8-flash, generated
2026-10-14, input1827/output2174 tokens. Key sets, value types, array lengths and
double-brace placeholders were automatically checked. Fluent human review is pending.
No reviewer signature or suitability for real victims is asserted.
