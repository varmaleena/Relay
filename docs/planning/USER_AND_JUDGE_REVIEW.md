# Relay: user and judge review at the M3 checkpoint

Reviewed 17 October 2026, Asia/Calcutta. This is a product assessment, not a
feature approval, legal review, usability-study result, or predicted judge score.
M0–M3 implementation and their recorded approvals are historical evidence. M4
has not been authorized at this checkpoint. Read the dated phase reports for
their original scope and results; later phases supersede their statements that
the next phase was not yet implemented.

## The product in one sentence

Relay helps a person who has recently been scammed turn their account and
evidence into confirmed facts, a contact plan and recipient reports they can
review, copy/download and submit themselves through an official channel. A
separate optional demo shows explicit approval and simulated delivery; Relay
does not submit to real institutions or confirm self-submission.

The unit of value is a usable handoff, not an AI conversation. The present
product does not recover money, locate funds, determine legal liability, file a
real complaint, or obtain a human institution decision.

## Who needs it and what they are trying to do

**Primary intended user:** a recently scammed person during the initial response,
possibly distressed, using a phone and unfamiliar with reporting procedures.
The intended need is represented by the dossier personas; actual demand and
outcomes have not been validated with real victims. The build accepts synthetic
details only. It must not be presented as a released service for real victims.

**Job to be done:** “I think I have lost money. Help me understand the next safe
action, preserve an accurate account, and tell the right organization what it
needs without making me repeat the story or claim something untrue.”

This combines four distinct needs:

1. Understand the immediate action without waiting for an AI job to complete.
2. Correctly record amount, currency, time, recipient, transaction reference and
   who authorized the payment, with uncertainty visible.
3. Understand who to contact and why; review a useful message in the recipient's
   language plus a readable victim copy.
4. Know what was prepared and, in the optional integration demo, what exact
   version was approved and which simulated receipt exists. Copying a report
   does not establish that an institution received it.

The emotional outcome is greater clarity and control. That is an intended
benefit, not a measured anxiety reduction or a promise of recovery.

**Secondary intended user:** recipient institution staff reviewing an addressed
report. Their job is to understand the submission, see what is missing, request
specific information, and make an authorized decision. The Receiver Console,
receiver briefs and genuine request/answer loop belong to M4 and are currently
unavailable. A mock submission receipt is not evidence that this second user has
been served.

**Judge:** needs to understand the problem, observe the handoff, inspect the
Google AI/Cloud implementation and evidence, and distinguish functioning code
from simulations and unfinished work within a short review window.

## What the user gets, and where it can be used

| Stage | Concrete output | Current use channel | Necessary distinction |
| --- | --- | --- | --- |
| Start/intake | Immediate safe-action copy; saved conversation and confirmed facts | Local responsive English/Hindi web application | First actions are visible before model inference; voice is disabled. |
| Evidence | Validated upload, structured extraction, explicit confirmation | Signed local file upload and owned case view | A successful screenshot extraction is not an OCR accuracy benchmark. |
| Plan | Three India/UPI contact identities, channels, source passages and draft notices | S4 plan view | Bank, cyber authority and payment app are distinct recipients; phone/portal are channels for the cyber recipient. Ordering is a draft product heuristic. |
| Message review | Recipient message, victim copy, field provenance, verification results and version | S5, clipboard and actual PDF | A readable artifact is the deliverable. Model verification is not human legal/source approval. |
| Approved submission | Content/version-bound approval and SIM ticket from a registered MCP mock | Internal in-process MCP tools and S6 tracker | Nothing goes to a real bank, authority or payment app; no hold is automatic. |
| Follow-up | Recorded events, message status, in-app notifications and audit export | S6 tracker | Receiver decisions and real receiver information requests are not implemented. |

The PDF and clipboard demonstrate portability, but this does not authorize using
synthetic draft guidance for a real report. No real recipient endpoint or email
address is automatically contacted. The displayed local URL is not a deployed
Google Cloud submission URL.

## Why each implemented phase belongs in this journey

