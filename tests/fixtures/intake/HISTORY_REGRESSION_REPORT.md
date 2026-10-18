# Intake omission and bounded-history regression

Date: 14 October 2026. Scope: four authorized synthetic diagnostic model calls;
Google GenAI SDK, configured gemini-3.8-flash, project work-511514/global. No real
user case contents, credentials, headers or tokens were logged. No further calls
were made for prompt versioning.

## Observed user issue versus diagnostic results

Root inspected only persisted facts/pipeline metadata of the reported case:
country IN, UPI method, timestamp and Test Bank persisted; amount and recipient
were missing; the three steps had degraded=false. This supports a valid partial
extraction omission, not a wholesale Money-schema validation failure.

Calls 1–3 replayed the synthetic three-turn story using the prior latest-text-only
prompt and known facts. All three outputs passed strict local validation. Call2
returned amount value45000/currencyINR, so the original omission **was not reproduced**
in this nondeterministic replay. It also returned a recipient as type vpa and incorrectly
copied the recipient into transactionRef; call3 replaced the latter with the explicitly
supplied synthetic TEST reference. These observations motivate stronger type/reference
instructions; they are not claims of general accuracy or fixed nondeterminism.

Call4 used the updated history-aware prompt, simulated persisted facts matching the
reported omissions, and both prior user statements with server timestamps. Latest
text began “INR” and explicitly stated self-authorization, phone contact, stopped
contact and a TEST reference. The result recovered45000/INR, UPI recipient
safe.verify@fakebank, authorizedByVictim=true, phone channel, ongoingContact=false
and TEST0000000001; missingMinimum=[] and degraded=false. No broad financial regex
or hardcoded story parser was added. No extra retry/batch was used to improve results.

## Change and safety boundaries

The new optional history input contains only prior victim statements {text,at}:
last six statements, at most16000 characters, each text at most4000 characters,
credential-scrubbed before prompting. Assistant replies and system instructions are
excluded. The model fills missing facts from explicit statements about the same
payment; source timestamps govern historical relative-time interpretation, and known
timestamps must not be reinterpreted. Confirmed fields remain protected by the API
mutation boundary and optimistic revision checks.

The prior prompt remains `agents/prompts/intake_text.v1.md`. The active prompt is
`intake_text.v2.md`, and IntakeReply.promptVersion reports intake_text.v2. Evidence
prompt/version is unchanged. Degraded replies now explain that extraction could not
reliably read the message and offer retry or the Change/manual-entry control instead
of silently presenting the same ordinary missing-field question.

Synthetic regression tests cover intentionally omitted second-turn amount, recovery
using prior source context, preserved partial facts, bounded/scrubbed history and
explicit degraded UX. Sixty-three agent tests passed before the version-only update;
the final version regression run is recorded in the task hand-off. These local tests
use fake clients and do not establish a live-model success rate.
