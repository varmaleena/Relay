# Source ingestion boundary

This slice implements reviewer/admin organization-scoped E29–31 and an authenticated
source upload PUT. It does not build, review, sign, publish or render a pack. Every
source remains `reviewStatus=unverified`. Publication needs its later explicit gate.

`OfficialFetcher` requires an injected explicit host allowlist. It checks every DNS
answer and every redirect, connects to a checked numeric IP without a second DNS
lookup, verifies the TLS hostname/certificate, rejects nonpublic addresses, credentials,
sensitive query keys, non-HTTPS/443 destinations, compression and unsupported MIME.
It accepts PDF, HTML and UTF-8 plain text up to 25 MiB, with bounded DNS concurrency,
redirect count, socket timeouts and 25s fetch budget. Tests inject all networking;
no official URL was fetched during this implementation. Runtime host allowlisting
must come from reviewed official domains, not an arbitrary reviewer-supplied URL.

Default parsing runs in a separate Linux process with 512 MiB address-space limit,
4 CPU seconds, 7s parent timeout, 200 PDF pages, 500,000 extracted characters and 400 passages.
Encrypted/image-only/malformed PDFs, invalid UTF-8 and content beyond these limits
are rejected. HTML active elements are removed before passage extraction; only plain
text is exposed by E31. Original snapshots stay private, are hashed and written once;
no original HTML/PDF preview/download endpoint exists. Credential patterns in extracted
text are rejected before snapshot persistence. This is not comprehensive image/PDF DLP
or proof that every source is authentic, current, legally applicable or human-reviewed.
Use only synthetic/public official source material under the existing project rules.

Windows default parser deliberately fails closed because an equivalent OS memory bound
is not implemented. Local tests used the real pure HTML/text extraction function via
explicit parser injection, not the production subprocess. Linux subprocess resource
limits, live HTTPS and actual GCS/Firestore ingestion still require deployment checks.

Parent integration:

- Instantiate `SourceService(repository, source_store, OfficialFetcher(reviewed_hosts),
  api_base_url=public_api_base)`, with `GoogleSourceStore(private_sources_bucket)` in
  cloud or `LocalSourceStore(private_directory)` in local environments. The shared
  intake BlobStore has 10 MiB limits and is intentionally not reused.
- Mount `create_source_router(service)` from `services.api.sources.router`. Preserve
  existing Firebase/App Check middleware; no static staff headers or public upload.
  Exempt only `/api/v1/sources/{id}/upload` PUT from the general 64 KiB JSON body limit;
  that handler authenticates first and streams its own 25 MiB cap.
- Add durable `pack_ingest` dispatch to bounded worker/PubSub/sweeper. It calls
  `await service.process(job_id)`. The job has `resourceId=sourceId`, reviewer uid and
  orgId. Extend job GET authorization to reviewer-org jobs without victim-case access;
  existing victim-only intake job authorization is insufficient for these new jobs.
- E29/E30 require UUID Idempotency-Key. Upload is immutable per source hash; ingestion
  completion atomically commits 400 or fewer passages plus metadata/job. A source stores
  at most 3 explicit ingestion job intents; active leases are respected before cap checks.
- Add necessary private source-bucket object permissions for API/worker runtime only;
  no public bucket access. No cloud resources or settings were changed in this slice.
- Operational source erasure/retention and Pack Studio UI are later integration work;
  this contract slice has no source DELETE endpoint. Do not claim whole M6 complete.
