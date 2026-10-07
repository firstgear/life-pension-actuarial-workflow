# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Model factory — thousands of GLMs in parallel (Spark `applyInPandas`)
# MAGIC One Gompertz-Poisson GLM per **segment x bootstrap replicate**: the same small Python
# MAGIC function, run thousands of times on independent data. Spark ships each group to a worker;
# MAGIC no rewrite of the statistics into Spark — the kernel is plain statsmodels.
# MAGIC A sequential baseline on the driver gives the speed-up (the on-prem "one fit after another").

# COMMAND ----------
import json, time, uuid
from datetime import datetime, timezone
import numpy as np, pandas as pd
from pyspark.sql import functions as F
from common import Ctx, register_lib_for_udfs
from actuarial_lib.glm import fit_segment_gompertz

ctx = Ctx(spark, dbutils, n_bootstrap="10", segment_by="scheme,sex,product_type,region,period", requested_by="scheduler")
register_lib_for_udfs()
seg_cols = [c.strip() for c in ctx.p["segment_by"].split(",") if c.strip()]
n_boot = int(ctx.p["n_bootstrap"])
run_id = uuid.uuid4().hex[:10]

base = (spark.table(ctx.t("experience_mart")).where("exposure > 0")
        .groupBy(*seg_cols, "age").agg({"exposure": "sum", "deaths": "sum"})
        .withColumnRenamed("sum(exposure)", "exposure").withColumnRenamed("sum(deaths)", "deaths"))
work = base.crossJoin(spark.range(n_boot + 1).withColumnRenamed("id", "replicate"))  # replicate 0 = point estimate
n_segments = base.select(*seg_cols).distinct().count()
n_fits = n_segments * (n_boot + 1)
print(f"{n_segments} segments x {n_boot + 1} replicates = {n_fits:,} GLM fits")

# COMMAND ----------
out_schema = ", ".join(f"{c} string" for c in seg_cols) + """, replicate long, intercept double, b_age double,
    deviance double, converged boolean, n_cells int, deaths double, exposure double, fit_ms double"""

def fit_group(pdf: pd.DataFrame) -> pd.DataFrame:
    rep = int(pdf["replicate"].iloc[0])
    res = fit_segment_gompertz(pdf, rng_seed=None if rep == 0 else 1000 + rep)
    row = {c: str(pdf[c].iloc[0]) for c in seg_cols}
    row.update({"replicate": rep, **res})
    return pd.DataFrame([row])

t0 = time.time()
# explicit repartition so AQE doesn't coalesce the fits onto a few tasks
results = work.repartition(256, *seg_cols, "replicate").groupBy(*seg_cols, "replicate").applyInPandas(fit_group, out_schema)
results.withColumn("factory_run_id", F.lit(run_id)) \
       .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(ctx.t("factory_results"))
spark_secs = time.time() - t0
print(f"Spark: {n_fits:,} fits in {spark_secs:.1f}s")

# COMMAND ----------
# Sequential baseline on the driver: time a sample of fits, one after another, and extrapolate.
sample_groups = base.select(*seg_cols).distinct().limit(25).collect()
pdf_all = base.toPandas()
t0 = time.time(); k = 0
for g in sample_groups:
    m = np.ones(len(pdf_all), bool)
    for c in seg_cols:
        m &= pdf_all[c].astype(str).to_numpy() == str(g[c])
    for rep in range(min(n_boot + 1, 4)):
        fit_segment_gompertz(pdf_all[m], rng_seed=None if rep == 0 else 1000 + rep); k += 1
per_fit = (time.time() - t0) / max(k, 1)
seq_secs = per_fit * n_fits
print(f"Sequential estimate: {seq_secs:.1f}s ({per_fit * 1000:.1f} ms/fit) -> speed-up x{seq_secs / spark_secs:.1f}")

# COMMAND ----------
# Segment summary: point estimate + bootstrap 95% interval of the mortality rate at 65
r = spark.table(ctx.t("factory_results")).toPandas()
r["mu65"] = np.exp(r.intercept + r.b_age * 65)
pt = r[r.replicate == 0].set_index(seg_cols)
bs = r[r.replicate > 0].groupby(seg_cols).mu65.quantile([0.025, 0.975]).unstack()
summ = pt[["mu65", "b_age", "deaths", "exposure", "converged"]].join(bs.rename(columns={0.025: "mu65_p025", 0.975: "mu65_p975"})).reset_index()
summ["segment"] = summ[seg_cols].astype(str).agg(" · ".join, axis=1)
summ["relative_to_book"] = summ.mu65 / np.nanmedian(summ.mu65)
summ["factory_run_id"] = run_id
spark.createDataFrame(summ).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(ctx.t("factory_segment_summary"))

now = datetime.now(timezone.utc)
run_row = [(run_id, now, ctx.p["requested_by"], ",".join(seg_cols), n_segments, n_boot, n_fits, float(spark_secs),
            float(seq_secs), float(seq_secs / spark_secs), int(r.converged.sum()), "serverless · Spark applyInPandas",
            ctx.job_run_id())]
spark.createDataFrame(run_row, """factory_run_id string, run_ts timestamp, requested_by string, segment_by string,
    n_segments long, n_bootstrap long, n_fits long, parallel_seconds double, sequential_seconds_est double,
    speedup double, converged long, engine string, job_run_id string""").write.mode("append").saveAsTable(ctx.t("factory_runs"))
ctx.audit("FACTORY_RUN", "model_factory", run_id, details={"n_fits": n_fits, "seconds": round(spark_secs, 1),
                                                         "speedup": round(seq_secs / spark_secs, 1)}, actor=ctx.p["requested_by"])
display(spark.table(ctx.t("factory_runs")).orderBy("run_ts", ascending=False))
