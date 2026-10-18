CREATE TABLE IF NOT EXISTS `{{PROJECT}}.relay_eval.datasets` (
  dataset_version STRING NOT NULL, created_at TIMESTAMP, n_cases INT64,
  languages ARRAY<STRING>, jurisdictions ARRAY<STRING>, generator_commit STRING
);
CREATE TABLE IF NOT EXISTS `{{PROJECT}}.relay_eval.cases_gold` (
  dataset_version STRING NOT NULL, case_id STRING NOT NULL, jurisdiction STRING,
  language STRING, typology STRING, authorization_type STRING, entities_gold JSON,
  required_recipients ARRAY<STRING>, required_fields JSON, injection_variant BOOL
);
CREATE TABLE IF NOT EXISTS `{{PROJECT}}.relay_eval.runs` (
  run_id STRING NOT NULL, dataset_version STRING, system STRING, model_ids JSON,
  started_at TIMESTAMP, finished_at TIMESTAMP, git_sha STRING
);
CREATE TABLE IF NOT EXISTS `{{PROJECT}}.relay_eval.case_results` (
  run_id STRING NOT NULL, case_id STRING NOT NULL, system STRING, outputs JSON,
  latency_ms INT64, tokens_in INT64, tokens_out INT64, errors ARRAY<STRING>
);
CREATE TABLE IF NOT EXISTS `{{PROJECT}}.relay_eval.metrics` (
  run_id STRING NOT NULL, system STRING, metric STRING, slice STRING,
  value FLOAT64, ci_low FLOAT64, ci_high FLOAT64, n INT64
);
CREATE TABLE IF NOT EXISTS `{{PROJECT}}.relay_eval.packbuilder_results` (
  run_id STRING NOT NULL, source_id STRING, field_type STRING, precision FLOAT64,
  recall FLOAT64, f1 FLOAT64, n_gold INT64, n_pred INT64, critic_rejections INT64
);
