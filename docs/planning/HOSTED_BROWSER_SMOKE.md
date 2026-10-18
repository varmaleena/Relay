# Hosted browser smoke harness

Prepared 17 October 2026. scripts/cloud_browser_smoke.mjs uses real hosted
Firebase anonymous Auth and normal reCAPTCHA Enterprise App Check, real API requests,
Firestore persistence and browser signed GCS PUT. No mocks, route fulfillment, debug
tokens, service-account files or source-module imports. Only newly created synthetic data.

Default phase has no provider actions: consent creates a fresh case, authenticated E4
confirms synthetic facts, reload checks persistence, E6+browser PUT tests real signed
storage. It deliberately does not finalize evidence/enqueue extraction. It then deletes
the case through its owner's API. This does not prove worker/model processing.

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH=(Join-Path (Get-Location) '.tmp/playwright-browsers')
node scripts/cloud_browser_smoke.mjs --hosting APPROVED_HOSTING_HTTPS_ORIGIN --api APPROVED_API_HTTPS_ORIGIN --headful
```

Only after root separately authorizes paid calls, add --phase full --allow-paid. That
phase performs one intake-message UI action, one explicit unreviewed-draft planning
action and one packet-generation action, then expects three recipient drafts and a
real signed PDF. It never approves delivery. Three UI actions are not a guarantee of
three provider requests: multiple writers/verifiers and internal retries can incur more.
No rerun is authorized by a failed check. Evidence processing remains excluded.

App Check automation failure must be recorded; use a normal headful browser and
registered exact preview domain, never a debug/bypass token. Root supplies actual
approved origins after preview deployment. Domain allowlists restrict the harness to
the approved project and API service. Runtime limits/global model attempt budget must
be enforced server-side separately. Polling is existing application behavior, not a
new high-frequency harness loop; UI stage waits are bounded and no paid button retries
are attempted.

Artifacts are desktop/mobile/failure screenshots and result.json under .tmp. The report
retains stage, sanitized status/problem code, pass checks and cleanup result, never
tokens, full network logs, signed URLs, auth storage state or raw exception strings.
Screenshots contain only synthetic UI content. Tokens exist only transiently in browser
memory to reuse the actual authenticated/AppCheck request boundary; they are discarded
on exit. Default output is .tmp/cloud-browser-smoke. Nonzero exit means a failed gate
or cleanup not confirmed204; it is not a passed cloud/model test. Negative token and
cross-user/expired Firestore checks remain separate root-owned gates.

## Actual no-AI security gate, 17 October

Root-authorized run against the approved work-511514 relay-review preview and Mumbai
Cloud Run API passed all seven checks. Real normal App Check worked headless; no bypass
was used. Missing both headers returned401; a valid Firebase ID token without App Check
returned401; a separate browser context obtained its own real anonymous identity and
normal App Check token, created its own case, and was denied403 reading the first case.
Exact preview-origin CORS was allowed, while a foreign origin received no allow-origin
header. Confirmed synthetic facts survived reload and a real browser signed GCS PUT
succeeded without enqueueing extraction. Both owner deletions returned204.

Sanitized evidence: .tmp/cloud-browser-auth-r2/result.json and desktop/mobile screenshots.
No paid UI actions or provider endpoints were invoked by this harness phase. This gate
does not measure inference reliability, worker execution, legal review, human comprehension
or expired direct Firestore reads. The first owner's screenshot/upload was synthetic only.
