# ADR 0002: Foundation trust and deterministic rules

Status: accepted for M0, 13 October 2026.

The running API and contract export application are separate. Future business operations are explicit 501 contract stubs. Health is public; nonpublic requests require verified Firebase identity and App Check. Anonymous Firebase accounts may act as victims; receiver and reviewer roles require organization claims. Admin SDK IAM must be scoped separately from Firebase client rules.

Readiness remains 503 with dependency verification status until real probes are installed. This health-specific payload differs from the problem envelope used for request failures. Successful imports or developer authentication alone do not establish readiness.

Pack expressions use an allowlisted AST, canonical schema paths, bounded structures and operation deadlines. Known missing values propagate unknown. Exact Decimal money and trusted aware timestamps retain domain meaning. Arbitrary Python objects are rejected. Calendar additions preserve local calendar dates, elapsed time uses UTC, and DST gaps or ambiguous target times require review. Business calendars are unsupported in v1.

YAML aliases, excessive depth and oversized files are rejected before schema loading. Publication validates references and reviewer metadata but cannot establish legal correctness; human source review remains mandatory. No production pack or reviewer signature is fabricated in M0.

Developer credentials are workspace-local and ignored. Deployed workloads and CI must use service identities and Workload Identity Federation. Mumbai storage is selected for the demo; AI processing location is separately verified per capability. The initial cost target is ₹1,000 through submission, with alerts and workload limits. Billing alerts do not impose a hard spending cap.

The server always generates its request ID. This deliberately changes the spec's supplied-ID echo rule (§14.1), because an arbitrary header may contain volunteered secrets. Logs accept fixed event names, field-specific identifiers/enumerations and finite bounded metrics only. Neither exception text nor model output is logged. The synthetic Cloud Run smoke uses a global model endpoint; it establishes connectivity, not regional residency or application readiness.
