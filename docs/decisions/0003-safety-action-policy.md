# ADR 0003: deterministic safety and server-owned approval

Date: 2026-10-13. Status: accepted for M0 implementation; later API integration remains required.

## Decision

T09 supplies pure dataclass policies and bilingual text patterns without importing the concurrently developed schemas. The API must construct actors from verified identity/custom claims and resource scope from trusted storage. These classes are not authentication mechanisms. Never deserialize client JSON into an Actor, Context, or persisted Approval and call that verified authorization.

`check` returns allow, require-approval, or deny; default and unknown actions deny. Victim send/share/download is owner-only, institution decisions are receiver/org-only, reviewer publishing is reviewer/org-scoped or admin. Admin cannot impersonate victim approval or receiver decisions. Automated extraction/planning is permitted for trusted system principals or the owning victim. Receiver evidence access refers only to the recipient-scoped projection and permitted attachment; the later API must enforce that projection.

`check_with_approval` requires a record retrieved from a server approval repository, bound to actor, action, resource, exact version, content hash, recipient, and aware-time validity. Editing, rerouting, expiry, or revocation denies. In M3 the API must record the explicit human confirmation before adapter invocation, atomically bind current verification/revision, and audit decisions/denials without content. Approval is not reusable across actions. Idempotent delivery and transactional revision checks belong to the future API/repository boundary, not this pure policy.

Output text controls inspect English, Hindi, and common Hinglish solicitation/promise patterns. A caution such as “do not share your OTP” remains allowed; a request to share is blocked. Legal-conclusion patterns block even when prefixed with a citation: textual wrappers cannot establish source entailment. Later verified pack paraphrases require structured provenance/verification; there is no caller-controlled “trusted citation” bypass. Controls are intentionally conservative and incomplete; an allowed output is not proof of safety. No model classifier, multilingual full coverage, or red-team performance claim exists in M0.

Labeled text credentials and card-shaped numbers are scrubbed before logs/persistence. This cannot detect arbitrary secrets, image credentials, speech credentials, or all languages. Intake/attachment integration must reject or quarantine potential secret-bearing content and must never log raw inputs. Metadata validation verifies allowed MIME, 10MiB limit, image decode assertion, and PDF page count ≤20; the assertion must come from a real decoder/parser, never the client. Metadata acceptance yields `quarantine`, not a safe-file designation.

## Quarantine lifecycle for M1

Upload to a restricted temporary location inaccessible to case listeners and receiver previews. Sniff MIME, decode safely, bound expansion/pages, strip metadata, compute hashes, inspect text/OCR for prohibited credentials and injection, then promote only accepted synthetic evidence. On rejection, delete quarantine content and persist only a scrubbed reason/event. Apply a short lifecycle deletion policy for abandoned uploads and failed processing. Injection is flagged untrusted data and not executed; a flagged source never earns tool privileges. Hashing does not establish safety. Original byte retention and sanitized hash lineage must be explicitly defined before promotion.

## Live limitation and M5 experiment

Text checking after captions arrive cannot prevent unsafe raw audio already played. No M0 code claims pre-play voice protection. M5 must measure buffering until transcript checks versus constrained text-first response/audio synthesis, including interrupted utterances, multilingual secret solicitations, latency, and missing transcripts. User review of that experiment precedes voice release. Raw input audio must not persist; scrub speech-derived text before durable writes.

## Verification

Unit tests cover actor/org exclusions, deny-default actions, approval revision/hash/recipient/expiry/revocation, en/hi/Hinglish solicitations and safe warnings, zero-width obfuscation, labeled secret scrubbing, malicious instruction flags, and upload metadata bounds. These are local deterministic tests, not deployed IAM, browser, model, audio, or complete safety evaluation evidence.
