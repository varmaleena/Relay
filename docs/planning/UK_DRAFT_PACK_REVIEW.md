# UK draft reference pack review

17 October 2026. Authoring and structural validation only: **no human legal review,
reviewer signature, acceptance or publication**. T28 is not complete as “authored and
reviewed”; only the source-author draft portion is complete. Existing global India
retrieval/passages catalogs and the pack registry implementation were not edited.

## Evidence and current official sources

Two public official pages were downloaded successfully over HTTPS on 17 October.
Their original response bytes, visible-text extractions, byte-level SHA256 hashes,
retrieval times and sixteen exact-offset passages are isolated under
`docs/pack-sources/uk/`. HTML passages use text offsets and `page=null`, never invented
PDF page numbers. Registry validation verifies snapshot, extraction and passage hashes.

- [PSR APP fraud reimbursement protections](https://www.psr.org.uk/information-for-consumers/app-fraud-reimbursement-protections/)
  supports immediate bank contact, scheme scope/exclusions and published process terms.
- [FOS guidance for scams involving an authorised payment](https://www.financial-ombudsman.org.uk/consumers/complaints-can-help/fraud-scams/scams-youve-tricked-making-payment)
  supports the firm-first complaint path, evidence retention and conditional applicability.
- [Report Fraud reporting scope](https://www.reportfraud.police.uk/reporting-a-fraud/)
  and [its reporting guidance](https://www.reportfraud.police.uk/should-i-report-to-report-fraud/)
  were verified through the browsing tool: the service covers England, Wales and
  Northern Ireland; Scotland has a different route. Direct archival HTTP requests
  returned 403, including one standard user-agent check. No bypass was attempted and
  no police response was falsely represented as a successful raw snapshot. The disabled
  police candidate cites the archived FOS reference; its narrower region scope remains
  a separately documented primary-web verification and archival gap.

The PSR consumer page retains an older “Action Fraud” label. The current official
police service confirms that Report Fraud replaced it in December 2025. The pack uses
Report Fraud and does not copy the obsolete name. The PSR page also contains a separate
FOS compensation-limit figure that this draft deliberately does not adopt or assert
as current. No statistical outcome or recovery-rate claim is taken from these pages.

## What is authored and what is blocked

Canonical ID `pack_uk_reimbursement`, version 0.1.0, country GB, archetype
mandatory_reimbursement, timezone Europe/London, currency GBP, English-only draft.
These are authored jurisdiction metadata, not country inference from money/language.
Every recipient, sequence, deadline and liability rule is unverified; every channel
has `verified=false`. The reviewer fields remain empty.

The only enabled recipient is the sending bank/payment firm, conditional on explicit
GB country facts. Its initial action is immediate contact using independently verified
bank contact information. No bank-specific URL, phone number or account details are
guessed. The generic contact-channel choice and form-field choices are Relay product
advice, not claims about an institution's official mandatory form.

The Report Fraud candidate is `applies_when=False` until the schema can capture and
confirm UK nation. This prevents automatic Scotland misrouting. The Ombudsman candidate
is also blocked because CaseFacts does not represent the preceding firm complaint,
response state or timing prerequisites. Their official information pages remain in the
draft for reviewer inspection; they are not automatically added as immediate plan steps.

APP policy context is limited to authorised manipulation with bank_transfer and GB.
It is explicitly **not** a rule for unauthorised access, card, cash, crypto or civil
disputes. Even that predicate establishes only potential relevance: covered UK rail,
receiving-account country, qualifying customer, transfer date, vulnerability, fraud
complicity and other conditions are not resolved by the canonical facts. The draft
never determines eligibility, gross negligence, an excess or an individual award.

## Windows and limits retained as evidence, not computed clocks

`review-mapping.json` binds each observation to exact archived passages and records
why no executable date/amount is produced. The official pages describe a scheme start
in October 2024, a report window measured from the last payment, processing in business
days with stop-clock rules, and conditional monetary limits/excess. These are retained
for review, not turned into an account-specific conclusion.

The pack does not assume that the single payment.timestamp is the final payment of a
multi-payment claim. It does not assume a report timestamp equals the scheme claim
start, and it has no reviewed business calendar or stop-clock state. It therefore
creates no numeric 13-month, 5-day, 35-day or complaint deadline. A duration-null immediate
contact rule is the only timing entry. It does not map complaint-response periods onto
APP reimbursement processing, or borrow a final-response date that is not recorded.

The current packet verifier's currency-amount check permits case amounts, not arbitrary
scheme-cap amounts in generated prose. Numeric policy limits stay in the review sidecar
and citations rather than being promoted into executable liability prose. A later,
reviewed feature would need an explicit source-bound legal-number distinction; this
pack does not weaken that verifier.

## Tests, product value and remaining gates

Eleven focused tests passed in 2.95s, without models or cloud calls. They cover schema,
all snapshot/extraction/passage hashes, exact offsets, blocked publication without human
review, false verified-channel prevention, unsupported applicability classes, explicit
country predicates, region/complaint gates and tamper rejection. The deterministic
India/UK comparison injects each registry with its own evidence directory. The same
synthetic bank-transfer story yields India bank+cyber steps and UK bank-only pending
scope clarification, with different forms/currency/timezone/language metadata and no
fabricated UK due date. No real country-switch UI, institutional send or human usability
study was run. This proves a constrained contrast, not complete UC9 or complete M6.

A first user can identify the safe initial bank-contact action. A judge can inspect the
source traceability and see unresolved cross-country assumptions rather than a promise
of automatic reimbursement. Full value still depends on parent registration, region and
complaint-state capture, reviewed legal applicability, human language/source review,
actual UI verification and the later explicit publish gate. Routine user development
approval is not a substitute for those reviews.

Parent integration must explicitly register the new subdirectory and merge/reference
its isolated source manifest through a reviewed path; do not silently mutate the global
catalog or bypass the registry's source checks. The default registry still does not
load this nested draft. A future qualified reviewer must assess the complete applicable
requirements and freshness before enabling any blocked route or numeric policy logic.
No paid inference, cloud resource change, real institution contact, publication or
human signature occurred during this task.
