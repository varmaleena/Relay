# Hosted packet static-provenance diagnosis

17 October 2026. Actual run evidence: `.tmp/cloud-browser-full-r2/result.json`
and `.tmp/cloud-full-r2-audit.json`. The hosted case and its packets were deleted
successfully by the harness; their failed check IDs and extracted fact delta were
not retained. The actual failed check and exact hosted root cause remain unknown.

## What the retained evidence establishes

- The packet-generation job succeeded as a job, while each of three packets was
  NEEDS_HUMAN_REVIEW with 16 checks and exactly one failed check.
- Eight provider calls were recorded: one successful intake, one successful
  classification, three successful packet writers, two packet-writer HTTP504s,
  and one packet-writer HTTP429. No VerifierAgent call was recorded.
- The current and staged r3 `agents/packets/core.py` were byte-identical at diagnosis
  (SHA256 `bee1ce5ac4927ed57566a1acf0345715c1cc8b1e0c0792e1c0e7c435098059f1`).
  India draft-pack YAML and passage catalog also matched the staged r3 versions.
- PacketVerifier has exactly 16 initial deterministic checks and returns before
  entailment when any blocker fails. Thus the observed count and call audit support
  a static blocker, rather than failed model entailment. Count alone cannot identify
  which deterministic check failed.

## Reproduced mechanism, distinct from the actual-run conclusion

The browser harness confirms the synthetic payment fields, caller identifier and
victim bank before intake. It does not confirm `contact.claimedIdentity`. A later
intake delta can add this common packet field from the new victim statement.
Previously, merge_facts recorded that leaf as victim_statement with no reference;
anchor_confirmed_facts supplied missing references only to confirmed values. The
packet provenance check correctly blocked the populated untraceable statement.

The new offline regression constructs the harness-shaped confirmed facts and adds
only `contact.claimedIdentity=bank` through an unanchored merge. For all three India
recipients it reproduces exactly 16 checks, one failed check named `provenance`,
and zero entailment calls. This proves a concrete code defect capable of explaining
the observations. It does not prove that the deleted hosted delta contained this
field or that this was the actual hosted failed check.

Source/form problems are not established by the retained evidence. Bank/app source
refs are empty draft refs, and the cyber reference resolves in the unchanged source
catalog. Required fields are included in the harness confirmation. These facts make
a shared newly populated statement-origin gap a strong hypothesis; they do not
exclude other static failures without the original check IDs.

## Narrow fix and safeguards

- Text ingestion supplies a server-only statement reference bound to its generated
  case ID, actual victim turn ID and next facts revision. The sanitized victim turn
  and fact mutation commit in the same transaction.
- Model-supplied provenance remains ignored. New statement values retain the
  victim_statement source; they are not upgraded to confirmed or extracted.
- Repeated unchanged values retain their prior origins. Legacy unanchored facts
  are not repaired by a generic current-turn reference.
- Composite amount/recipient origins require all relevant components to have the
  same actual statement reference. Mixed or incomplete origins remain fail-closed.
- The verifier was not weakened or edited. Source references were not fabricated.
  The Live path is handled separately by its owner and must require a real durable
  victim caption before passing this optional server reference.

After an actual synthetic message commit, the regression verifies that the origin
points to its durable user turn. All initial deterministic checks pass for all three
recipients, then the injected synthetic entailment implementation is called three
times. This is offline behavior evidence, not provider-quality or cloud evidence.

Validation: five new provenance tests plus 15 existing intake tests passed, 20 total
in 2.42 seconds on the final focused run. Ruff and mypy on the modified intake service
passed. No paid inference, network fetch, deployment or cloud mutation was performed
for this diagnosis/fix. Only test additions followed the service-file freeze.

## Required next evidence

Retain bounded allowlisted failed check IDs/types/severities and attempt counts in
the browser diagnostic before deleting its synthetic case. Record provenance source
and whether an origin exists, without logging raw facts, model output or tokens.
Keep all three packet states visible: job success is not verification success.
An additional hosted run needs separate authorization/budget accounting; no rerun
was performed here. Do not mark the actual r2 cause resolved solely from this
reproduction or from another provider attempt.
