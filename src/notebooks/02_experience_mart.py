# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Experience mart — Spark data parallelism
# MAGIC Joins **approved** experience data to the policy master and aggregates to risk cells
# MAGIC (calendar year x age x sex x scheme x product x salary x sector x region x duration).
# MAGIC Exposure, events and expected deaths on the standard table — the GLM-ready mart.
# MAGIC Writing this table fires the **table-update trigger** on the assumption-model job.

# COMMAND ----------
import time
from common import Ctx, DURATION_BAND_SQL
ctx = Ctx(spark, dbutils, scale_factor="1")
T = ctx.t

approved_experience = f"""
  SELECT y.*, p.sex, p.scheme, p.product_type, p.salary_band, p.employer_sector, p.region, p.retirement_age
  FROM {T('silver_policy_years')} y
  JOIN {T('silver_policies')} p USING (policy_id)
  WHERE y.source_file IN (SELECT source_file FROM {T('extract_approvals')} WHERE status = 'APPROVED')
"""

MART_SQL = f"""
WITH e AS ({approved_experience}),
std AS (SELECT age, sex, qx, annual_improvement FROM {T('silver_base_mortality')})
SELECT
  e.calendar_year,
  CASE WHEN e.calendar_year < 2020 THEN '2015-2019' ELSE '2020+' END AS period,
  e.age,
  concat(cast(floor(e.age / 10) * 10 AS INT), '-', cast(floor(e.age / 10) * 10 + 9 AS INT)) AS age_band,
  e.sex, e.scheme, e.product_type, e.salary_band, e.employer_sector, e.region,
  {DURATION_BAND_SQL} AS duration_band,
  count(*)                          AS policy_years,
  round(sum(e.exposure_years), 4)   AS exposure,
  sum(e.death)                      AS deaths,
  sum(e.disability_incidence)       AS disabilities,
  sum(e.surrender)                  AS surrenders,
  sum(e.paid_up)                    AS paid_ups,
  sum(CASE WHEN e.age < e.retirement_age THEN e.exposure_years ELSE 0 END) AS exposure_pre_retirement,
  round(sum(e.exposure_years * -ln(1 - least(std.qx * pow(1 - std.annual_improvement, e.calendar_year - 2020), 0.99))), 6)
                                    AS expected_deaths_std
FROM e LEFT JOIN std ON e.age = std.age AND e.sex = std.sex
GROUP BY ALL
"""

t0 = time.time()
spark.sql(f"CREATE OR REPLACE TABLE {T('experience_mart')} COMMENT 'GLM-ready experience mart: exposure (life-years) and decrement counts per risk cell, built from APPROVED policy admin extracts only. expected_deaths_std = expected deaths on the STANDARD_2020 table with improvement. Synthetic data.' AS {MART_SQL}")
mart_secs = time.time() - t0
col_comments = {
    "exposure": "Central exposure to risk in life-years", "deaths": "Observed deaths",
    "expected_deaths_std": "Expected deaths on the standard table (A/E denominator)",
    "disabilities": "Disability (loss of earning capacity) incidences", "surrenders": "Surrenders / transfers out (lapse)",
    "paid_ups": "Policies made paid-up (contributions stopped)", "scheme": "Pension scheme: COMPANY_PENSION, PRIVATE_PENSION, LIFE_ANNUITY, DISABILITY_COVER, HEALTH_COVER",
    "product_type": "AVERAGE_RATE (with-profits, guaranteed) or MARKET_RATE (unit-linked)", "period": "Experience period bucket",
}
for c, txt in col_comments.items():
    spark.sql(f"ALTER TABLE {T('experience_mart')} ALTER COLUMN {c} COMMENT '{txt}'")
print(f"experience_mart rebuilt in {mart_secs:.1f}s")

# COMMAND ----------
# MAGIC %md ### Model points (in-force at valuation date) and lapse assumptions

# COMMAND ----------
spark.sql(f"""
CREATE OR REPLACE TABLE {T('model_points')} COMMENT 'In-force model points at 2025-12-31 (age at 2026). Input to the BEL projection engine.' AS
SELECT row_number() OVER (ORDER BY scheme, product_type, sex, salary_band, age, retirement_age) AS model_point_id, *
FROM (
  SELECT scheme, product_type, sex, salary_band, 2026 - year(birth_date) AS age, retirement_age,
         count(*) AS policy_count,
         round(avg(annual_benefit_eur), 0) AS annual_benefit_eur,
         round(avg(annual_premium_eur), 0) AS annual_premium_eur,
         round(sum(savings_balance_eur), 0) AS savings_balance_eur,
         round(avg(guaranteed_rate), 4) AS guaranteed_rate
  FROM {T('silver_policies')}
  WHERE status IN ('ACTIVE', 'PAID_UP', 'IN_PAYMENT', 'DISABLED') AND 2026 - year(birth_date) < 110
  GROUP BY ALL)
""")
spark.sql(f"""
CREATE OR REPLACE TABLE {T('lapse_assumptions')} COMMENT 'Best-estimate annual surrender rates by scheme and product (pre-retirement, 2021+ experience).' AS
SELECT scheme, product_type, sum(surrenders) AS surrenders, round(sum(exposure_pre_retirement), 2) AS exposure,
       round(sum(surrenders) / nullif(sum(exposure_pre_retirement), 0), 5) AS lapse_rate
FROM {T('experience_mart')} WHERE calendar_year >= 2021 GROUP BY ALL
""")

# COMMAND ----------
# MAGIC %md ### Optional: scale the book to show Spark data parallelism
# MAGIC `scale_factor = 100` replicates the experience 100x (~84M policy-years) and runs the same aggregation.

# COMMAND ----------
scale = int(ctx.p["scale_factor"])
if scale > 1:
    t0 = time.time()
    big = spark.sql(approved_experience).crossJoin(spark.range(scale).withColumnRenamed("id", "replica"))
    big.createOrReplaceTempView("big_e")
    n = spark.sql("SELECT count(*) FROM big_e").first()[0]
    cells = spark.sql("""SELECT calendar_year, age, sex, scheme, product_type, salary_band, region, replica,
                                sum(exposure_years) e, sum(death) d FROM big_e GROUP BY ALL""").count()
    secs = time.time() - t0
    spark.createDataFrame([(scale, n, cells, secs)], "scale_factor int, policy_years long, cells long, seconds double") \
        .selectExpr("current_timestamp() AS run_ts", "'experience_mart_scaled' AS workload", "*") \
        .write.mode("append").option("mergeSchema", "true").saveAsTable(T("benchmark_runs"))
    print(f"{n:,} policy-years aggregated to {cells:,} cells in {secs:.1f}s")

v = spark.sql(f"DESCRIBE HISTORY {T('experience_mart')} LIMIT 1").first().version
ctx.audit("MART_REBUILT", "table", T("experience_mart"), version=str(v),
          details={"seconds": round(mart_secs, 1), "scale_factor": scale})
display(spark.sql(f"SELECT period, scheme, round(sum(deaths)/sum(expected_deaths_std),3) AS ae_std, sum(exposure) exposure FROM {T('experience_mart')} GROUP BY ALL ORDER BY ALL"))
