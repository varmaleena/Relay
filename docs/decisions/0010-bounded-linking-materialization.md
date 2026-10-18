# ADR 0010: bounded private linking materialization

18 October 2026. T33 requires BigQuery and networkx worker components. Neither
networkx nor the Secret Manager SDK is installed in the current runtime. This
increment uses an equivalent deterministic graph traversal for connected
components and an existing transactional repository for a strictly bounded
private development materialization, with an injected HMAC secret. It does not
claim those source infrastructure requirements complete. This avoids adding
unreviewed dependencies or provisioning from a delegated domain-only task.

Only confirmed or edited scammer-role entities are eligible; unknown/merchant
roles are excluded until explicit product semantics authorize them. Both records
must already be addressed to the receiver's organization before linked references
are returned. This conservative privacy boundary may hide cross-organization
leads, but never reveals an unrelated organization's case reference. Broader
sharing requires a separately authorized projection design.

A deployment must add actual Secret Manager retrieval, BigQuery tables and
retention/deletion reconciliation, worker scheduling, E25/E26 human validation,
Google-model explanation verification and evaluated quality. The finite private
materialization fails explicitly at capacity rather than silently dropping data.
