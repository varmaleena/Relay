# Pack Studio durable service

`PackStudioService(source_service, PackBuilderAdapter(model_client))` is an isolated
reviewer-org service. Mount `create_packstudio_router(service)` and dispatch
`await service.process(job_id)` for `pack_build` jobs through the existing trusted
worker. Authentication/App Check remain the application middleware's responsibility;
the router additionally requires a verified reviewer/admin Actor with an organization.
No model is constructed by this module.

The service verifies private raw snapshot SHA256 and the complete extracted passage
hash before constructing immutable agent DTOs. Build metadata and source proofs are
bound again at commit. Five progress stages reflect actual builder pass transitions;
a failed job never produces an executable pack. E33 returns full strict candidate
bodies, immutable source references/evidence spans, model verdicts, revision, human
reviews and publication blockers. `evalVsGold` remains null: no gold evaluation is
claimed merely because a goldPackId was supplied.

Mutations require UUID idempotency keys scoped to actor, organization and route;
different bodies cannot reuse a key. E34 and E35 require the exact current revision.
Editing preserves candidate ID and complete evidence proof and cannot reuse the
original model critic's SUPPORTED label to claim verification. Accepted unsupported
items must remain unverified, with explicit acceptance at publication. All human
review decisions are audited; the model cannot review or publish its own output.

Publication requires an explicit canonical `packDraft`, all review decisions, named
human reviewer and notes, and four explicit true checklist values. The caller must
supply currency, timezone, languages, disclaimers, applicability and scope conditions;
missing conditions are rejected before canonical model defaults can insert `True`.
Channels and rule fields must match reviewed source candidates. Unknown recipient
field mappings and secret credential fields are rejected. Crisis contacts require a
supported, unedited, explicitly reviewed mapping. Pack validation runs before an
immutable `packs/{packId}/versions/{version}` document and evidence sidecar are saved.
Retirement writes a separate tombstone; it never rewrites published version bytes.

## Explicit integration gaps

- The existing filesystem PackRegistry must be connected to durable published pack
  versions and retirement tombstones before a newly published pack is selectable.
  The Studio API by itself does not make a pack available to victim planning.
- Upload-only source metadata has no official URL in the current source contract.
  Such a source fails `source_metadata_required`; no official URL is invented.
- Canonical form field mappings cannot yet be reconstructed safely from natural
  language sequence `formFields`. Publication with forms fails
  `explicit_form_mapping_required`. A reviewed, typed mapping must be added before
  claiming the complete form-authoring workflow.
- Runtime must inject `PackBuilderAdapter(model.for_packbuilder())` for the explicit
  8,000-token/temperature 0.1 extraction and critic profile. This profile is tested
  offline; actual quality and latency are unmeasured.
- No actual model, cloud worker, human source/language review, realistic gold-pack
  evaluation or live publication was executed for this slice. Synthetic tests prove
  service trust boundaries and orchestration, not regulatory correctness.
