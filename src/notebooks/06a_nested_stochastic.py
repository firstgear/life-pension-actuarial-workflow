# Databricks notebook source
# MAGIC %md
# MAGIC # 06a · Nested stochastic valuation
# MAGIC ```
# MAGIC outer real-world scenario (ESG rate path x longevity-trend shock)
# MAGIC  ├── liability portfolio re-discounted on the path, mortality scaled by the shock
# MAGIC  └── inner risk-neutral Monte Carlo: cost of the interest-rate guarantee on average-rate savings
# MAGIC ```
# MAGIC Every outer scenario is independent, so chunks of scenarios run as parallel Spark tasks
# MAGIC (`applyInPandas`). `backend` switches the inner kernel: `numpy` (reference), `numba` (JIT CPU)
# MAGIC or `torch` (runs on a GPU when one is attached — e.g. serverless GPU — else CPU).

# COMMAND ----------
import json, time, uuid
from datetime import datetime, timezone
import numpy as np, pandas as pd
from common import Ctx, load_champion, register_lib_for_udfs
from actuarial_lib.projection import Assumptions, project
from actuarial_lib.stochastic import LONGEVITY_GRID, value_outer_scenarios

ctx = Ctx(spark, dbutils, n_outer="1000", n_inner="20000", backend="numpy", requested_by="scheduler")
register_lib_for_udfs()
n_outer, n_inner, backend = int(ctx.p["n_outer"]), int(ctx.p["n_inner"]), ctx.p["backend"]
champ, version = load_champion(ctx)
spec = champ.unwrap_python_model().spec
lapse = {f"{r.scheme}|{r.product_type}": float(r.lapse_rate or 0.0) for r in spark.table(ctx.t("lapse_assumptions")).collect()}
mp = spark.table(ctx.t("model_points")).toPandas()

# Portfolio net cash flows on a grid of longevity multipliers (interpolated per scenario)
cf_grid = np.stack([project(mp, spec, lapse, Assumptions(mortality_mult=m), return_cashflows=True)[1].sum(0)
                    for m in LONGEVITY_GRID])
pol = spark.sql(f"""SELECT guaranteed_rate, sum(savings_balance_eur) bal FROM {ctx.t('silver_policies')}
                    WHERE product_type = 'AVERAGE_RATE' AND status IN ('ACTIVE','PAID_UP') AND savings_balance_eur > 0
                    GROUP BY guaranteed_rate ORDER BY guaranteed_rate""").toPandas()
buckets = pol[["bal", "guaranteed_rate"]].to_numpy(dtype=float)
run_id = uuid.uuid4().hex[:10]

# COMMAND ----------
scen = spark.sql(f"""SELECT scenario_id, array_sort(collect_list(struct(projection_year, short_rate))).short_rate AS rates
                     FROM {ctx.t('silver_economic_scenarios')} WHERE scenario_id <= {n_outer} GROUP BY scenario_id""")
n_chunks = min(64, n_outer)
scen = scen.selectExpr("*", f"scenario_id % {n_chunks} AS chunk")
out_schema = """scenario_id long, longevity_factor double, r0 double, bel_eur double, tvog_eur double,
                total_liability_eur double, calc_ms double"""

def value_chunk(pdf: pd.DataFrame) -> pd.DataFrame:
    ids = pdf.scenario_id.to_numpy()
    rates = np.stack(pdf.rates.to_numpy())
    longevity = np.exp(np.random.default_rng(12345).normal(0, 0.08, 100_000))[ids - 1]   # seeded per scenario id
    return pd.DataFrame(value_outer_scenarios(rates, ids, longevity, cf_grid, buckets, n_inner, backend=backend))

t0 = time.time()
# explicit repartition: AQE would otherwise coalesce this tiny (1,000-row) shuffle into a handful of tasks
res = scen.repartition(n_chunks, "chunk").groupBy("chunk").applyInPandas(value_chunk, out_schema)
res.selectExpr(f"'{run_id}' AS stochastic_run_id", "*").write.mode("append").option("mergeSchema", "true").saveAsTable(ctx.t("stochastic_results"))
secs = time.time() - t0

# COMMAND ----------
r = spark.table(ctx.t("stochastic_results")).where(f"stochastic_run_id = '{run_id}'").toPandas()
tl = r.total_liability_eur
seq_est = r.calc_ms.sum() / 1000
summary = [(run_id, datetime.now(timezone.utc), str(version), n_outer, n_inner, backend, float(tl.mean()),
            float(tl.quantile(0.05)), float(tl.median()), float(tl.quantile(0.95)), float(tl.quantile(0.995)),
            float(tl.quantile(0.995) - tl.mean()), float(r.tvog_eur.mean()), float(r.bel_eur.mean()), float(secs),
            float(seq_est), n_outer * n_inner, ctx.p["requested_by"], ctx.job_run_id())]
spark.createDataFrame(summary, """stochastic_run_id string, run_ts timestamp, model_version string, n_outer long,
    n_inner long, backend string, mean_liability_eur double, p05_eur double, p50_eur double, p95_eur double,
    p995_eur double, scr_proxy_eur double, mean_tvog_eur double, mean_bel_eur double, parallel_seconds double,
    sequential_seconds_est double, inner_paths long, requested_by string, job_run_id string""") \
    .write.mode("append").saveAsTable(ctx.t("stochastic_runs"))
spark.sql(f"COMMENT ON TABLE {ctx.t('stochastic_runs')} IS 'Nested stochastic runs: distribution of total liability (BEL + time value of guarantees) across outer scenarios; scr_proxy = 99.5th percentile minus mean (illustrative).'")
ctx.audit("STOCHASTIC_RUN", "nested_stochastic", run_id, str(version),
          {"n_outer": n_outer, "n_inner": n_inner, "backend": backend, "seconds": round(secs, 1)}, actor=ctx.p["requested_by"])
print(f"{n_outer} outer x {n_inner:,} inner in {secs:.1f}s (sum of task time {seq_est:.1f}s)")
