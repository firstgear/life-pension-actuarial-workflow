# Databricks notebook source
# MAGIC %md
# MAGIC # 04b · Model factory on Ray (illustrative — classic cluster with spot workers)
# MAGIC Same kernel as notebook 04, fanned out as **Ray tasks** instead of Spark groups. Ray is the
# MAGIC better fit when the unit of work is *Python logic* (projection engines, nested simulations,
# MAGIC stateful workers, parameter sweeps) rather than a DataFrame operation.
# MAGIC Spark still does the data plane (read the mart, write results to Delta).
# MAGIC
# MAGIC **Not run in the demo** — shown to illustrate the pattern and the job config (spot + Ray).

# COMMAND ----------
import time
import numpy as np, pandas as pd
import ray
from ray.util.spark import setup_ray_cluster, shutdown_ray_cluster
from common import Ctx
from actuarial_lib.glm import fit_segment_gompertz

ctx = Ctx(spark, dbutils, n_bootstrap="50")
n_boot = int(ctx.p["n_bootstrap"])
seg_cols = ["scheme", "sex", "product_type", "region", "period"]

# Ray-on-Spark: start Ray worker nodes on the Spark cluster's (spot) workers
setup_ray_cluster(min_worker_nodes=2, max_worker_nodes=16, num_cpus_worker_node=8)
ray.init(ignore_reinit_error=True)

# COMMAND ----------
# Data plane: Spark reads the governed mart, hands each segment to Ray via the object store
pdf = (spark.table(ctx.t("experience_mart")).groupBy(*seg_cols, "age")
       .agg({"exposure": "sum", "deaths": "sum"}).toPandas()
       .rename(columns={"sum(exposure)": "exposure", "sum(deaths)": "deaths"}))
groups = {k: ray.put(g) for k, g in pdf.groupby(seg_cols)}

@ray.remote(num_cpus=1)
def fit(seg_key, cells, replicate):
    res = fit_segment_gompertz(cells, rng_seed=None if replicate == 0 else 1000 + replicate)
    return {**dict(zip(seg_cols, seg_key)), "replicate": replicate, **res}

t0 = time.time()
futures = [fit.remote(k, ref, rep) for k, ref in groups.items() for rep in range(n_boot + 1)]
results = pd.DataFrame(ray.get(futures))
print(f"Ray: {len(results):,} fits in {time.time() - t0:.1f}s on {int(ray.cluster_resources().get('CPU', 0))} CPUs")

# COMMAND ----------
spark.createDataFrame(results).write.mode("overwrite").saveAsTable(ctx.t("factory_results_ray"))
shutdown_ray_cluster()
