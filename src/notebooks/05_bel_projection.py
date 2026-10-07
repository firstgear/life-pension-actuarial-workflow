# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Best-estimate liability projection
# MAGIC Fired by the **model trigger** when the mortality model's `@champion` alias changes
# MAGIC (or from the Workbench with what-if parameters). Loads the champion from the Unity Catalog
# MAGIC registry, projects 80 years of cash flows per model point with a vectorised NumPy kernel,
# MAGIC and fans the model points out over Spark with `mapInPandas`.

# COMMAND ----------
import json, time, uuid
from datetime import datetime, timezone
import numpy as np, pandas as pd
from common import Ctx, load_champion, register_lib_for_udfs
from actuarial_lib.projection import Assumptions, project, HORIZON, START_YEAR

ctx = Ctx(spark, dbutils, discount_rate="0.025", mortality_mult="1.0", lapse_mult="1.0",
          scenario_label="Base (champion)", requested_by="model trigger")
register_lib_for_udfs()
champ, version = load_champion(ctx, "mortality_glm", "champion")
spec = champ.unwrap_python_model().spec
lapse = {f"{r.scheme}|{r.product_type}": float(r.lapse_rate or 0.0)
         for r in spark.table(ctx.t("lapse_assumptions")).collect()}
A = Assumptions(discount_rate=float(ctx.p["discount_rate"]), mortality_mult=float(ctx.p["mortality_mult"]),
                lapse_mult=float(ctx.p["lapse_mult"]))
run_id = uuid.uuid4().hex[:10]
print("champion mortality_glm v", version, "| assumptions", A)

# COMMAND ----------
mp = spark.table(ctx.t("model_points")).repartition(32)
bel_schema = "model_point_id long, bel_eur double, pv_benefits_eur double, pv_expenses_eur double, pv_premiums_eur double, duration_years double"
cf_schema = "scheme string, projection_year int, net_cashflow_eur double"

def bel_udf(it):
    for pdf in it:
        yield project(pdf, spec, lapse, A)

def cf_udf(it):
    for pdf in it:
        _, cf = project(pdf, spec, lapse, A, return_cashflows=True)
        out = pd.DataFrame(cf, columns=range(1, HORIZON + 1))
        out["scheme"] = pdf["scheme"].to_numpy()
        long = out.groupby("scheme").sum().reset_index().melt(id_vars="scheme", var_name="projection_year", value_name="net_cashflow_eur")
        long["projection_year"] = long["projection_year"].astype(int)
        yield long

t0 = time.time()
bel = mp.mapInPandas(bel_udf, bel_schema)
res = (spark.table(ctx.t("model_points")).join(bel, "model_point_id")
       .selectExpr(f"'{run_id}' AS projection_run_id", f"'{version}' AS model_version", "*"))
res.write.mode("append").option("mergeSchema", "true").saveAsTable(ctx.t("bel_results"))
cf = mp.mapInPandas(cf_udf, cf_schema).groupBy("scheme", "projection_year").sum("net_cashflow_eur") \
       .withColumnRenamed("sum(net_cashflow_eur)", "net_cashflow_eur") \
       .selectExpr(f"'{run_id}' AS projection_run_id", "*", f"{START_YEAR} + projection_year - 1 AS calendar_year")
cf.write.mode("append").option("mergeSchema", "true").saveAsTable(ctx.t("bel_cashflows"))
secs = time.time() - t0

# COMMAND ----------
by_scheme = {r.scheme: float(r.bel) for r in spark.sql(
    f"SELECT scheme, sum(bel_eur) bel FROM {ctx.t('bel_results')} WHERE projection_run_id = '{run_id}' GROUP BY scheme").collect()}
total = sum(by_scheme.values())
n_mp = spark.table(ctx.t("model_points")).count()
row = [(run_id, datetime.now(timezone.utc), str(version), ctx.p["scenario_label"], A.discount_rate, A.mortality_mult,
        A.lapse_mult, total, json.dumps(by_scheme), n_mp, float(secs), ctx.p["requested_by"], ctx.job_run_id())]
spark.createDataFrame(row, """projection_run_id string, run_ts timestamp, model_version string, scenario_label string,
    discount_rate double, mortality_mult double, lapse_mult double, total_bel_eur double, bel_by_scheme string,
    model_points long, seconds double, requested_by string, job_run_id string""").write.mode("append").saveAsTable(ctx.t("bel_runs"))
spark.sql(f"COMMENT ON TABLE {ctx.t('bel_runs')} IS 'One row per BEL projection run: champion model version, assumptions, total best-estimate liability (EUR) and split by scheme.'")
ctx.audit("PROJECTION_RUN", "bel_projection", run_id, str(version),
          {"total_bel_eur": round(total), "scenario": ctx.p["scenario_label"], "seconds": round(secs, 1)}, actor=ctx.p["requested_by"])
print(f"BEL {total / 1e9:,.2f} bn EUR over {n_mp:,} model points in {secs:.1f}s")
