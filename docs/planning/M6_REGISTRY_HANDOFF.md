# M6 registry increment

18 October 2026. This increment serves two users: a victim selecting a jurisdiction
and a reviewer managing a published guidance version. It does not perform human
review or publish checked-in drafts.

`PackRegistry.register_known("uk")` explicitly registers the known nested UK
pack and its separate source manifest. Arbitrary directories are never scanned
recursively. The UK material remains draft and requires the existing local/dev
synthetic preview policy. Public metadata omits reviewer notes and identifiers.

`StudioCatalog(source_service)` optionally reads existing Studio registrations,
immutable versions and retirement tombstones. It loads at most 50 registrations
and 20 versions each; an overflow rejects the catalog rather than serving a
partial list. Every usable version rechecks private source snapshots, extraction
and passage hashes, the persisted build and human review decisions, the checklist
and canonical publication mapping. Invalid stored evidence rejects the catalog
without including private error details. Retirement removes availability and
rejects a previously selected version's proof. No model calls occur in the reader.

Runtime integration belongs to the parent: call `registry.register_known("uk")`
when constructing the configured registry, then set
`registry.studio_catalog = StudioCatalog(service.sources)` after creating the
source service when Studio is enabled. Planning should bind its current catalog
proof to `registry.catalog_hash(**selection_options)` and use `registry.proof(pack)`
for selected-version proof; do not hash only root YAML files. Keep source storage
private and provide its existing read permission to API/worker identities.

Planning and packet services now use the source-bound registry catalog proof at
enqueue, read, pre-generation, partial checkpoint and final commit boundaries.
The catalog-only proof consistently uses the workflow's configured preview
authorization; serving a draft still requires the original request opt-in.
This avoids immediately invalidating a published selection merely because other
drafts are visible to that configured demonstration. The selected pack's original
canonical pack hash remains unchanged. Plans created with the old catalog hash
must be explicitly regenerated; no stored approval or plan is silently migrated.
Invalid source evidence marks a displayed plan stale and blocks packet creation.

Final validation: 53 focused offline tests passed across the existing registry,
durable/UK, planning and packet service tests, with a harmless pytest cache
permission warning. Ruff and mypy passed for all four changed source files.
Synthetic publication fixtures are
explicit test actions, not evidence of actual review. Tampering tests cover
snapshot bytes, passages, canonical pack content, human reviews, checklist and
organization binding. Retirement, catalog bounds, an actual fixture published
plan becoming stale after retirement, and copied-source snapshot tampering tests
passed. The failed preliminary run used partially updated hash consumers; the
complete final run passed after every consumer was migrated.

This supports the technical implementation and generality judging criteria.
Actual hosted Studio publication, a genuinely reviewed fourth pack, human legal
and Hindi review, and outsider comprehension remain unverified. Registry checks
establish structural/source consistency, not legal accuracy or human usability.
