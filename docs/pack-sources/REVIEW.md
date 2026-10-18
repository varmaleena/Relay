# T17 source and draft review package

Status: DRAFT. No human reviewer, acceptance, or publication has been recorded.
All recipients, sequencing rules, liability notes, and channels are unverified.

The retrieval timestamps, final URLs, raw-byte hashes, sizes, extraction methods,
and extraction hashes are in `retrievals.json`. Actual response bytes are preserved
under `snapshots/`. `passages.json` records exact extracted text, source IDs,
locators, and passage hashes. Hash integrity establishes provenance consistency;
it does not establish legal correctness, current applicability, or human approval.

## India traceability

| Draft item | Evidence or explicit product heuristic | Review required |
| --- | --- | --- |
| cyber (1930 phone first, NCRP portal second) | `mha-1930:reporting`: MHA operationalized 1930 for immediate financial fraud reporting and assistance with the National Cyber Crime Reporting Portal. | Confirm current channels and national/state operational scope. |
| bank | Relay product advice: contact the bank using an independently obtained official channel. No bank-specific contact or universal remedy asserted. | Add institution-specific contacts separately after verification. |
| payment-app | Relay product advice, conditional on UPI: use support inside the app actually used. | Validate each app's current workflow; no fabricated universal NPCI filing channel. |
| sequence-bank, sequence-cyber, sequence-payment-app | Relay sequencing heuristic; steps can run in parallel. The MHA source supports qualitative prompt reporting, not legal priority or a numerical deadline. | Review practical ordering without delaying urgent reporting. |
| unauthorized-scope | `rbi-unauthorized-2017:scope`; reporting passage also retained for review. The 2017 RBI circular addresses unauthorized electronic banking transactions. | Confirm institution and transaction coverage, amendments, and applicability. |
| all forms | Minimal Relay text field lists, not copies of official forms or claims that agencies require exactly those fields. | Review recipient needs, data minimization, and language. |

Authorized but manipulated payments must be described accurately. The RBI note
does not apply unauthorized liability protections to such payments. The draft
contains no zero-liability finding, refund guarantee, numerical reporting window,
bank working-day calculation, or presumed reimbursement eligibility. No crisis
contacts are supplied.

The India draft has exactly three recipient identities: bank, cyber, payment-app.
The helpline and portal are two channels for the same cyber reporting recipient;
they do not create duplicate forms or plan steps.

## Generic fallback

The generic fragmented pack is unsourced Relay product advice: contact the bank
and identify an appropriate local reporting authority after confirming country.
It supplies no jurisdiction-specific statute, agency contact, or reimbursement
rule. `UTC` and `XXX` are explicit schema placeholders, never inferred country,
payment currency, or a local legal deadline. Recipient language is English; the
pack supports the case interface in English and Hindi, without claiming an
official agency accepts Hindi documents.

## Excluded sources and claims

- The NPCI dispute-redressal URL currently serves a JavaScript-only shell; its
  indexed text was not substituted for freshly retrieved source evidence.
- NPCI's FAQ request was rejected on direct browsing. No claim about stopping
  completed UPI payments or a universal complaint escalation ladder is authored.
- The NCRP citizen instruction PDF labelled “For Delhi Only” was not generalized
  into a national 24-hour filing rule. Full card numbers are not requested.
- RBI's numerical liability, shadow-credit, and resolution windows were excluded
  rather than applied to an authorized manipulated payment.
- A newer official NPCI UPI HELP assistant pilot circular describes transaction
  status and service-issue complaints. It should be considered when reviewing
  competition positioning; no unsupported claim that it handles scam recovery is
  made in these packs.

## Registry and release gate

`PackRegistry(Path('packs')).available()` returns published packs only. With the
current draft-only repository, ordinary selection explicitly raises
`no_published_pack`. A local demonstration must provide all three arguments:
`allow_draft_preview=True`, `environment='local'`, `demo_mode=True`. Production
and non-demo draft requests fail closed. Unknown countries select the generic
pack only if it passes the same gate. Published versions take precedence over
draft previews; versions compare numeric semantic-version components.

Human review must assess each rule, source passage, institution scope, channel,
form, language, and sequencing heuristic. Only an actual reviewer may populate
the review record, accept explicitly identified unverified rules, and authorize
publication through the existing validator. This task does not grant that gate.
