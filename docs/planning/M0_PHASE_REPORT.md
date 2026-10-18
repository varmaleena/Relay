# M0 foundation review

Date: 13 October 2026, Asia/Calcutta. Status: foundation increment ready for review; local gates and deployed Gemini connectivity pass. Outstanding cloud configuration is explicit below. M1 has not started.

| Task | Delivered | Remaining external evidence |
|---|---|---|
| T01 tooling | Exact Python/Node locks, cross-platform runner, CI gates | Hosted GitHub CI has not run; local equivalents pass |
| T02 infrastructure | Reviewed smoke setup deployed, scoped identities, Mumbai storage, full resource registry and BigQuery DDL | Application Firebase/database/queues/secrets/WIF remain pending; the full foundation registry is not an executed provisioning script |
| T03 platform | All 18 SDK symbols available; 28 models discovered; V1–V9 report; deployed Gemini request succeeded | Actual Live access and project quotas remain distinct checks |
| T04 schemas | Canonical Pydantic domain types, provenance and blocked states | Human regulatory facts and production packs are later work |
| T05 contracts | 47 operation contracts, JSON Schema/OpenAPI, strict TypeScript types/client, drift gate | Business operations are 501 contract stubs, not implemented features |
| T06 common | Settings, exact money/entity normalization, HMAC identifiers, locale/timezone, structured allowlist logging, identity boundary | Hindi copy review and real Firebase configuration pending |
| T07 packs | Schema validation, bounded AST evaluator, tri-state missing facts, timezone deadlines, safe YAML limits | Legal passage correctness requires a named reviewer; business calendars unsupported |
| T08 auth/rules | ID-token revocation and App Check verification, organization roles, receiver projections, Firestore/Storage rules | Emulator evidence does not establish deployed Firebase settings or backend IAM isolation |
| T09 safety | English/Hindi/Hinglish guard, quarantine policy, version/hash/recipient-bound ActionPolicy | Real streaming audio enforcement and measured safety evaluation belong to later milestones |

## Verification

Final full Python integration run: 281 tests passed, 96% combined statement coverage, including all 20 setup tests. No LLM inference was used in local tests. Actual Firestore/Storage emulator run: 41 passed, repeated after tooling security overrides. Ruff, format, Python mypy, strict generated TypeScript compilation, contract drift and pip dependency checks pass. High/critical npm audit gate passes; five moderate CLI-only advisories remain documented.

Tests verify meaningful boundaries: malicious objects and AST paths, exact Decimal inputs, hostile YAML, missing facts, calendar ambiguity, generated request IDs, credential redaction, role/org ownership, approval expiry/version/hash/recipient/revocation, and rules access across users/organizations. Synthetic injected identity tests do not bypass runtime verification.

Developer CLI/ADC authenticated for `work-511514`; billing enabled. INR1,000 project alert budget active for selected October 13–18 operating period. Alerts are not hard caps. Mumbai at-rest storage is separate from global model processing. Cloud execution details and exact reviewed plan are in CLOUD_EXECUTION_RECORD.md and M0_SMOKE_REVIEWED_PLAN.json.

## Reviewable behavior and next gate

The API runs locally with public health/version/configuration endpoints, explicit unready dependency status, and protected nonpublic routes. There is no case intake UI or working business endpoint yet. Use README.md for commands and the three ADRs for contract, trust and safety choices. Original documents, all task IDs and source hashes remain preserved for later phases.

The Cloud Run Job generated the synthetic marker in one successful execution, recorded in CLOUD_EXECUTION_RECORD.md. This verifies Google workload identity and real model access, not feature completeness or application readiness. Full project provisioning, Firebase configuration and quota verification are unfinished M0 items; do not silently mark those complete. Review this foundation increment with the user, close those dependencies, then begin M1 only after explicit phase progression (consent, session continuity, text intake, uploads, extraction and entity confirmation).
