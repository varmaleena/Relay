# M0 platform verification record

Date: 2026-10-13 (Asia/Calcutta). Scope: T03 read-only SDK/API inspection, primary documentation, and authorized ADC-backed publisher catalog discovery. No resources provisioned, raw credentials inspected/logged, billable model generation, or deployment smoke performed by this task. Documentation capability does not establish project entitlement, quota, or region compatibility.

## Reproduce the local inspection

```powershell
.\.venv\Scripts\python.exe scripts/verify_platform.py
.\.venv\Scripts\python.exe scripts/verify_platform.py --strict
```

The script imports installed modules and inspects parameter/schema names without creating clients, reading environment values, obtaining credentials, rendering default values, or calling remote APIs. It prints sanitized exception class names only. Non-strict mode prints unresolved capabilities and exits normally; strict mode fails on required symbol absence or foundational SDK lock drift. Its report is local evidence, never a deployment success report.

## Local evidence observed

| Dependency | Installed/lock | Result |
|---|---|---|
| google-genai | 2.30.1 / 2.30.1 | Match |
| google-adk | 2.11.0 / 2.11.0 | Match |
| Pydantic | 2.14.1 / 2.14.1 | Match |
| google-generativeai legacy | Not installed | Correct |
| mcp | 2.3.0 / 2.3.0 after tooling owner resolved extras | Match |
| a2a-sdk | 1.2.2 / 1.2.2 after tooling owner resolved extras | Match |

Confirmed importable: GenAI `Client`, `Models.list`, `Models.generate_content`, `AsyncLive.connect`; ADK `Runner.run_live`, `LlmAgent`, `SequentialAgent`, `ParallelAgent`, `LoopAgent`, `RunConfig`, `StreamingMode`; GenAI `LiveConnectConfig`, `SessionResumptionConfig`, `ContextWindowCompressionConfig`, and `GenerateContentConfig`.

Observed `LlmAgent` supports `output_schema` and input/state schemas. `LoopAgent` exposes `max_iterations`. `RunConfig` exposes response modalities, input/output audio transcription, session resumption, context compression, save-live-audio/blob controls, max-LLM-calls, and streaming mode. GenAI generation config includes response schema/JSON schema and Model Armor config. These field names only establish installed API shape; model/backend support still needs integration validation.

At initial inspection `McpToolset` and `StreamableHTTPConnectionParams` were absent from ADK's import surface and `to_a2a` failed import. Local installed package source contains those definitions but wraps MCP imports in optional ImportError handling. Installed ADK metadata declares `mcp>=1.24,<3` with the `mcp` extra and `a2a-sdk[http-server]>=0.3.4,<2` with the `a2a` extra. Tooling owner must resolve and pin compatible extras before strict verification passes. This task did not alter the lock or install packages.

Update: the tooling owner resolved the extras; repeat inspection confirmed all 18 required symbols available, including the MCP connection/toolset and A2A exposure function, with both optional package versions matching the lock. `--strict` now passes. Importing ADK reports its pluggable-auth feature as experimental; authentication interoperability remains untested.

## V1–V9 status

| ID | Confirmed evidence | Pending / next gate |
|---|---|---|
| V1 models | Official lifecycle and Live capabilities list current 3.8 generation models; documented 2.5 Pro retirement is 2026-10-20; actual work-511514/global publisher discovery returned gemini-3.8-flash | Minimal deployed generation still required to prove invocation; final workflow/live model roles need separate capabilities. No copied example model becomes a constant. |
| V2 SDK | Installed GenAI 2.30.1, ADK 2.11.0, MCP 2.3.0 and A2A SDK 1.2.2 match lock; modern SDK entry points available; legacy package absent | Validate schema/tool combinations against chosen model. JS GenAI version irrelevant until frontend voice integration actually uses it; browser should not hold model credentials. |
| V3 Live | PCM input/output formats and model-specific thinking configuration documented; local Live/resumption/compression/transcription types and `run_live` import | Verify Vertex/Agent Platform backend, session limits, reconnect handles, context policy, tool latency, Hindi behavior and actual browser audio; M5 safety-before-play experiment remains required. |
| V4 ADK/MCP/A2A | Local workflow constructors/schema fields, MCP toolset/connection and A2A exposure import confirmed after extras resolved; official Google docs support reference API | Authenticated transport/interoperability and deploy CLI still need tests. |
| V5 Model Armor | Mumbai is documented but limited-support residency region. Screening constraints materially conflict with “screen every upload” assumptions | Choose residency/filter design explicitly; no silent cross-region routing. Keep custom guard. Confirm service enabled and selected feature before integration. |
| V6 Search | Official current Discovery Engine quota table uses Global/US/EU locations, 100 total datastores, 150 engines, 300 regional search requests/min under default pricing | Search is not automatically Mumbai-resident. Choose permitted source-passage index fallback unless Search residency/budget decision approved; exact current project quota still unknown. |
| V7 region | Official guidance separates at-rest storage from ML processing and says global requests may process worldwide; root selected Mumbai stored data after user delegated choice | Validate every selected service/model region and preserve this distinction in privacy copy. Global model smoke is a separate processing choice. |
| V8 official facts | Official source candidates found for India helpline, UK reimbursement, Singapore framework | No pack authored, reviewed, or published in M0. Named human reviewer must verify precise passages, exceptions, versions/effective dates. Other draft/2026 modules/UK channel/Australia claims remain pending. |
| V9 quotas | Official quota documentation describes project/region/model quota checks and adjustment routes | Inspect actual project allocations, Live concurrent sessions, Cloud Run limits and Search quotas after authorized context; requests/increases remain separate account actions. Per-process semaphores cannot bound all replicas. |

