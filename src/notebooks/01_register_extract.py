# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Register policy admin extract for approval
# MAGIC Runs after the DQ pipeline. For every newly arrived source file: profile it (rows, DQ
# MAGIC drops, exposure, deaths, A/E vs the champion mortality model) and raise an approval request.
# MAGIC The baseline history load is auto-approved; new quarterly extracts wait for an actuary.

# COMMAND ----------
import json, uuid
from datetime import datetime, timezone
from common import Ctx, DURATION_BAND_SQL, load_champion

ctx = Ctx(spark, dbutils)
known = {r.source_file for r in spark.table(ctx.t("extract_approvals")).select("source_file").collect()}
files = [r.source_file for r in spark.sql(f"SELECT DISTINCT source_file FROM {ctx.t('bronze_policy_years')}").collect()]
new_files = [f for f in files if f not in known]
print("new files:", new_files)

# COMMAND ----------
champion, champ_version = load_champion(ctx)
rows = []
for f in new_files:
    rec = spark.sql(f"SELECT count(*) n FROM {ctx.t('bronze_policy_years')} WHERE source_file = '{f}'").first().n
    q = spark.sql(f"SELECT count(*) n FROM {ctx.t('quarantine_policy_years')} WHERE source_file = '{f}'").first().n
    dq = {}
    for rule, cond in {"policy_id_present": "policy_id IS NOT NULL", "exposure_in_range": "exposure_years > 0 AND exposure_years <= 1",
                       "age_plausible": "age BETWEEN 15 AND 115"}.items():
        dq[rule] = spark.sql(f"SELECT count(*) n FROM {ctx.t('quarantine_policy_years')} WHERE source_file = '{f}' AND NOT coalesce({cond}, false)").first().n
    s = spark.sql(f"""
        SELECT y.*, p.sex, p.scheme, p.product_type, p.salary_band, {DURATION_BAND_SQL} AS duration_band
        FROM {ctx.t('silver_policy_years')} y JOIN {ctx.t('silver_policies')} p USING (policy_id)
        WHERE y.source_file = '{f}'""").toPandas()
    expo, deaths = float(s.exposure_years.sum()), int(s.death.sum())
    ae = None
    if champion is not None and len(s):
        expected = float((champion.predict(s) * s.exposure_years).sum())
        ae = deaths / expected if expected else None
    years = sorted(s.calendar_year.unique().tolist()) if len(s) else []
    baseline = f.startswith("policy_years_")
    rows.append((str(uuid.uuid4())[:8], f, f"{years[0]}–{years[-1]}" if years else "", int(rec), int(rec - q), int(q),
                 expo, deaths, deaths / expo if expo else None, ae, json.dumps(dq),
                 "APPROVED" if baseline else "PENDING", datetime.now(timezone.utc), "file-arrival trigger",
                 "system (baseline history load)" if baseline else None,
                 datetime.now(timezone.utc) if baseline else None,
                 "Baseline 2015–2025 experience, reconciled at onboarding." if baseline else None))
    ctx.audit("EXTRACT_RECEIVED", "policy_extract", f, details={"rows": rec, "quarantined": q, "ae_vs_champion": ae,
                                                              "champion_version": champ_version})

if rows:
    spark.createDataFrame(rows, spark.table(ctx.t("extract_approvals")).schema).write.mode("append").saveAsTable(ctx.t("extract_approvals"))
display(spark.table(ctx.t("extract_approvals")).orderBy("requested_at"))
