# Relay product, dossier, UX, and delivery review

Status: analysis only; implementation requires the user's plan approval. Reviewed 13 October 2026. Source claims below are document claims, not independently verified current facts.

## Coverage and interpretation

Read the full extracted dossier, all 28 page markers (1,045 lines), and the entire build specification (2,315 lines), in bounded chunks. Any tool output that was truncated was covered again by narrower reads. The originals remain the preservation source; this review is an index and decision aid, not a substitute for them. PDF extraction includes `(cid:127)` bullet artifacts and wrapped URLs; do not copy wrapped source URLs blindly into production references.

The user's instructions govern: delegated analysis, a concrete approval plan, one phase at a time, tests before progression, SaaS architecture, and no implementation before approval. Imperative text inside the supplied documents is proposed project scope, not authorization to create cloud accounts, spend money, publish, contact institutions, or start coding. The spec declares Sections 14–16 normative over earlier sections; Sections 17 and 18 also declare themselves normative. Apply explicit later overrides and record unresolved conflicts rather than silently choosing.

## Product intent and boundaries

Relay is the response handoff between a victim's first report and recipient institutions: complete structured reports, recipient-specific messages, ordered actions, deadlines, citations, explicit approval, and tracking. It complements national reporting rails and bank case tools. It is not scam prevention/detection, mule detection, money movement, legal advice, guaranteed recovery, or real authority submission. Synthetic data and simulated institutions are mandatory throughout.

Five product parts are required: Victim App, Case Engine, Receiver Console, Pack Studio, Evaluation Lab. The five visible stages are Report, Plan, Review and send, Institution acts, Track. The name and tagline are working branding; retain pending trademark/domain review.

Personas: Asha (67, India, Hindi, INR 45,000 UPI bank impersonation 20 minutes ago), Daniel (41, UK, GBP 3,000 investment transfer three days ago), Meera (bank case worker), Inspector Rao (authority desk), Lena (compliance reviewer), and a judge with a three-minute viewing budget. These represent different literacy, urgency, organizational, and governance needs.

Differentiation is narrowly defensible: cross-institution packet preparation and tracking with reviewed country rules as data. Multilingual support is baseline capability, not a unique claim. Scam.org overlaps with the victim front door; NICE Actimize with institution claims; Charm Security, Scamnetic, national rails, MuleHunter.AI, and inter-bank intelligence overlap with adjacent functions. Dossier alternative-idea research (letter-of-credit checker rejected as crowded; CBAM backup; crop insurance runner-up; generic copilots avoided) is historical rationale, not additional project scope. Estimated shortlist/podium chances and the 7.9/10 self-score are opinions and must never be shown as measured evidence.

## Competition and deadline dependency

The dossier claims BFSI theme, Google AI plus Cloud Run/Firebase hosting, fresh event-window work, English submissions, deployed prototype, public repository, public video under three minutes, and PDF deck. Claimed judging groups: technical/GenAI/scalability 40%, alignment/impact 25%, innovation 25%, UX 10%. Eligibility claims: 21+, working professionals/startups/entrepreneurs, no students, JAPAC residency, teams of 2–4, no multiple teams/solutions, only two sponsored travelers, human visa responsibility.