## Primary-source details and implementation implications

Official Live capability documentation lists Gemini 3.8 Live and Extended Thinking, with default Live omitting `thinkingLevel` and Extended Thinking supporting distinct levels. It specifies raw 16-bit little-endian PCM, native 16kHz input and 24kHz output, and audio transcriptions. Process all parts of each event; transcripts are not a second response modality. Exact project backend support is not proven here. [Live capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities).

Without compression, documented audio-only sessions have a 15-minute limit and audio/video a 2-minute limit; resumption uses server-issued handles. Configure Relay's separate ten-minute application budget without assuming the model's connection lifetime. Reconnect/resumption and context compression are different concerns and require end-to-end tests. [Live session management](https://ai.google.dev/gemini-api/docs/live-api/session-management).

Model lifecycle documentation currently names replacements and retirement dates, but project discovery and pinned configuration are still required. Do not substitute preview availability for production guarantees. [Model lifecycle](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions).

Current ADK guides show `Runner.run_live` with `RunConfig`/streaming mode and `to_a2a` for exposure; the codelab shows `McpToolset` and streamable HTTP configuration. These are reference shapes, not proof that optional packages are installed. [ADK Live configuration](https://github.com/google/adk-docs/blob/main/docs/live/configuration.md), [ADK A2A exposure](https://github.com/google/adk-docs/blob/main/docs/a2a/quickstart-exposing.md), [Google MCP/A2A codelab](https://codelabs.developers.google.com/getting-started-mcp-a2a-adk?hl=en).

Model Armor documentation lists Mumbai, with limited feature support under residency enforcement; broader filters may require routing outside that jurisdiction. This must be an explicit choice, never a fallback hidden from the user. [Model Armor locations](https://docs.cloud.google.com/model-armor/locations), [residency](https://docs.cloud.google.com/model-armor/data-residency?hl=en).

Model Armor document screening skips files over 4MB; Relay allows 10MB. Images require supported JPEG/PNG/BMP, ≤4MB, single-image requests, and US/EU multi-regions; WEBP and images embedded in PDFs are not automatically covered. Audio/video are unsupported. Hindi is not among its explicitly tested injection-filter languages. Therefore Model Armor cannot establish full bilingual multimedia protection, and skipped/failed screening must never be interpreted as allow. Disable content logging and keep transcript/OCR custom checks plus synthetic-only quarantine policy. [Model Armor overview](https://docs.cloud.google.com/model-armor/overview?hl=en).

Search defaults are shared with Gemini Enterprise services using Discovery Engine, so default published values are not remaining account quota. Data-store location choices must be evaluated separately from Firestore/Storage. No Search resources or pricing subscription created. [Search quotas](https://docs.cloud.google.com/generative-ai-app-builder/quotas).

The global model endpoint provides no geographic processing guarantee, while chosen at-rest storage remains a separate property. Report these independently; do not claim Indian processing solely from `GCP_REGION=asia-south1`. [Model residency](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/data-residency?popup=false).

Model/project quota documentation is a reference to the procedure; actual allocations remain unavailable until inspected in the authorized project. Record selected region/model, request/token limits, Live concurrency, observed 429 behavior, and deployment limits before load testing. [Platform quotas](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/quotas).

## V8 source candidates, not approved pack content

- India: PIB July 2026 release confirms helpline 1930 and discusses NCRP/CFCFRMS. This is a candidate source; pack authoring still requires stable passage snapshots, source hash and named reviewer. [PIB release](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2290377&lang=1&reg=3).
- UK: PSR PS24/7 states £85,000 Faster Payments per-claim ceiling from 7 October 2024. Older official news still states £415,000, illustrating that official provenance alone does not establish latest applicability. Use the final instrument and relevant amendments/exceptions, not a stale press release. [PS24/7](https://www.psr.org.uk/publications/policy-statements/ps247-faster-payments-app-scams-reimbursement-requirement-confirming-the-maximum-level-of-reimbursement/), [consumer protections](https://www.psr.org.uk/information-for-consumers/app-fraud-reimbursement-protections/).
- Singapore: MAS lists SRF implementation from 16 December 2024 and describes phishing-scam scope. Do not generalize it to all manipulated transfers. [MAS scam framework](https://www.mas.gov.sg/regulation/combatting-scams).

RBI draft compensation/window status, MuleHunter count, restoration/grievance modules, UK current reporting channel/RCMS details, Singapore helpline, and Australia's commencement remain unverified in this task. No generated legal rules, reviewer signatures, or measured accuracy claims are provided.

## Acceptance status

Local import inspection completed and reported initial optional dependency failures accurately; after tooling resolved extras, strict inspection passes with no missing symbols or lock drift. Ruff and mypy pass for both scripts. Authenticated publisher discovery now passes; deployed hello-world remains pending. Successful imports or catalog retrieval cannot satisfy the deployed M0 exit gate.

## Read-only cloud discovery and proposed minimal smoke

`scripts/list_models.py --project <project-id> --location global` uses ADC and the GenAI Vertex backend, `Models.list(query_base=True)`, explicit v1beta1 publisher catalog API, request timeout and single-attempt retries. Page size is bounded 1–100, pages 1–10 (default three), timeout 1–30 seconds. It prints model name/version, supported actions and token limits only; it never prints access tokens, model descriptions, page tokens, raw exceptions, or generated text. Failure output exposes only exception class, integer HTTP code and whitelisted uppercase status. Listing is not inference, and a publisher catalog listing does not prove the caller can invoke a model. Help, invalid-page bounds and mock pagination/no-inference were exercised locally.

### Actual discovery and fixed API mismatch

After root enabled the API, the original explicit `v1` catalog request returned sanitized `ClientError`, HTTP404 and no service status string. No error body/headers were printed. Google's official publisher catalog list method is documented under `v1beta1/{parent}/models`, where parent is `publishers/google`; this differs from stable v1 generation calls. Changed the discovery script only to `v1beta1`. [Publisher list REST reference](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1beta1/publishers.models/list).

Authorized actual discovery using workspace ADC (`CLOUDSDK_CONFIG=.local/gcloud`) against project `work-511514`, location `global`, max one page: **exit0; 28 publisher entries; one page; truncated=false; no inference**. The catalog includes `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, and `gemini-3.1-flash-lite`, alongside image/transcription/preview/older models. Capability and token-limit fields were null, so the catalog cannot establish multimodal/tool/Live support or current generation access. Older 2.x catalog entries do not override Relay's exclusion of them. `gemini-3.8-live` was not returned in this catalog; its future access requires a separate documented Live probe.

The issue was the catalog API-version mismatch, evidenced by failure under v1 and success under v1beta1 without changing auth/project/region. No alternative model is needed for the tiny smoke candidate; retain configured `gemini-3.8-flash`, then test actual invocation from Cloud Run. A region-specific catalog query is not a processing-residency guarantee.

For the actual deployed smoke, recommend configured `gemini-3.8-flash` with model location `global`, while Cloud Run and stored demo data use `asia-south1`. Google's current Vertex developer guide explicitly lists this ID as GA and provides its global endpoint. Use one tiny synthetic text prompt, no tools/retrieval, tightly bounded output, and explicit timeout. Do not silently use 2.x or a preview fallback if access fails. [3.8 Flash developer guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-8-flash).

The current price table lists global text input/output at USD0.75/USD3.75 per million tokens through 2026-12-31 and USD1.50/USD7.50 from 2027-01-01; plan conservatively using the latter and record actual usage, reasoning tokens, and billing rather than asserting an exact tiny rupee cost. Root selected an INR1000 total target through submission, which is a target rather than a cloud hard cap. Minimum instances and runtime infrastructure can dominate the model smoke. [Dated platform pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing).
