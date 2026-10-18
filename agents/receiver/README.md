# Receiver brief agent (T24)

Inject ReceiverBriefAgent(client).make_brief as async briefmaker(projection).
The backend must authorize org ownership and supply an immutable addressed,
approved packet projection. This agent does not authorize access or execute
institution decisions. It accepts no full victim case document and sends no
owner/case ID, raw evidence, signed preview URL or timeline to the model.

The canonical ReceiverBrief has no free summary/linkedCases field. Top-five
keyFacts, missingItems and riskSignals are deterministic; the supplied valid
approved completeness.score is authoritative. If absent, required-field fallback
uses critical-weight2/provenance-aware presence per18.1. Invalid supplied score
fails closed. Canonical victim_statement is treated as the statement source.

Only bounded recommendation reasons and optional victim-language reply originate
in the model. A second exact-index check covers every generated sentence,
translation and completed-decision claims. One20s total deadline includes both
calls/queue waits; no automatic retries or tools. A false/partial/invalid checker,
provider/schema/timeout/safety failure raises BriefUnavailable with a static code.
Backend may show a deterministic view only if briefStatus stays unavailable;
never label that fallback as generated AI output. The checker is fallible, not a
proof of truth or a substitute for staff review/Hindi human review.

The model receives only permitted actions; request_info cannot solicit explicitly
unavailable fields. place_hold_simulated is only suggested for an eligible
supplied bank/timing context and is never executed. No recovery/fund-location or
liability claim is authorized. Full account/card credentials remain forbidden
regardless of a template requirement.

T24 agent code is isolated here. No live model evaluation was performed.
SpecT25 requires an actual A2A agent card/authenticated task/artifact endpoint;
none is implemented by this module and no RPC integration is claimed.
