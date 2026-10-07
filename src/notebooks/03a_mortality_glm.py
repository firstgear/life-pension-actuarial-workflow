# Databricks notebook source
# MAGIC %md
# MAGIC # 03a · Mortality assumption — Poisson GLM (statsmodels)
# MAGIC `deaths ~ age + year + sex + scheme + product + salary band + duration band, offset log(exposure)`
# MAGIC — log-linear in age (Gompertz) with a calendar-year trend (mortality improvement).
# MAGIC The fit is shipped to MLflow as a **transparent rating table** (base rate x relativities),
# MAGIC registered in Unity Catalog and tagged **@challenger**. Promotion to **@champion** is a
# MAGIC four-eyes decision made in the Workbench, not in code.

# COMMAND ----------
import json, os, tempfile, time, uuid
from datetime import datetime, timezone
import mlflow, numpy as np, pandas as pd
from mlflow.models import infer_signature
from common import Ctx, SRC, experiment, register_and_alias, has_alias, mart_version, load_champion, champion_event
import actuarial_lib
from actuarial_lib.glm import fit_poisson_glm, predict_rate, RatingTableModel

ctx = Ctx(spark, dbutils, factors="sex,scheme,product_type,salary_band,duration_band")
MODEL = "mortality_glm"
keys = ["calendar_year", "age", "sex", "scheme", "product_type", "salary_band", "duration_band"]
cells = (spark.table(ctx.t("experience_mart")).groupBy(*keys)
         .agg({"exposure": "sum", "deaths": "sum", "expected_deaths_std": "sum"}).toPandas()
         .rename(columns={"sum(exposure)": "exposure", "sum(deaths)": "deaths", "sum(expected_deaths_std)": "expected_std"}))
mv_mart = mart_version(ctx)
print(len(cells), "cells;", cells.deaths.sum(), "deaths;", round(cells.exposure.sum()), "life-years")

# COMMAND ----------
exp_id = experiment(ctx, "assumption-models")
bootstrap = not has_alias(ctx, MODEL, "champion")
variants = ([("baseline: age, year, sex, scheme, product, duration", ["sex", "scheme", "product_type", "duration_band"])]
            if bootstrap else [])
variants.append(("candidate: + salary band" if bootstrap else "re-estimate on latest approved experience",
                 [f.strip() for f in ctx.p["factors"].split(",") if f.strip()]))

def log_fit(label, factors):
    fit = fit_poisson_glm(cells, factors=factors, continuous=["age", "year_c"])
    spec = json.loads(fit.to_json())
    expected = predict_rate(spec, cells) * cells.exposure
    ae = float(cells.deaths.sum() / expected.sum())
    with mlflow.start_run(run_name=f"mortality_glm · {label}") as run:
        mlflow.set_tags({"model_family": "mortality", "method": "Poisson GLM (statsmodels)",
                         "data": "synthetic", "mart_table_version": mv_mart})
        mlflow.log_params({"factors": ",".join(factors), "continuous": "age,year_c", "family": "Poisson",
                           "link": "log", "offset": "log(exposure)", "lib_version": actuarial_lib.__version__})
        mlflow.log_metrics({**{k: v for k, v in fit.gof.items()}, "ae_overall": ae, "fit_seconds": fit.fit_seconds,
                            "male_relativity": float(np.exp(fit.params.get("C(sex, Treatment(reference='F'))[T.M]", 0))),
                            "age_slope": fit.params["age"], "annual_improvement": float(1 - np.exp(fit.params["year_c"]))})
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "rating_table.json"); open(p, "w").write(fit.to_json())
            fit.relativities.to_csv(os.path.join(d, "relativities.csv"), index=False)
            mlflow.log_artifact(os.path.join(d, "relativities.csv"))
            example = cells[keys].head(5)
            mlflow.pyfunc.log_model(
                name="model", python_model=RatingTableModel(), artifacts={"spec": p},
                code_paths=[os.path.join(SRC, "actuarial_lib")], input_example=example,
                signature=infer_signature(example, predict_rate(spec, example)),
                pip_requirements=["numpy", "pandas"])
        return fit, run.info.run_id, ae

