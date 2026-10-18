# Read-only quota/capacity diagnosis

On15October2026 an ADC-authenticated Service Usage GET returned HTTP200 for
project798642284156 / aiplatform.googleapis.com. Two bounded pages covered372
metrics without truncation. Only safe quota configuration metadata was retained;
there were no inference calls, API enables, quota changes or billing changes.

The snapshot has no gemini-3.8-flash model-specific fixed-quota bucket. The generic
online-prediction request setting has a30000/min default, but it is not a measured
utilization value or a model-specific throughput promise. Null/missing limits
mean unavailable, not zero. ConsumerQuotaMetrics lists configured limits, not the
actual current rate or provider capacity. [Service Usage method documentation](https://docs.cloud.google.com/service-usage/docs/reference/rest/v1beta1/services.consumerQuotaMetrics/list).

The current official3.8Flash model page lists Standard PayGo with usage tiers and
explicitly excludes fixed quota. Thus the evidence does not justify requesting a
larger fixed Gemini RPM quota. [Model consumption options](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash).

Typed HTTP429 outcomes are compatible with pooled Standard PayGo capacity or
usage-tier/acceleration pressure. This read cannot distinguish those mechanisms
or prove which resource was exhausted. The original SDK error prose/details were
not retained; there is no safe historical metadata available to recover that
specific cause. No fresh inference probes were made to reproduce it. Google
recommends global routing where appropriate, bounded backoff and smoother traffic;
this application already usesglobal and a single packet request at a time.
[429 guidance](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/deploy/error-code-429),
[Standard PayGo](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/standard-paygo).

Conclusion: no evidence of an adjustable fixed3.8Flash project quota being hit;
resource/capacity pressure remains the supported operational category, with exact
cause unresolved. The safe next action is retain failures and bounded retries,
not mutate billing/quotas or claim the problem is solved. The user's INR1000
figure remains a target, not an inferred hard cap. This read establishes no spend.

`quota_diagnostic.json` contains the timestamp, HTTP status, pagination coverage,
relevant safe settings and limitations. `mixed_run_fixture_manifest.json` contains
three synthetic artifacts with source-report hashes and content hashes: original
baseline bank plus recovery cyber/payment-app. It explicitly disclaims a3/3
single-batch result and requires normal current API authorization/version gates.
