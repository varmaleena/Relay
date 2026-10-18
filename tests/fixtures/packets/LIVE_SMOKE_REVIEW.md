# M3 packet live smoke - 15 October 2026

One authorized batch, n=3 synthetic packets, Gemini 3.8 Flash / Vertex global,
google-genai2.30.1. Classification was a labeled fixture; planning used the actual
ADK workflow, deterministic planner and integrity-checked local draft registry.
This was not live end-to-end classification.

- Verified: 1/3; descriptive Wilson95% interval [0.061, 0.792].
- Bank verified after3 writer attempts: 58.453s.
- Cyber writer/provider unavailable: 12.109s.
- Payment-app writer/provider unavailable: 12.266s.
- Mean packet latency 27.609s; nearest-rank p95 58.453s,
  n=3 (not a reliable production tail estimate). No low-latency target claim.
- Provider attempts7, generic recorded provider failures3, SDK usage records4.
- Observed usage only: 7369 input, 1271 output,
  3062 reasoning tokens. Failed requests without SDK usage are
  missing, not zero. No verified monetary cost is available.

The frozen report retained only final checks and generic model_unavailable codes.
Consequently, exact HTTP/error causes and superseded repair checks cannot be
reconstructed. The failed writers were provider failures, not successful drafts
with omitted fields. No429/schema/timeout cause is asserted without evidence.
The bank's earlier repair causes were not retained. This is an instrumentation gap;
future runs need per-attempt stage/error/check ledgers before authorization.
No hidden fallback or rerun occurred. A Settings preflight failure made zero model
calls and is separately recorded in preflight_diagnostic.json.

Only the bank content can seed the UI as a real generated smoke artifact. Failed
packets must remain visibly failed; do not fabricate replacements or relabel
fixtures as successful model output. Draft source labels remain unverified.

Offline27 packet tests and149 combined intake/classification/packet tests passed.
The bilingual PDF was regenerated with the simulation banner and visually checked.
Hindi logical text extraction under glyph shaping remains a documented limitation;
fluent translation review has not occurred.