results = []
for label, factors in variants:
    fit, run_id, ae = log_fit(label, factors)
    version = register_and_alias(ctx, run_id, "model", MODEL, "challenger")
    results.append((label, factors, fit, run_id, ae, version))
    print(label, "-> v", version, fit.gof["aic"], ae)

# COMMAND ----------
# MAGIC %md ### Publish results for the Workbench, Genie and governance

# COMMAND ----------
from mlflow import MlflowClient
now = datetime.now(timezone.utc)
rel_rows, log_rows = [], []
for label, factors, fit, run_id, ae, version in results:
    r = fit.relativities.copy()
    r.insert(0, "model_version", version); r["model_name"] = MODEL; r["label"] = label; r["trained_at"] = now
    rel_rows.append(r)
    log_rows.append((MODEL, version, run_id, exp_id, now, mv_mart, actuarial_lib.__version__,
                     json.dumps({**fit.gof, "ae_overall": ae}), json.dumps({"factors": factors, "label": label}),
                     "challenger", ctx.job_run_id()))
spark.createDataFrame(pd.concat(rel_rows)).write.mode("append").option("mergeSchema", "true").saveAsTable(ctx.t("mortality_relativities"))
spark.createDataFrame(log_rows, spark.table(ctx.t("model_registry_log")).schema).write.mode("append").saveAsTable(ctx.t("model_registry_log"))

if bootstrap:  # first ever run: the baseline becomes the initial champion (documented as such)
    base_v = results[0][5]
    MlflowClient().set_registered_model_alias(ctx.t(MODEL), "champion", base_v)
    MlflowClient().set_registered_model_alias(ctx.t(MODEL), "challenger", results[-1][5])
    spark.sql(f"""INSERT INTO {ctx.t('model_approvals')} VALUES ('{uuid.uuid4().hex[:8]}', '{MODEL}', '{base_v}', NULL,
        'APPROVED', 'system', current_timestamp(), 'Initial baseline model, migrated from the legacy estimation suite.',
        'system (bootstrap)', current_timestamp(), 'Baseline champion.', '{{}}')""")
    ctx.audit("MODEL_PROMOTED", "model", ctx.t(MODEL), base_v, {"alias": "champion", "reason": "bootstrap"})
    champion_event(ctx, MODEL, base_v, None, "system (bootstrap)", "Initial baseline champion")
for label, factors, fit, run_id, ae, version in results:
    ctx.audit("MODEL_REGISTERED", "model", ctx.t(MODEL), version, {"alias": "challenger", "run_id": run_id, "aic": fit.gof["aic"]})

# COMMAND ----------
# A/E by segment for champion vs latest challenger (what the approver looks at)
champ, champ_v = load_champion(ctx, MODEL, "champion")
chall, chall_v = load_champion(ctx, MODEL, "challenger")
c = cells.copy()
c["exp_champion"] = champ.predict(c).to_numpy() * c.exposure
c["exp_challenger"] = chall.predict(c).to_numpy() * c.exposure
c["age_band"] = (c.age // 10 * 10).astype(int).astype(str) + "-" + (c.age // 10 * 10 + 9).astype(int).astype(str)
c["period"] = np.where(c.calendar_year < 2020, "2015-2019", "2020+")
out = []
for dim in ["age_band", "sex", "scheme", "product_type", "salary_band", "period"]:
    g = c.groupby(dim).agg(exposure=("exposure", "sum"), deaths=("deaths", "sum"), exp_champion=("exp_champion", "sum"),
                           exp_challenger=("exp_challenger", "sum"), exp_std=("expected_std", "sum")).reset_index()
    g = g.rename(columns={dim: "level"}); g.insert(0, "dimension", dim); out.append(g)
ae = pd.concat(out)
ae["ae_champion"] = ae.deaths / ae.exp_champion
ae["ae_challenger"] = ae.deaths / ae.exp_challenger
ae["ae_standard_table"] = ae.deaths / ae.exp_std
ae["champion_version"], ae["challenger_version"], ae["computed_at"] = str(champ_v), str(chall_v), now
spark.createDataFrame(ae).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(ctx.t("ae_results"))
spark.sql(f"COMMENT ON TABLE {ctx.t('ae_results')} IS 'Actual vs expected deaths by segment for the champion and challenger mortality models and the standard table. A/E = deaths / expected deaths.'")
display(spark.table(ctx.t("ae_results")))
