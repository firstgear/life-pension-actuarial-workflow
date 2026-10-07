# Databricks notebook source
# MAGIC %md
# MAGIC # 06b · Stress tests — Solvency II-shaped life and interest-rate stresses
# MAGIC Deterministic re-projections of the whole book under each stress, using the champion
# MAGIC mortality model. Illustrative calibration (standard-formula *shaped*, not a regulatory run).

# COMMAND ----------
import uuid
from datetime import datetime, timezone
import pandas as pd
from common import Ctx, load_champion
from actuarial_lib.projection import Assumptions, project, STRESSES

ctx = Ctx(spark, dbutils, requested_by="scheduler")
champ, version = load_champion(ctx)
spec = champ.unwrap_python_model().spec
lapse = {f"{r.scheme}|{r.product_type}": float(r.lapse_rate or 0.0) for r in spark.table(ctx.t("lapse_assumptions")).collect()}
mp = spark.table(ctx.t("model_points")).toPandas()
run_id = uuid.uuid4().hex[:10]

rows = []
for name, kw in STRESSES:
    out = project(mp, spec, lapse, Assumptions(**kw))
    by = out.groupby(mp.scheme).bel_eur.sum()
    rows.append({"stress": name, "bel_eur": float(out.bel_eur.sum()), **{f"bel_{k.lower()}": float(v) for k, v in by.items()}})
res = pd.DataFrame(rows)
base = res.loc[res.stress == "Base", "bel_eur"].iloc[0]
res["delta_eur"] = res.bel_eur - base
res["delta_pct"] = res.delta_eur / base
res["capital_impact_eur"] = res.delta_eur.clip(lower=0)
res.insert(0, "stress_run_id", run_id)
res["model_version"], res["run_ts"], res["requested_by"] = str(version), datetime.now(timezone.utc), ctx.p["requested_by"]
spark.createDataFrame(res).write.mode("append").option("mergeSchema", "true").saveAsTable(ctx.t("stress_results"))
spark.sql(f"COMMENT ON TABLE {ctx.t('stress_results')} IS 'BEL under Solvency II-shaped stresses (longevity, mortality, lapse up/down/mass, expense, interest rates). delta = stressed minus base BEL in EUR.'")
ctx.audit("STRESS_RUN", "stress_test", run_id, str(version), {"stresses": len(res)}, actor=ctx.p["requested_by"])
display(res)