| Phase | User problem addressed | Implemented product logic and proof | Assessment at this checkpoint |
| --- | --- | --- | --- |
| M0 foundation | “Can I trust the application to preserve my information and respect my control?” | Canonical contracts, identity/ownership policy, logging/privacy controls, pack expression/source gates, local development and a separate real Cloud Run/model-access smoke. | **PASS for recorded local foundation checks. OPEN for complete application deployment, cloud dependencies, production backup and human privacy/source review.** A health response proves connectivity, not case usefulness. |
| M1 intake | “I am upset and have fragments of what happened.” | First safe action, text/evidence extraction, confirmed-fact revisions, multi-turn history, quarantine, owner isolation, reload and deletion. Actual browser/emulator evidence and separate live smoke are recorded. | **PASS for tested local intake mechanics. OPEN for broader extraction quality, fluent Hindi and outsider comprehension.** The live smoke's 19/20 schema/source-valid outputs and 10/20 exact raw-field matches are different measures. |
| M2 plan | “Who should I contact, and why?” | ADK classification, authorization distinction, explicit country handling, deterministic pack rules, citations, staleness and durable jobs. Local India preview requires explicit draft opt-in. | **PASS for tested local orchestration and boundaries. BLOCK for claims of reviewed production guidance or meeting live accuracy/latency targets.** Only draft packs exist. Live smoke produced 12 plans, 3 clarifications and 5 failures across 20 requests; p95 was 15.99 seconds. |
| M3 messages | “What exactly do I send, and did I agree to it?” | Bounded drafting/verifying, immutable content versions, correction/reverification, named current-version approval, persisted outbox, actual registered MCP mock tools, receipt tracking, signed PDFs and deletion. | **PASS for the recorded synthetic transport/approval tests. BLOCK for a dependable fresh live-generation claim.** Separate live runs verified 1/3, 0/3 and 2/3 recipient messages; the final bank attempt failed with 429s. No combined 3/3 batch exists. |

The M3 phase report records 599 main-suite passes, six separately passing emulator
checks, package/service coverage gates, browser transport and accessibility
checks. These are dated engineering results, not 599 users or a victim-impact
study. Fixture model tests prove workflow behavior under supplied outputs; live
smokes measure a different, much narrower set of model/provider outcomes.

There is a coherent victim-side text journey through M3. There is not yet a
complete victim-to-human-recipient-to-victim loop. The dossier's “first complete
text loop” at M4 must not be confused with complete submission P0 scope: later
voice, generality, evaluation and presentation obligations remain.

## Current blockers, deferrals and wording risks

| Item | State | Practical consequence |
| --- | --- | --- |
| User's registration/team eligibility/private dashboard cutoff | **UNKNOWN** | Repository work does not establish valid entry. Submission readiness must check the actual dashboard. |
| Public deployed application URL, repository, English video/deck | **OPEN / NOT ESTABLISHED** | Local review and an earlier private infrastructure smoke do not satisfy the whole submission package. Do not infer publication status. |
| Published human-reviewed rule packs | **BLOCKED pending actual review** | Draft preview is an explicit local demonstration exception. No invented reviewer, numerical legal deadline, liability finding or refund entitlement. |
| Provider reliability and 429 capacity pressure | **OPEN** | Fresh generation can fail; exact capacity cause is unproven. Typed errors/backoff improve honesty, not availability evidence. |
| Cyber rail category mapping | **OPEN configuration limitation** | NEEDS_INFO can mean the demo mapping is missing, not that the victim should invent a category. |
| Human Hindi, privacy/legal and fraud-operations review | **OPEN** | Automated accessibility/verification checks cannot substitute for these reviewers. |
| Receiver Console and information-request loop | **DEFERRED to unapproved M4** | No present claim of staff acknowledgment, hold decision, resolved request, or case closure. |
| Voice, UK/general pack switching, Pack Studio, linking, full Evaluation Lab and Present Mode | **DEFERRED to their approved future milestones** | Contracts or planned architecture are not implemented user capability. |
| Real institution submission, recovery, funds location or production liability advice | **OUT OF DEMO SCOPE** | Never imply these occur after an approval click or SIM ticket. |

The 17 October corrective increment resolved three source-level clarity risks:

- Privacy and consent now explain saved reports and 72-hour access expiry,
  without implying browser-only storage or guaranteed physical deletion.
- The plan describes proposed contact ordering and visible source/draft labels,
  rather than implying a validated legal priority.
- Recorded facts are read-only in report review, with a link to change intake
  answers. Genuinely missing report fields remain editable.

