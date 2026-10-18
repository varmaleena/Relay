-- Substitute {{PROJECT}} only after confirming target project and dataset locations.
-- Datasets are provisioned separately with location and scoped access reviewed first.
CREATE TABLE IF NOT EXISTS `{{PROJECT}}.relay_entities.entity_sightings` (
  sighting_id STRING NOT NULL, case_ref STRING NOT NULL, entity_type STRING NOT NULL,
  entity_hmac STRING NOT NULL, first_seen TIMESTAMP NOT NULL, jurisdiction STRING,
  typology STRING, amount_bucket STRING
) PARTITION BY DATE(first_seen) CLUSTER BY entity_type, entity_hmac;
CREATE TABLE IF NOT EXISTS `{{PROJECT}}.relay_entities.case_links` (
  link_id STRING NOT NULL, case_a STRING NOT NULL, case_b STRING NOT NULL,
  shared_entity_types ARRAY<STRING>, link_strength FLOAT64, band STRING,
  computed_at TIMESTAMP, validation_decision STRING, validated_by STRING, validated_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS `{{PROJECT}}.relay_entities.clusters` (
  cluster_id STRING NOT NULL, case_refs ARRAY<STRING>, size INT64,
  entity_types ARRAY<STRING>, created_at TIMESTAMP, explanation STRING,
  explanation_model STRING
);
CREATE TABLE IF NOT EXISTS `{{PROJECT}}.relay_entities.entity_denylist` (
  entity_hmac STRING NOT NULL, reason STRING, added_by STRING, added_at TIMESTAMP
);
