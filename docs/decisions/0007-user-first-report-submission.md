# ADR 0007: self-submission is separate from simulated integration

17 October 2026. User-authorized corrective M3 increment; M4 is not authorized.

The project owner found the message/send flow confusing. A recently scammed
individual is the primary intended user, with a concrete job: organize an
accurate account, understand whom to contact and prepare a usable recipient
report. Institution staff are a separate proposed M4 user. The judge is an
audience evaluating that value, not a replacement persona.

The main flow is Tell us → Plan → Prepare report. “Submit yourself” explains
copy/PDF and the recipient's listed reporting channels. Copying or downloading
does not submit, approve delivery, create a ticket, confirm official acceptance
or update a real filing tracker. Drafts with unresolved checks must remain
clearly labeled; automated content verification is not legal/source approval.

The existing integration showcase remains under a separate, collapsed “Try
simulated delivery” section. It retains the same server approval, owner,
recipient, version, hash, verification and staleness gates. Only this simulated
path can produce a SIM receipt and demo updates. There is no real institution
integration, email send, portal autofill or new manual-submission status.

User-facing recipient messages are called reports or report drafts. The intake
chat still sends chat messages; internal Packet schemas, API paths and immutable
version/outbox behavior remain unchanged. Recorded case facts are corrected in
the facts screen; missing report details can be completed where allowed.

Privacy wording reflects saved reports and 72-hour access expiry. It must not
promise browser-only storage or exact physical deletion at expiry: production
TTL/cleanup verification remains open. Draft ordering is a proposed contact
order, not an established legal priority.

At each later phase, record the user, job, next action, demonstrated versus
hypothesized benefit, real/simulated boundaries, test evidence, official judging
criteria and the project owner's approval. Automated checks are not human
comprehension tests. Meaningful Google AI and a coherent flow support the entry;
deployment, submission artifacts, provider reliability and human reviews remain
separate gates. Preserve all original task IDs and source documents.