The primary flow now prepares reports for user inspection and self-submission;
optional simulated delivery is separately collapsed. Copied reports include exact
structured fields, requested actions, citations and draft/demo warnings. Copying
and downloading never establish submission or call the send operation.

Twenty browser checks passed, covering English/Hindi desktop/mobile views,
accessibility and submission boundaries; the desktop money regression also
passed (its existing mobile variant is skipped). These are engineering checks,
not observed user comprehension. Human Hindi review and outsider usability
validation remain open. See M3_CLARITY_REVIEW.md for this increment's evidence.

## Judge evidence matrix

The root agent freshly verified the official themes and FAQ pages on 17 October:
technical/GenAI 40%, alignment/impact 25%, innovation 25%, UX/design 10%, unchanged
from [COMPETITION_ASSESSMENT.md](COMPETITION_ASSESSMENT.md). Organizer sources are
[themes](https://aibuildercup.com/themes.html),
[FAQ](https://aibuildercup.com/Faqs.html), and
[timeline](https://aibuildercup.com/index.html). BFSI fraud is a direct theme fit.
The verified submission requirements include Google AI, a deployed Cloud
Run/Firebase prototype, public GitHub repository, video strictly under three
minutes, explanatory deck and English submission materials. The FAQ requires
2–4 members, age 21+, JAPAC residency and eligible professionals/startups rather
than students. Whether this actual team qualifies and is registered remains
unknown. Use the private dashboard for the exact cutoff; this document does not
claim access to that private state.

| Criterion | Defensible current evidence | Likely judge challenge | Evidence needed before a stronger claim |
| --- | --- | --- | --- |
| Technical/GenAI, 40% | Real Gemini intake/classification/packet smokes; actual ADK workflow; deterministic source-bound planning; strict verification/approval; real MCP registrations; transactional jobs/outbox and scoped storage. | “Why does this need AI, and can it reliably finish a new case?” | Show how language/evidence become a usable handoff. Retain live failures and latency. Prove a deployed whole application; do not count named services/agents as technical merit by themselves. |
| Problem alignment/impact, 25% | Specific BFSI post-scam response need; authorization distinction; confirmed evidence and tailored messages reduce avoidable ambiguity in principle. | “Who uses the output, and did it improve anything?” | Complete the human receiver loop, run comprehension and paired handoff-task measurements, and report actual denominators. No recovery or prevented-loss estimate exists. |
| Innovation/creativity, 25% | Potential differentiation in source-governed, cross-recipient, version-approved handoff and follow-up rather than a one-shot answer. | “Is this a chat wrapper or an existing reporting portal?” | Demonstrate the durable artifacts and actions after chat; compare against an appropriate same-model baseline. Existing victim assistants, bank case tools and national rails overlap. Uniqueness is not established. |
| UX/design, 10% | English/Hindi responsive journey, first-action visibility, explicit approval, real PDFs, warnings and recorded desktop/mobile accessibility checks. | “Can a distressed person tell what happens next and what is only a simulation?” | Outsider tasks, fluent Hindi review, clear error/retry paths, recorded-fact editing clarity, and a complete receiver-request response journey. Axe and screenshots do not establish usability. |

Do not put a speculative 8/10, finalist probability or dossier self-score in place
of this matrix. No other entrants, final selection threshold or judge outcomes
are known. A smaller demonstrable workflow with honest limits is stronger
evidence than a longer architecture inventory.

## How to demonstrate value without presenting a chat wrapper

Use one frozen synthetic incident and identify the user and deliverable before
showing chat. Observe the progression: fragmented statement → confirmed facts →
source-labelled contact plan → recipient message and victim copy → an edit that
invalidates old approval → explicit approval of the current version → a matching
SIM ticket and tracker entry. Show one relevant correction or safety boundary.

The judge should be able to answer: “Which message is useful to which recipient?
Who approved it? What actually happened? What still needs a human?” If the answer
is only “the AI gave helpful advice,” the differentiating product has not been
demonstrated. A mixed-run or replay fixture must be labelled; it cannot stand in
for a successful fresh live batch.

## Proposed impact measurement, not completed results

Predefine a small synthetic handoff task and compare Relay with a frozen
same-model general-guidance baseline, using equivalent scenario information and
documented model/prompt/budget versions. Counterbalance task order if the same
participants try both. Retain errors, retries and provider failures.

Measure time to the first **correct** safe next action; correct recipient/channel
selection; completeness and factual faithfulness of the final message; user
understanding of what was submitted; and completion of a specific receiver
information request. Separate configuration issues from information missing from
the user's report. Report sample size, actual failures and uncertainty, and
distinguish task time from model latency and deliberate test pauses.

Use outsiders to test comprehension and a suitable fraud-operations reviewer to
assess handoff usefulness. The spec's three-outsider screen-comprehension check
is a minimum clarity gate, not statistically representative impact evidence.
Any larger study, expected improvement, throughput saving or prevented loss is
currently a proposal. Do not manufacture testimonials, recovery figures, time
savings or monetary ROI.

## M4 questions that must be answered before and during implementation

1. **Who receives this?** Which synthetic recipient organization is the logged-in
   staff member authorized to view? The receiver sees the addressed packet and
   necessary projection, not the full victim case or unrelated reports.
2. **What is the decision?** Distinguish transport receipt, human acknowledgment,
   request for information, simulated hold outcome, rejection and escalation.
   AI can summarize/recommend; staff must explicitly decide.
3. **What exactly is missing?** A request names bounded specific fields/items and
   a comprehensible message. Missing routing configuration must not masquerade
   as a victim question.
4. **How does the victim respond?** The tracker opens the actual request, collects
   the answer, creates a new version and verifies it. A previous approval cannot
   authorize the new version or implicitly resend it.
5. **Can both users understand the result?** Show a matching event/request/ticket
   and explain the next action. Do not imply recovered money or a real hold.
6. **What proof closes the loop?** Owner/recipient isolation, explicit decision,
   stale/version races, bounded retries, reload, expired requests and deletion
   need tests. A synthetic two-role browser task must exercise the real API.

M4's exit demonstration is: an owned submitted report reaches the correct
synthetic staff view; staff explicitly request a specific item; the victim
understands and answers; the new version is verified and freshly approved; both
surfaces show a consistent simulated outcome. This is the next product-value
proof, not permission to start M4 or a reason to hide the live-provider gate.

## Required exit rubric for every phase

| Gate | Question to answer in the phase review | Evidence for PASS; otherwise label BLOCKED, OPEN or DEFERRED |
| --- | --- | --- |
| Who | Which primary/secondary user is served in this increment? | Name the role and permissions; a judge/operator is not silently substituted for the victim. |
| User goal | What concrete problem is now solved? | State the job and resulting artifact/action in ordinary language. |
| Understands action | Does the user understand what to do next and what the status means? | Show the purpose, primary action, result and failure path; record outsider comprehension separately from automated checks. |
| Value | What can the user or recipient actually do with the output? | Demonstrate its channel and downstream use. Mark intended benefits separately from measured improvements. |
| Safety | What can the system not do without the right human or permission? | Show provenance, uncertainty, simulation, ownership, version approval, correction and deletion boundaries. Keep human review gates explicit. |
| Test proof | Which implementation, transport and live-model checks actually ran? | Link dated reports with counts, failures and environments. Fixture success, live quality and cloud deployment are separate claims. |
| Criteria | Which competition requirement or judging dimension is supported? | Use current organizer/dashboard requirements; do not replace the product goal with tool counting. |
| User approval | Did the project owner review this result and authorize the next phase? | Record the actual decision, accepted limitations and next scope. Silence and an implementation approval are not acceptance of all quality gates. |

A phase may be locally implemented with open release gates, but must not be
reported simply as “complete” without those qualifications. New phases require
the user's iterative approval. Eligibility, deployment, human review and live
reliability remain visible across phase boundaries until actually resolved.

## Evidence read for this assessment

- `PRODUCT_DOSSIER_REVIEW.md`, `COMPETITION_ASSESSMENT.md`, M0/M1/M2/M3 phase
  reports, current checkpoint and `docs/testing/M0_M3_USER_TESTS.md`.
- Actual `App.tsx`, `Packets.tsx`, `Tracker.tsx`, English locale copy and generated
  contracts; packet/intake/planning services and HTTP/MCP tests inspected during
  their implementation and the present review; ADR0006.
- No new inference, cloud mutation, deployment, source publication or institution
  contact was performed for this document. No user-study result was created.
