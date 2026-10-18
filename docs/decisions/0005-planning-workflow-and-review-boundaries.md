# ADR 0005: durable planning and explicit source review

Status: accepted for M2 local implementation, 15 October 2026.

M2 implements T14–T19. The API queues work; a Firestore transaction claims a
bounded lease and a worker runs classification, jurisdiction resolution and
deterministic planning. The installed Google ADK workflow API coordinates these
three stages using Workflow and FunctionNode. Its deprecated SequentialAgent is
not required. ADK sessions are ephemeral; authoritative jobs, classifications,
immutable plans and audit events live in the repository.

The idempotency key includes canonical facts, recent victim statements, ready
extractions, available pack catalog and explicit preview/version options. This
strengthens the specification's facts-only key: a model omission must not make
new source evidence invisible to reprocessing. A claim token prevents an expired
worker from committing over another worker. Inputs and catalog are rechecked
before committing. Stale plans remain readable with a warning; reprocessing
creates another plan rather than rewriting history. Deletion removes plans,
jobs and idempotency records along with intake data.

Classifier transport/schema failures are retryable failures, distinct from a
successful classification asking for human clarification. Urgency is a product
triage heuristic, not a legal deadline or claim about available funds. Country
selection requires victim evidence; language and currency do not establish it.

Both initial packs remain drafts. Official snapshots, hashes, passages and a
review package make them reviewable, but do not constitute human approval.
Unpublished packs require all local/demo configuration gates and a separate,
unchecked-by-default preview choice for each request. Production cannot use
this exception. Channels and sources retain visible unverified status; no
numeric legal deadline is emitted from these drafts. Bank/payment-app ordering
is Relay's heuristic, not a regulator's prescribed priority.

Planner explanations use authored English/Hindi templates rather than an
additional LLM rewrite. This reduces unsupported claims and inference cost;
Hindi remains a translation draft pending fluent review. Packet generation,
institution sends and tracking remain M3 work and have not been implemented.

Local emulator snapshots rotate between two ignored directories. Only a
successful export advances the import pointer. They reduce interruption loss;
they are not production backups or a guarantee that the newest minute survives.
Unexported data from an earlier terminated emulator could not be recovered.
