# M7 / T33 bounded linking domain checkpoint

18 October 2026. This increment implements private deterministic linking logic,
not a completed M7 deployment. The receiver's job is to inspect a possible link
between reports already addressed to their organization and decide whether it is
related. Victims do not receive a criminality determination or raw identifiers.

Implemented: typed sightings, links and components; HMAC-SHA256 over
`type|normalizedValue`; source-defined normalization and type weights; minimum
shared-sighting time factor; 0.60/0.85 thresholds and 0.99 cap; components of at
least three; official-channel HMAC denylist; confirmed/edited scammer-side entities
only. Victim, merchant, unknown, extracted and unrelated identifiers cannot enter
the index. Shared amount, transaction reference, timestamp, currency, bank/app
name, claimed identity and unweighted routing codes cannot create links.

`LinkingService` accepts trusted approved-projection ingestion, persists hashes
only through the existing transaction repository, recomputes links/components,
and transactionally removes sightings and derived links/components on deletion.
The development materialization deliberately accepts at most 40 cases / 500
sightings. Both cases must already be addressed to the requesting organization.
No full victim case is read by receiver methods. No public route bypasses this
boundary. The explainer receives only case references, types, counts and time;
pointers and the human confirmation warning are server-generated. The injected
model has not been called; further semantic verification is required before
shipping arbitrary explanation prose.

Actual validation: 29 synthetic unit tests passed, including a six-case shared
beneficiary ring producing 15 links and one six-case component; wrong-role,
unconfirmed, excluded-type, official-channel, time-boundary, duplicate-type,
cross-organization and deletion negatives. These are deterministic fixture
assertions, not a measured real-world detection precision or recall evaluation.
Ruff and mypy checks passed for the owned modules.

Remaining integration: canonical shared E25/E26 response contracts and routes;
version-bound human validation/audit; runtime Secret Manager access to an actual
32-byte-or-longer secret (never a checked-in default); approved-projection
indexing hook; deletion hook in the same case deletion transaction; durable
compute_links worker wiring; actual BigQuery tables and parameterized ingestion,
retention/deletion reconciliation; linked-cases panel; real configured Google
model generation and verification, evaluation with n and confidence intervals.
No BigQuery, Secret Manager or model/cloud calls were performed here.

Parent hooks: `replace_case(case_ref, org_ids, entities, first_seen, country)` is
trusted-service-only and must receive only approved, current, confirmed scammer
identifiers. `cleanup_case(tx, case_ref)` must run before parent deletion commits.
`links_for(case_ref, org_id)` requires authenticated receiver claims checked by
API; returns sanitized snake_case domain records to map into canonical E25.
Do not expose the private index document or hashes to a receiver client.

BigQuery schema required by source: entity_sightings(sighting_id,case_ref,
entity_type,entity_hmac,first_seen,jurisdiction,typology,amount_bucket), partition
DATE(first_seen), cluster entity_type/entity_hmac; case_links(case_a,case_b,
shared_entity_types,link_strength,computed_at); clusters(cluster_id,case_refs,size,
entity_types,created_at,explanation,explanation_model); entity_denylist(entity_hmac,
reason,added_by,added_at). Raw values must never enter warehouse rows or logs.
This private development materialization does not substitute for these tables.

User/judge gate: technical contribution is privacy-preserving, interpretable
heuristic linkage; innovation/value evidence is limited to synthetic fixture
behavior. Simulation boundaries remain explicit. No human usability, fraud
operations review or live network detection claim is made.

## T34 receiver API/domain increment

`ReceiverLinks(linking, clock=...)` and `create_linking_router(service, rate_limiter)`
now implement E25/E26 using the existing canonical API DTOs. The list reads only
the private HMAC index plus `receiverViews/{org}/cases/{id}` and its latest packet;
it never reads a full victim case. Both pair members must have an active,
non-deleting, non-deleted parent and approved delivered projection addressed to
the authenticated receiver organization. Stale or undelivered packets are hidden.

The returned opaque linkId includes the organization, heuristic pair and both
current packet version/contentHash/status/plan/facts-revision proofs. This avoids
a shared-contract change for an E26 proof field: an old linkId fails 409 after
any such projection update. E26 requires a UUID Idempotency-Key and explicit
related/not_related decision. Request hashes bind actor, organization, pair
proof, decision and optional note. Replays do not duplicate the audit; conflicting
reuse fails 409. Active projection proof is checked before replay, so deletion
or expiry cannot resurrect a result. Private audit stores only a hash of optional
review notes, never raw free text. Cleanup removes the case's reviews and request
records along with its sightings/links/components.

