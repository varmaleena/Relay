# Pack Studio access increment

18 October 2026. This increment connects the existing S9 reviewer component to a
separate Firebase reviewer session. The primary user is an authorized pack
reviewer, who adds source material, examines extracted candidates and their cited
passages, and records review actions. It is separate from the victim report flow.

StudioWorkspace restores a session or asks for a reviewer email/password. It uses
normal Firebase Auth and App Check, with a separate named Firebase app and browser
session persistence. Browser role/org checks are convenience guards; server
reviewer/org authorization remains authoritative. Source upload requires the
configured API origin, exact source-upload route, normal identity/App Check
headers, and redirect refusal. No account credentials are embedded in the app.

The backend public configuration must enable both sources and Pack Studio before
the workspace permits Studio actions; missing or failed configuration remains
unavailable. Publication is intentionally blocked without an explicit human-
authored canonical publication draft. No reviewer signature, legal review or
pack publication was performed by this increment.

The optional seed_reviewer operator script provisions one explicitly synthetic
reviewer in demo-relay-local or work-511514. Cloud mode requires --apply; emulator
mode requires the exact local Auth emulator target. Random credentials are stored
only under ignored .local/reviewer-auth with restricted permissions. Existing
accounts must exactly match the stored fixture and claims; mismatches are refused.
The script was not executed as part of this increment.

Validation: seven Python seed/ACL/idempotency/account-adoption tests, two browser
policy tests for claims and upload destinations, and three bilingual/content
checks passed. TypeScript and reviewer helper mypy/Ruff checks passed after public-config
contract regeneration. No cloud calls,
provider calls or authenticated browser end-to-end test were run here. Hindi copy
is a draft, pending human review. Existing Pack Studio component checks do not
establish human source accuracy or usability.

Judging relevance: the separated reviewer role and fail-closed configuration make
the generality/source-review story concrete and understandable. This evidence is
an implementation/security increment, not measured impact or proof that the full
M6 live-build gate passed. Remaining gates include actual reviewer browser login,
source ingestion, extraction/critic review, a human-authored publication draft,
human approval and real bounded evaluation against a gold pack.
