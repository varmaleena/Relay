# Task traceability

Source: build spec Section 18.8. All tasks retained. Status: not started; awaiting plan approval.

| ID | Task | Lane | Depends on | Milestone |
|---|---|---|---|---|
| T01 | Repo, tooling, CI skeleton, Makefile targets | IN | none | M0 |
| T02 | GCP setup script, service accounts, buckets, Firestore, Pub/Sub, BQ DDL | IN | T01 | M0 |
| T03 | Resolve V1–V9; `list_models.py`; record decisions | AG | T02 | M0 |
| T04 | Pydantic schemas, JSON Schema export, TS types | BE | T01 | M0 |
| T05 | OpenAPI from Section 14.2; TS client generation; drift check | BE | T04 | M0 |
| T06 | Settings, logging, ids, hashing, i18n helpers | BE | T01 | M0 |
| T07 | Pack validator, expression evaluator, deadline math (with tests) | BE | T04 | M0 |
| T08 | Firebase Auth, roles, App Check; Firestore and Storage rules with emulator tests | IN | T02, T04 | M0 |
| T09 | SafetyGuard v0 and ActionPolicy; output filter patterns (en, hi) | AG | T04 | M0 |
| T10 | Design tokens, fonts, base components, Flow Rail, i18n scaffolding | DS/FE | T01 | M1 |
| T11 | `api`: cases, facts, messages, uploads, evidence endpoints (E1–E11) | BE | T05, T06, T08 | M1 |
| T12 | EvidenceAgent and IntakeTextAgent; fixtures | AG | T03, T04, T09 | M1 |
| T13 | Victim S1, S2, S3 screens | FE | T10, T11 | M1 |
| T14 | `worker` skeleton, job handlers, idempotency | BE | T02, T04 | M2 |
| T15 | ClassifierAgent, JurisdictionResolver | AG | T12 | M2 |
| T16 | Rule engine (PlannerAgent core) | BE | T07, T15 | M2 |
| T17 | Author `pack_generic_fragmented` and `pack_in_cyber_rail` from official sources, with review records | DA | T07 | M2 |
| T18 | Plan endpoints (E12, E13) and Victim S4 | BE/FE | T16, T17 | M2 |
| T19 | Eval smoke harness: 20 hand-made cases, metrics skeleton | EV | T15 | M2 |
| T20 | PacketAgent, VerifierAgent loop, PDF export | AG/BE | T16, T17 | M3 |
| T21 | Packet endpoints (E14–E21), Victim S5 and S6, notifications inbox | BE/FE | T20 | M3 |
| T22 | Mock MCP servers (bank, rail) with simulation rules | BE | T04 | M3 |
| T23 | Send, track, deadline watcher | BE | T21, T22 | M3 |
| T24 | Receiver Console S7, console endpoints (E22–E24), ReceiverBriefAgent | BE/FE/AG | T23 | M4 |
| T25 | A2A receiver; needs-info loop (E19); audit panel | BE/AG | T24 | M4 |
| T26 | `live-gateway`, IntakeLiveAgent, audio worklets, captions, resume | BE/FE/AG | T12, T09 | M5 |
| T27 | Distress protocol and tests | AG/QA | T26 | M5 |
| T28 | `pack_uk_reimbursement` authored and reviewed; jurisdiction switch | DA/FE | T18 | M6 |
| T29 | Source ingestion with SSRF protections; passages index | BE | T04 | M6 |
| T30 | PackBuilderAgent, PackCriticAgent; build endpoints (E29–E36) | AG/BE | T29 | M6 |
| T31 | Pack Studio S9 (stepper, split source view, publish gate) | FE | T30 | M6 |
| T32 | Pack Builder evaluation vs gold pack; pre-built fallback pack | EV/DA | T30, T17 | M6 |
| T33 | Entity hashing, BigQuery sightings, links, clusters, ClusterExplainer | BE/AG | T14 | M7 |
| T34 | Linked cases panel S8 and validation endpoint (E25, E26) | FE/BE | T33, T24 | M7 |
| T35 | Synthetic generator (cases, screenshots), dataset v1, dataset card | EV | T19, T17, T28 | M8 |
| T36 | Systems: baseline, ablations; metrics with CIs; red-team set | EV | T35 | M8 |
| T37 | Eval Lab S10 and endpoints (E37–E40) | FE/BE | T36 | M8 |
| T38 | Accessibility pass, i18n human review, contrast and jargon lints | QA/DS | T13, T21, T24 | M9 |
| T39 | Authorization matrix tests, contract tests, load tests, resilience tests | QA | T24, T25 | M9 |
| T40 | Demo Control S11 and demo endpoints; `make preflight` | BE/FE | T23 | M9 |
| T41 | Present Mode S12: dual sessions, narration templates, operator panel, caption translation | FE | T24, T26, T40 | M9b |
| T42 | Comprehension tests (five-second, silent-video) with outsiders | QA/DS | T41 | M9b |
| T43 | Video, deck, README, repo cleanup, baseline log | all | T37, T42 | M10 |
