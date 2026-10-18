# T15 synthetic classification fixtures

Twenty explicit synthetic scenarios cover the allowed typologies, self-authorized
manipulated transfers, unauthorized access, card misuse, uncertain initiation, low
confidence, English and Hindi. The accompanying outputs are hand-authored **fake
client responses**, not model-generated gold or measured model accuracy. Unit tests
verify strict output handling and domain invariants against those fixtures; independent
live classification evaluation belongs to T19 after integration authorization.

ClassifierAgent uses the configured ModelClient and canonical Classification schema.
The same GoogleGenAIClient native JSON-schema projection and strict local Pydantic
validation from M1 apply. No model ID is hardcoded in domain code. Timing thresholds
120minutes/72hours are constructor configuration; exact UTC boundaries and future or
missing timestamps are tested. Critical recency for a transfer is workflow urgency,
not a legal deadline or assertion that money remains available. Funds stay unknown.

Model rationale is replaced with explicit case fact-path explanations; confidence
below0.7, absent authorization, contradictory classification/facts, and invalid output
require a safe one-question clarification. Unclear confidence is capped below0.7.
No language barrier or distress is invented solely from using Hindi. Caller supplies
only bounded untrusted user history/evidence; secrets are scrubbed before prompting.

Resolver consumes server-loaded, registry-gated Pack objects. Only selected/confirmed
country is definitive; statement confidence must meet0.8, and missing statement
confidence is not promoted. Language/currency alone never select a country. Published
selection uses stable numeric semantic versions. Draft country preview requires both
explicit opt-in and local demo mode, plus country confirmation; generic draft fallback
also requires that opt-in. Placeholders GM/XX/ZZ stay unknown. No reviewer signatures
are generated. Published empty packs in unit tests are synthetic selection fixtures,
not source-validated packs or shipped regulatory content.

Public interface: agents.classification exports ClassifierAgent, JurisdictionResolver,
ResolvedPack and compute_urgency. Classification is the shared canonical schema.
ResolvedPack contains pack/confidence/reason/notice/unverified/needs_country_confirmation
with pack_id and version properties. Registry source integrity/publish authorization
are independent upstream gates; the resolver cannot turn draft into reviewed status.