The public explanation is deterministic metadata text explicitly saying possible
link, heuristic, no identity/wrongdoing conclusion and human confirmation. It is
not described as generated by Gemini. Public pointers are the two case references
plus the shared types, never HMACs or raw values. No shared canonical files were
edited. EN/HI linked-panel text remains a frontend integration task.

Actual checks: 44 combined linking tests passed (29 domain/explainer + 15
receiver/HTTP tests), with canonical DTO validation, six-case ring, receiver/victim/
admin/other-org checks, expired/deleted/deleting/stale projection negatives,
changed version/contentHash/status races, UUID enforcement, idempotent replay,
conflict, note-secret rejection and deletion of review evidence. Ruff and mypy
passed for owned source modules. Tests use MemoryRepository/TestClient and synthetic
records; no live Firestore, Secret Manager, BigQuery, Google model or browser
acceptance was run for this increment.

Parent integration requirements:

1. Root verified existing `phonenumbers==9.0.41` runtime pin (installed version used here).
2. Retrieve at least 32 random secret bytes from Secret Manager at startup under
   a resource-specific secretAccessor grant. Inject Hasher(key, reviewer_denylist),
   then LinkingService(repository, hasher), ReceiverLinks(linking). Never log key,
   raw identifier or HMAC; no fallback hardcoded key.
3. Mount create_linking_router(receiver_links, existing_rate_limiter) before the
   E25/E26 contract-only fallback and omit those operation stubs when enabled.
   Existing Firebase/App Check middleware must construct Actor claims.
4. Trusted ingestion supplies `replace_case(public_case_ref, approved_org_ids,
   confirmed_scammer_entities, aware_first_seen, country, case_id=internal_id)`.
   Entity dictionaries use type/value/role/status; the optional wallet flag
   caseSensitiveWallet defaults true. Never accept org_ids from request JSON.
   Indexing must run only after a current approved delivery; revoke old scopes
   and invalidate receiver projections when facts/plan/approval change.
5. Call cleanup_case(tx, public_case_ref) inside the case deletion transaction.
   API and worker must resolve the same secret/denylist and private index.
6. Limits now 40 cases/500 sightings and 300 review requests. This explicit
   bounded development service still needs BigQuery + durable compute_links;
   do not call it source-complete M7 or silently reset/delete old reports.

Projection-proof limitation: this service knows only receiver projections.
The parent must invalidate them when underlying facts or plan change; reading
full victim documents in the receiver handler would violate its privacy design.


Trusted invalidation integration: IntakeService._event now invalidates known receiver
projections in the same case mutation. An actual local MCP-approved send followed
by update_facts test passed; stale anchor E25 returns409, active other-member
E25 omits the pair, and E26 with the old ID returns409. This is local synthetic
flow evidence, not a deployed browser claim. The standalone invalidation helper
is tested but is not required by runtime because the trusted central hook owns it.


## T34 linked-cases panel checkpoint

`RelatedCases.tsx` is ready for parent mounting with injected E25/E26 client,
caseId and required scopeKey (`uid:orgId`). The panel shows scoped references,
shared types, heuristic scores/bands and deterministic localized evidence text.
It explicitly states that a possible link does not establish identity, wrongdoing
or a criminal network. The server's arbitrary explanation prose is not rendered.

Related/not-related choices open an accessible confirmation dialog; only its
explicit confirmation creates a UUID-bound POST. A synchronous click lock blocks
duplicate submissions. POST never retries automatically. Stale409 closes the
confirmation and requires manual GET refresh; safe GET429 honors Retry-After.
English/Hindi keys were added only under related-prefixed names, with responsive
wrapping and minimum44px review controls. Parent must mount only when the feature
is enabled and authenticate the receiver; the component never implies it does so.

Actual results: TypeScript passes; three content/i18n checks pass; eight injected-
client Playwright tests pass on desktop/mobile, covering explicit confirmation,
double-click prevention, UUID payload, stale409/manual refresh/no POST retry,
GET429 recovery, denied and empty states, English/Hindi, horizontal overflow,
and zero serious/critical automated axe violations. Hindi mobile screenshot
`.tmp/ui-review/related-mobile-hi.png` was visually inspected for wrapping.
Initial browser attempt failed because main local5173 was not running; final
checks used an isolated Vite5174 fixture preview. These are component fixture
checks, not live staff-auth/browser/backend/cloud or human usability evidence.

`replace_case(..., tx=existing_transaction)` now permits pure hashing/materialize
in the approved-delivery transaction without nested transactions. Runtime
Secret Manager, feature flag and trusted delivery/deletion hooks remain owned by
the parent integration; BigQuery and live ClusterExplainer remain open.
