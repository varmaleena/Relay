CREATE TABLE IF NOT EXISTS `{{PROJECT}}.relay_analytics.usage_events` (
  ts TIMESTAMP NOT NULL, case_ref STRING, event STRING, agent STRING, model STRING,
  tokens_in INT64, tokens_out INT64, cost_estimate FLOAT64, price_version STRING,
  latency_ms INT64
) PARTITION BY DATE(ts);
