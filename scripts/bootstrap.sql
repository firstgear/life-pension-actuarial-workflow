-- Idempotent bootstrap: schema + governed tables that triggers and the app depend on.
-- Run by scripts/deploy.sh BEFORE `databricks bundle deploy` (table-update triggers
-- require their tables to exist when the job is created).
CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}
  COMMENT 'Life & Pension Actuarial Workbench demo (synthetic data). Deployed with Databricks Asset Bundles.';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.audit_log (
  event_id STRING, event_ts TIMESTAMP, event_type STRING, entity_type STRING, entity_id STRING,
  entity_version STRING, actor STRING, details STRING, source STRING, job_run_id STRING)
  COMMENT 'Append-only audit trail: every approval, promotion, job trigger and model registration.';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.extract_approvals (
  extract_id STRING, source_file STRING, extract_period STRING, rows_received BIGINT, rows_passed BIGINT,
  rows_quarantined BIGINT, exposure_years DOUBLE, deaths BIGINT, crude_mortality DOUBLE, ae_vs_champion DOUBLE,
  dq_summary STRING, status STRING, requested_at TIMESTAMP, requested_by STRING, reviewed_by STRING,
  reviewed_at TIMESTAMP, reviewer_notes STRING)
  COMMENT 'Human-in-the-loop gate: policy admin extracts must be APPROVED before they enter the experience mart.';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.model_approvals (
  request_id STRING, model_name STRING, model_version STRING, champion_version STRING, status STRING,
  proposed_by STRING, proposed_at TIMESTAMP, rationale STRING, reviewed_by STRING, reviewed_at TIMESTAMP,
  reviewer_notes STRING, evidence STRING)
  COMMENT 'Four-eyes approval of assumption models: an actuary proposes a challenger, the chief actuary approves it to @champion.';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.model_champion_events (
  event_id STRING, event_ts TIMESTAMP, model_name STRING, new_version STRING, previous_version STRING,
  actor STRING, reason STRING)
  COMMENT 'One row each time a @champion alias moves. Drives the BEL projection job (table-update trigger).';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.model_registry_log (
  model_name STRING, model_version STRING, run_id STRING, experiment_id STRING, trained_at TIMESTAMP,
  mart_table_version BIGINT, code_version STRING, metrics STRING, params STRING, registered_alias STRING,
  job_run_id STRING)
  COMMENT 'Reproducibility tuple per model version: data version + code version + MLflow run.';

-- Placeholder so the table-update trigger can be created; job 02 replaces it with the real mart.
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.experience_mart (calendar_year INT)
  COMMENT 'Placeholder — rebuilt by job 02.';
