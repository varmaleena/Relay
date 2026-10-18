# Constrained Pack Builder and Critic

`PackBuilderAgent(client).build(sources=..., jurisdiction_code=..., name=...,
archetype=...)` performs all five extraction passes with separate strict schemas:
recipients/channels, deadlines, remedies/liability, sequencing/forms, support.
Every nonempty chunk is independently checked by `PackCriticAgent`. The client uses
the existing async GoogleGenAIClient.generate interface; no tools are supplied.
Passages remain untrusted data separate from system prompts.

Input is at most 8 immutable sources and 24,000 extracted characters. Whole passages
are grouped into 12,000-character chunks and every chunk reaches every pass; larger
inputs fail explicitly, never truncate silently. At most 12 candidates per pass,
20s per call and 180s overall are defaults. A structured validation failure or an
empty/blocked response gets at most one same-input retry within the same bounded
attempt budget. Timeouts, transport failures and 429 fail without an internal retry
burst; parent durable orchestration owns any later backoff.

`ImmutableSource` requires canonical Source metadata, passage text SHA256, exact
page-text offsets and the T29 extractionHash of the complete supplied passage list.
The agent verifies these proofs before calling the model, then validates exact
quotes, reference sets, source slices, numeric tokens and exact contact values.
Metadata raw SHA256 is a trusted caller input: parent must load the immutable private
snapshot and verify that hash before constructing this DTO. Partial passage subsets
cannot reuse the complete source extraction hash; they fail proof checks.

The critic emits only SUPPORTED, PARTIAL, UNSUPPORTED or CONTRADICTED and must bind
each verdict to exactly the candidate and evidence refs. Non-supported items carry
a missing-support explanation. Unsupported/contradicted candidates are excluded
from usable output while retained as reviewer findings; contradictions and vague
wording remain visible. Every item, including SUPPORTED, remains unverified and
requires a human review. Deterministic checks plus a model entailment label do not
prove legal correctness, authenticity or applicability.

Result is a draft extraction/review artifact, not a published/executable Pack.
Canonical Pack lacks evidence-span/conflict/critic fields and E32 lacks currency and
timezone; this module does not invent them or erase provenance to force conversion.
Parent mapping must supply reviewed jurisdiction metadata and preserve this evidence
sidecar. No reviewer identity, acceptance, review timestamp or publish action exists
in this module. A support contact in a draft is not user-facing verified guidance.

Use `GoogleGenAIClient.for_packbuilder()` for the spec's explicit 8,000 output-token,
temperature 0.1 profile across the five extraction schemas and CriticOutput. It shares
the underlying SDK client, single-attempt HTTP transport (15s), and concurrency bucket;
there are no extra tools, retries or relaxed 20s/180s agent deadlines. Intake and
packet profiles retain their existing settings. This profile is unit tested against
an injected SDK; actual output quality and latency at these settings remain unmeasured.
Larger realistic sources, live quality, provider reliability/cost, human review,
Pack Studio persistence, publish gates and publication remain separate work.
Tests are synthetic model fixtures, not actual model-quality or attack-resistance
measurements. No live inference or cloud actions were executed for this slice.
