# Packet agent boundaries (M3)

`PacketPipeline.build` returns typed content/checks/attempts/status/model/prompt_versions.
`PacketVerifier.verify` rechecks edited content using keyword-only trusted context.
`prepare_content` is a server-only pure helper for persisted, legitimate missing-field
confirmations. It updates only those fields/provenance and computed completeness;
it never silently replaces a known amount, edited prose, footer or citation.

The writer emits only bounded prose. Canonical fields, completeness, citations,
attachment manifest and versioned footer are server-built. Missing required values
remain blank; explicit unavailable values remain not_available and require review.
No template exception permits storing full account/card credentials.

Deterministic checks run before entailment. The latter requires exact indexed
sentence coverage of summary/message, plus accurate victim copy and requested
actions, and returns per-sentence check IDs. Initial generation plus at most two
repair attempts is allowed. Provider/schema/timeout failures fail closed. Generated
credential content is never returned to persistence, even as an unsuccessful draft.
No network retries, hidden recovery batches, external tools or sends occur here.

These controls are not comprehensive semantic DLP or proof of truth. Numeric currency
and ISO timestamp checks catch explicit typed forms; arbitrary natural-language
claims, names and translated numbers still rely on fallible model entailment.
Draft sources remain visibly unverified even when a packet's factual checks pass.

`packages.packets.pdf.render_packet_pdf` exports real ReportLab PDF, with full
separately labeled victim-language copy. Noto Sans Devanagari/OFL and uharfbuzz
provide Hindi shaping. Missing dependencies/fonts/glyphs fail explicitly. Visual
inspection of `.tmp/pdf-review/bilingual.png` confirmed no clipping or missing
glyphs; this is not fluent human translation approval. Hindi PDF text extraction
can differ from the source logical character order because glyph shaping alters
text placement/mapping; searchable accessible PDF remains an open improvement.

Offline verification after diagnostics/profile refinement: 34 packet tests; 156 together
with intake/classification. One authorized live smoke produced1/3 verified packets;
see tests/fixtures/packets/LIVE_SMOKE_REVIEW.md. Original reports are frozen. The opt-in `smoke.py`
harness requires explicit authorized execution, synthetic facts and an actual
three-recipient plan. It caps all requests at 18, retains unique reports and records
available SDK usage without fabricating monetary cost.


## Diagnosable packet profile (not yet live-evaluated)

GoogleGenAIClient.for_packets() shares the original SDK transport and semaphore.
The writer uses2500 output tokens/temperature0.3; verifier uses2000/0.0.
Settings.packet_thinking_level (PACKET_THINKING_LEVEL) optionally enables LOW
only for verified gemini-3.8-flash. Intake/classification defaults remain unchanged.
The pinned SDK exposes ThinkingConfig/ThinkingLevel.LOW. Official model guidance
supports LOW/MEDIUM/HIGH and excludes MINIMAL:
https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-8-flash
https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash

No thinking_budget guess or timeout increase was introduced. The HTTP deadline
remains15s, outer call20s. LOW may reduce reasoning latency but has not been
measured on these packets. It is not a verified remedy for unknown failures.
A proposed separately authorized follow-up would reuse the identical synthetic
facts/plan, opt into LOW, cap18 requests, save a distinct report/JSONL ledger and
retain every failed attempt. It must not overwrite or replace the1/3 baseline.

Typed ModelFailure.reason/status_code derive only from actual exception type or
HTTP status attributes, never error-message guesses. SDK usage and failures have
separate lists; missing usage is unknown. The smoke wrapper flushes each attempt
to an exclusive JSONL file with schema/stage/reason/status/latency/repair IDs and
available usage. No prompts, raw error prose, tokens or credentials are logged.
PacketBuildResult.attempt_history retains prior deterministic/entailment checks.
The baseline lacks this new ledger; its exact failure causes cannot be recovered.