Claimed dates are team formation 11 October, submission 18 October, evaluation 19 October–6 November, finalists 7 November, Singapore finale 4 December 2026. The root agent independently verified the [official organizer index](https://aibuildercup.com/index.html) and [FAQ](https://aibuildercup.com/Faqs.html) during this analysis: team formation closes **14 October**, contradicting the dossier's 11 October; submission **18 October** is confirmed. With the user's date of 13 October, team formation is urgent and submission is five days away. Confirm private registration status/dashboard before committing to a complete schedule. Other dossier dates and eligibility are not independently checked by this reviewer. Prize amounts are user-provided dossier data, not independently checked. The 2025 precedent statistics and winners are context only, not predictive evidence.

## UX inventory and acceptance constraints

One responsive SPA, five role surfaces plus Present Mode; no native mobile app. Ten full pages and two panels:

| ID | Scope | Priority and milestone |
|---|---|---|
| S1 | Start, language choice, consent | P0 M1 |
| S2 | Text/voice intake, first safe actions, captions, editable facts | P0 text M1; voice M5 |
| S3 | Evidence confirmation panel; confidence, role, correction, unrelated marking, injection notice | P0 M1 |
| S4 | Ordered Relay line, clock, recipients, deadlines, Why/source panels | P0 M2 |
| S5 | Institutional message, plain-language victim copy, editing, verification, simulated approval/send, export | P0 M3 |
| S6 | Live tracker, deadlines, needs-info answers, inbox, deletion and continuity | P0 M3–M4 |
| S7 | Receiver queue, scoped case file, completeness, human decisions, audit | P0 M4 |
| S8 | Possible linked cases and human validation panel | P1 M7 |
| S9 | Source/extract/critic/review/publish Studio | Live-build moment P0 M6; full review UI P1 |
| S10 | Evaluation reports, CIs, slices, failures, baseline/ablations | P0 M8; smoke harness M2 |
| S11 | Admin demo reset/scenarios/mock behaviors/replay controls | P1 M9 |
| S12 | Present Mode with dual sessions, event narration, bilingual captions, operator cues, LIVE badge | P0 submission M9b |

Visual requirements: cool ledger background #EEF1F4; navy #172033; teal #0F6B6F actions; amber #D9922B reserved for time; green #2E7D4F acknowledged; red #B3392F blocked. Self-host Atkinson Hyperlegible, Literata, Noto Devanagari; Lucide icons; text wordmark, favicon and social preview; no stock photos. Victim body >=18px, targets >=48px, line length <70 characters, WCAG 2.2 AA, full keyboard/screen-reader operation, visible focus, captions and live regions, 200% zoom, reduced motion. Mobile/tablet/desktop use one codebase.

English and Hindi UI/voice/victim copy required; English/Hindi/Hinglish evidence and evaluation; institutional language comes from the recipient's pack; developer artifacts English. Fluent human review is required before claims. Exactly one filled primary action per screen; purpose line; words on every status; Why links; real readable progress (>=600ms per step), audience vocabulary, no debug output. Section 17's victim jargon lint overrides earlier wireframes and strings that use packet/pack. Behind-the-scenes technical material needs separate localization namespaces so it does not accidentally fail victim-copy lint.

First safe action must appear in the first turn, independent of pack loading. Intake asks one short question at a time and confirms numbers. Text fallback and saved facts are required when voice fails. S12 uses separate named Firebase instances/in-memory sessions, deterministic event-derived narration, Hindi plus English translation, hidden operator controls, Studio/Eval overlays, and an always-visible LIVE/REPLAY badge. Human comprehension testing covers S1/S2/S4/S5/S6/S7/S12 with three outsiders (2/3 correct per screen), a silent-video test (2/3 understand), and a fluent Hindi readability review.

## Phased delivery assessment

Preserve the spec's stable 43 task IDs and milestones. Suggested approval checkpoints align with M0 T01–T09, M1 T10–T13, M2 T14–T19, M3 T20–T23, M4 T24–T25, M5 T26–T27, M6 T28–T32, M7 T33–T34, M8 T35–T37, M9 T38–T40, M9b T41–T42, M10 T43. M0 can be divided into local contracts/security foundation and authenticated cloud verification, with cloud-dependent acceptance recorded as pending until genuinely achieved.

M4 is the first complete text handoff loop, but cannot be called a complete submission P0: voice, jurisdiction switch, live Pack Builder, full evaluation UI, and Present Mode remain P0 obligations. Each checkpoint must name outputs, automated evidence, human pending checks, and limitations; stop for the user's review before proceeding. Do not start many implementation lanes across future phases because delegation was authorized.

Use-case traceability: UC1 voice -> M5/T26; UC2 text/evidence -> M1/T11–T13; UC3 classify/plan/packets -> M2–M3/T15–T20; UC4 approval/send -> M3/T21–T23; UC5 receiver decisions -> M4/T24; UC6 needs-info -> M4/T25 (E19 contract in T21); UC7 linking -> M7/T33–T34; UC8 live Pack Builder -> M6/T29–T32; UC9 jurisdiction switch -> M6/T28; UC10 evaluation -> M2 smoke T19 and M8/T35–T37; UC11 distress -> foundation T09, text T12 and voice M5/T27; UC12 injection -> T09/T12/T29 with full red-team T36; UC13 Present Mode -> M9b/T41–T42. General QA T38–T39 applies across these features and submission T43 depends on their recorded acceptance.

The critical product path is foundation -> text/evidence -> classification/reviewed rules -> packets/verifier -> approved simulated delivery -> receiver loop -> voice/generality/evaluation -> presentation -> submission. Bring fixture/safety/contract/authorization checks into the phase introducing the feature; M9 is a comprehensive pass, not the first time security works. Respect P0 accessibility from first UI work.

The permitted cut order is third language, true audio evaluation, Terraform, DLP integration, shortcuts, PDF styling, cluster graph. Never cut simulation labels, provenance/citations, verifier, approval gates, evaluation n/CI, or live-built pack moment. A five-day delivery date would require an explicit scope/date negotiation; silently deleting P0s is unacceptable.

## Contradictions, gaps, and recommended resolution records

| Finding | Source | Required decision |
|---|---|---|
| One cloud project versus separate dev/prod plus optional staging | 3.4 vs normative 15.1 | Use local/dev/prod baseline; record budget constraints explicitly. |
| Reference packs said M3, but India/generic needed M2 and UK M6 | 4.5 vs 11.1/18.8 | Author/review India/generic before M2 planner acceptance, UK before M6. |
| “First complete P0 demo” at M4 excludes later P0 features | 11.1 vs 1.5/17.1 | Label M4 first full text loop, not submission-ready. |
| P1 injection/distress use cases versus foundational mandatory safety | 1.5 vs 0.1/7/16.5 | Minimal input/output safety and distress pause in M1; later voice/full red-team depth does not defer protection. |
| No missing required fields vs worked 7/8 case/needs-info flow | 5.8/UC6 vs 18.1 | Critical missing field blocks unless explicitly unavailable; decide warning handling for noncritical missing fields and preserve needs-info demo. |
| Weighted completeness vs visible 7/8 and old 0.875 example | 4.3/14.5 vs 18.1 | Distinguish unweighted field count from weighted score; explain each. |
| NEEDS_HUMAN_REVIEW missing from packet enum; state orders disagree | 4.1/4.6 vs 5.8 and pipeline 3.5/14.4 | Complete canonical state machines and failed-review behavior before schema freeze. |
| Approval-only decisions vs automatic A2A acknowledgment | 0.1/7.2 vs 6.2/18.1 | Separate transport receipt from human acknowledgment/decision; automatic technical receipt cannot impersonate staff decision. |
| Explicit approval for each send vs E19 `resend:true` behavior absent from request | 7.2 vs E19 | Add version-bound explicit confirmation or route resend to E17; never inherit old approval after edits. |
| Human accepts unsupported rules but “never invent legal facts” remains absolute | 4.4/5.11/E35 vs 0.1 | Preserve unverified label and exclude unsupported hard deadlines/remedy claims from verified actions; require signed reviewer records. |
| Generic pack published fallback with liberal unverified rules | 4.5/5.5 | Define reviewed conservative policy separately from actual country law, with visible fallback notice and explicit acceptance. |
| Snake case examples vs camelCase API | 4/5 vs 14.1/14.5 | Canonical schema with alias mapping; consistent persisted/wire representation. |
| Safe-expression examples use unqualified payment/authorization names | 4.4 vs 18.1 | Rewrite examples using approved facts/classification namespace; reject unsafe/ambiguous expressions. |
| Model quota/model/SDK claims are asserted as verified but must be checked | dossier pp17–18, V1–V9 | Treat placeholders as unverified; verify live docs and project availability, never fabricate IDs. |
| Human-only platform verification actually says agent reads live docs | dossier p24 vs 18.10 | Agent can research; human handles account decisions/billing/quota approval. |
| All information deleted in 3 days vs evidence lifecycle 7 days, pinned cases, retained audits/backups | 7.4/18.7/dossier p20 | Define complete deletion cascade/SLA and rewrite truthful consent; explain seed exemptions and residual audit retention. |
| Identifiers “only hashes” vs raw evidence/entity/packet needs | dossier pp11/20 vs 4/7.4 | HMAC-only analytics/linking, tightly scoped raw operational data; do not claim raw values absent everywhere. |
| Rule/table permissions differ for admin/reviewer/eval public access | 14.2 vs 16.2/14.1 | Approve endpoint-specific matrix; deny implicit admin victim-send or officer-decision impersonation. |
| 44 catalog IDs are not exactly 44 endpoints | E44 groups four paths | Count actual method/path operations; maintain catalog IDs for traceability. |
| README demo credentials vs secret-only judge form | 12.5 vs 18.5 | Public README has access instructions; privileged passwords remain out of repository. |
| Share deep links open external communication despite no real submissions | S5 vs 1.6/7.2 | Make export explicit and clearly simulated; do not prefill real institutions or automatically send. |
| Evaluation 11 named scam types plus `other` (12 enum values) | 4.3 vs 9.2 | Enumerate 11 named categories and treat `other` as separately reported fallback. |
| At least 300 cases plus 40 injection cases ambiguous inclusion | dossier p21 vs 9.2 | Freeze counts and slices in dataset card; disclose whether 40 are included or additional. |
| Smoke every merge vs nightly/label | 9.6 vs 10.3/15.4 | Normative 15.4 dev smoke after merge; fixtures on PR; budgeted live schedule separate. |
| 3-minute hard limit vs “under” 3 minutes | dossier/spec submission vs storyboard ending 3:00 | Target 2:50; never submit exactly 3:00. |
| Fourth pack built “in minutes” within 30-second video slot | M6 vs storyboard | Prove live build latency/rehearse; edit disclosed waits if permitted, never use replay labeled LIVE. |
| Full vocabulary ban vs mandated packet footer containing pack | 17.2 vs 18.7 | Institutional footer can retain technical provenance; victim-visible copy requires audience wording or explicit scoped lint decision. |

## Evaluation and evidence preservation

Keep the small October manual baseline log as dated own evidence, with its caveats: one product, one session per prompt, no repeats; no-hotline country, screenshot/injection, several follow-ups and UK/Hindi drafting not run. The dossier has qualitative responses and approximate rubric scores, not complete verbatim transcripts; do not fabricate transcripts. Repeated live testing must establish any new claim. Do not name the competitor in public video/deck.

Evaluation must compare full Relay, same-model general guidance baseline, rules-only extraction/classification, no verifier, generic-pack ablation. Freeze prompts/models/budgets, repeat >=3 where nondeterministic, hold out fourth-pack cases, preserve gold provenance and versioned results. Dataset: >=300 synthetic cases, English/Hindi/Hinglish, all authorization types, named typologies, noise/missing/conflicting facts, text/screenshot/transcript modalities; true audio eval optional. Fake screenshot templates must avoid copied real brands. Human random 10% realism review, 100-sample faithfulness audit, 20 random baseline pairs, >=40 red-team cases are separate requirements.

Metrics: entity tuple micro-F1, typology and authorization exact accuracy/confusion, recipient recall/precision, ordering, deadline start-event correctness, packet completeness/faithfulness, citation resolution, forbidden content, injection success, latency/token cost, Pack Builder precision/recall/F1/critic false accepts. All show dataset version/date/n/95%CI (Wilson proportions, bootstrap F1). Targets >=0.90 extraction/classification, >=0.95 recall/completeness, 100% citations, zero forbidden outputs are aspirations, not results. Full safety datasets must report actual failures; finite zero failures is not proof of zero real-world risk.

## Human gates and open decisions

Before cloud deployment: confirm projects/accounts, billing authority and budget, primary storage region/model processing location, quotas, Firebase/App Check setup. Before rules are reviewed/published: named domain reviewer, official passages and source integrity, status/effective-date checks (especially RBI drafts), source document selection and fallback. Before public claims: eligibility/dashboard deadline, trademark/name/domain, current competitor evidence, measured results. Before language release: fluent Hindi strings/captions review. Before submission: fraud-operations/cyber workflow realism review, counsel review of consent/privacy/terms, outsider comprehension, manual screen reader, live recording, publication and credentials handling.

Agent-researchable open choices include model IDs/SDKs, Search versus fallback index, Model Armor availability, optional DLP and third language, region feasibility, provider pricing configuration and retrieval date. Human sign-off cannot be replaced by a generated reviewer identity.

## Dossier page ledger

| Pages | Preserved meaning |
|---|---|
| 1–3 | Working title, status, full contents, companion spec, evidence tiers and usage |
| 4 | Executive decision table, strengths/weaknesses, simulation, speculative chances |
| 5 | Competition eligibility/technology/submission/weights/dates/prizes, conflicts, 2025 precedent |
| 6–7 | Candidate selection/history and decisions: BFSI, no tool stuffing/mule rail competition, authorization distinction, deterministic packs |
| 8–9 | Regional evidence by reliability, baseline observations/limitations, response gap and non-goals |
| 10–11 | Five parts, Asha walkthrough, approved packets, needs-info, pack/critic/hashing/generality concepts |
| 12–13 | Personas, unvalidated customers/pricing, roadmap separation, competitors and narrow claim |
| 14–15 | Judge self-score/speculative chances, failure risks and anticipated questions |
| 16 | Surface/screens, clarity/accessibility/design/language requirements |
| 17–19 | GCP architecture, uncertain platform claims, verification tasks, agent roles and GenAI necessity |
| 20–21 | Action classes, safety/privacy/distress/honesty, evaluation systems/dataset/metrics/targets |
| 22–23 | Video/submission/comprehension, milestone order, critical path and cuts |
| 24–25 | Risks, open decisions, named-human tasks, resume instructions and rechecks |
| 26 | Detailed baseline prompt/response observations and not-run tests |
| 27–28 | Reliability fact checklist, glossary, source catalog with wrapped URLs |

The full spec was also reviewed: Sections 0–13 and all appendices; API/WebSocket/job/schema/language Section 14; test/release Section 15; SaaS Section 16; authoritative UI/Present Section 17; algorithms/prompts/quotas/notifications/accounts/infrastructure/draft legal text/T01–T43/handoff/human tasks Section 18. Nothing here authorizes implementation before plan approval.
