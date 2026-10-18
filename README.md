# Relay

Relay helps someone organize a scam incident, review a source-linked draft plan and prepare reports for self-submission. This AI Builder Cup prototype uses synthetic data only. Bank, police and payment integrations are simulated, and guidance remains visibly unreviewed draft material.

**Development demo:** https://work-511514.web.app . On 18 October, a real hosted browser run completed intake, planning, three VERIFIED reports and a signed PDF download. Authentication, App Check, owner isolation and cleanup were also checked. This single scenario does not establish general reliability or legal accuracy; earlier model quota failures remain documented.

The public [evidence and results page](https://work-511514.web.app/results) separates observed hosted checks from the offline calculator fixture and unmeasured comparisons. See [the priority increment outcome](docs/submission/PRIORITY_INCREMENT_20261018.md) for the raw demo recording, submission artifacts and the still-failing automatic voice fact-saving gate.

M0–M4 core features are implemented. Later voice, Studio, linking, evaluation and demo-control increments have local tests but retain integration and human-review gates; advanced cloud flags remain disabled. See [the current core release](docs/submission/CORE_RELEASE_20261018.md) and [submission handoff](docs/submission/TONIGHT_SUBMISSION.md). Downloading a report does not submit it or establish official acceptance.

## Local development

Use Python 3.12, Node 22 and Java 21. Dependencies are pinned in `requirements.lock` and `package-lock.json`.

```powershell
.\.venv\Scripts\python.exe scripts/tasks.py lint
.\.venv\Scripts\python.exe scripts/tasks.py typecheck
.\.venv\Scripts\python.exe scripts/tasks.py test
.\.venv\Scripts\python.exe -m scripts.export_contracts --check
.\.venv\Scripts\python.exe scripts/tasks.py build
.\.venv\Scripts\python.exe scripts/tasks.py dev
```

For a fresh environment, create a Python 3.12 virtual environment, then run `scripts/tasks.py bootstrap` with its Python executable. Equivalent Make targets are available on systems with Make. Future-phase targets fail explicitly until implemented.

Open http://127.0.0.1:5173. The development runner starts the web app, API, job worker and real Firebase Auth/Firestore emulators. Java 21 is required. Emulators store identities and cases locally under project `demo-relay-local`; actual Gemini calls use authenticated ADC and `work-511514`, with a separate model project override available through `GENAI_PROJECT_ID`. Chat, extraction and plan classification incur usage. Use synthetic data only. The first emulator start may download its official binary. The runner exports rotating checkpoints every 60 seconds and on graceful shutdown; abrupt interruption can lose newer data. Signed evidence files remain in ignored `.local/intake/`.

The UI supports English and a Hindi translation draft, consent, anonymous case creation, text intake, manual corrections, evidence, extraction confirmation, reload and deletion. To test M2, complete country, payment method, amount/currency, payment time, contact channel and whether contact continues. Confirm who authorized the payment. Explicitly select the local draft preview, then build the plan. Inspect its ordered recipients, source passages and unverified notices. Change a fact afterward to check the stale-plan warning. Initial packs await human review; the checkbox does not publish them.

`scripts/tasks.py e2e` requires the local stack and Playwright Chromium; default checks do not call a model. `RELAY_LIVE_E2E=1`, `RELAY_MULTITURN_E2E=1` and `RELAY_PLAN_E2E=1` separately enable paid synthetic intake, multi-turn and planning checks. Leave them unset for ordinary regression checks.

The API exposes health, readiness, version and public configuration. Readiness reflects the configured environment's dependencies; local availability does not establish cloud readiness. Deployed business routes require real Firebase ID tokens and App Check. The local emulator adapter omits App Check only with enforced local environment, demo project and loopback emulator settings; it does not accept a static identity header. The separate contract application defines future API operations as 501 stubs and is not mounted in the running API.

For M3, prepare **recipient reports** after building a plan and inspect their
facts/checks. **Submit yourself** offers copying/downloading a draft for use with
the recipient's official process. Neither action files a complaint or confirms
submission. A separate **Try simulated delivery** section demonstrates explicit
approval of a current verified version; only its mock ticket appears in demo
updates. Editing or changing facts revokes approval eligibility. No real
institution receives anything through Relay. The initial draft
rail pack has incomplete routing setup, so its receipt can correctly request more
information instead of claiming successful routing. See the
[M3 review record](docs/planning/M3_PHASE_REPORT.md) for measured provider failures.
Live recovery verified two of three recipients; artifacts from separate runs must
not be presented as a clean single-batch success.

The primary user is a recently scammed person organizing an initial response;
institution staff are a distinct future M4 user. Each phase requires a concrete
user/value/judge review before the next phase is approved. See
[the user and judge assessment](docs/planning/USER_AND_JUDGE_REVIEW.md). Automated
tests establish workflow behavior, not user comprehension or measured impact.

`python -m scripts.dev --without-worker` is a controlled local fixture mode: queued
inference remains paused. Tests that seed and process synthetic emulator jobs use
this mode to prevent accidental provider calls. Ordinary review uses the default
runner with its worker enabled. The helper is not a product API or identity bypass.

Firebase rules testing and IAM limitations are documented in [infra/README.md](infra/README.md). Authentication instructions are in [docs/cloud-auth.md](docs/cloud-auth.md). Credentials in `.local/` and tooling in `.tools/` are excluded from Git and must never enter images or build artifacts.

## Architecture and project record

The monorepo separates schemas, common utilities, deterministic pack rules, safety policy and model agents from service transport. The API owns authoritative writes and approval checks. Firebase client rules isolate victim records and receiver projections; server IAM is a separate boundary. Evidence and planning workers use transactional Firestore claims, leases and bounded retries. An ADK workflow coordinates classification, jurisdiction resolution and deterministic planning. Later services provide the Live gateway and simulated institutions.

Pydantic models generate JSON Schema, OpenAPI and the TypeScript client. Contract drift fails verification. Money preserves Decimal precision. Pack rules use a bounded AST interpreter, never Python eval. Missing facts remain unknown; business calendars and ambiguous daylight-saving deadlines require review. Pack publication requires passage provenance and a named reviewer.

Source documents, hashes, task IDs, independent reviews and the phase plan are preserved under `docs/sources/` and `docs/planning/`. See [the checkpoint](docs/planning/CHECKPOINT.md) and [the iterative plan](docs/planning/ITERATIVE_BUILD_PLAN.md). Decisions are recorded in `docs/decisions/`.

All institution adapters are simulated. Use synthetic fixtures only. Safety controls are not a claim of regulatory correctness or comprehensive detection. Official pack review, fluent Hindi review, broader model evaluation and complete deployed application verification remain required. The [M1 agent smoke report](tests/fixtures/intake/SMOKE_REPORT.md) preserves the observed 19/20 valid responses, one timeout, and 10/20 strict raw-field matches; this is not a normalized accuracy or entity-F1 result.
