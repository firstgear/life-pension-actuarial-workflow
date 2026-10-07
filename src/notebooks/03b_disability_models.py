# Databricks notebook source
# MAGIC %md
# MAGIC # 03b · Disability (loss of earning capacity) — incidence GLM + recovery survival model
# MAGIC * **Incidence**: Poisson GLM on pre-retirement exposure (statsmodels).
# MAGIC * **Recovery**: Kaplan-Meier curves and a Cox proportional-hazards model on claim durations
# MAGIC   (lifelines) — recovery is the event; death and ongoing claims are censored.

# COMMAND ----------
import json, os, pickle, tempfile
from datetime import datetime, timezone
import mlflow, numpy as np, pandas as pd
from mlflow import MlflowClient
from common import Ctx, SRC, experiment, register_and_alias, has_alias, mart_version
import actuarial_lib
from actuarial_lib.glm import fit_poisson_glm, RatingTableModel, predict_rate

ctx = Ctx(spark, dbutils)
exp_id = experiment(ctx, "assumption-models")
now = datetime.now(timezone.utc)

def promote_if_first(model, version):
    if not has_alias(ctx, model, "champion"):
        MlflowClient().set_registered_model_alias(ctx.t(model), "champion", version)
        ctx.audit("MODEL_PROMOTED", "model", ctx.t(model), version, {"alias": "champion", "reason": "bootstrap"})

# COMMAND ----------
keys = ["age", "sex", "salary_band", "employer_sector", "calendar_year"]
cells = (spark.table(ctx.t("experience_mart")).where("exposure_pre_retirement > 0").groupBy(*keys)
         .agg({"exposure_pre_retirement": "sum", "disabilities": "sum"}).toPandas()
         .rename(columns={"sum(exposure_pre_retirement)": "exposure", "sum(disabilities)": "disabilities"}))
fit = fit_poisson_glm(cells, target="disabilities", factors=["sex", "salary_band", "employer_sector"], continuous=["age"])
with mlflow.start_run(run_name="disability_incidence_glm") as run:
    mlflow.set_tags({"model_family": "disability_incidence", "method": "Poisson GLM (statsmodels)", "data": "synthetic"})
    mlflow.log_params({"factors": "sex,salary_band,employer_sector", "continuous": "age"})
    mlflow.log_metrics(fit.gof)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "rating_table.json"); open(p, "w").write(fit.to_json())
        mlflow.pyfunc.log_model(name="model", python_model=RatingTableModel(), artifacts={"spec": p},
                                code_paths=[os.path.join(SRC, "actuarial_lib")], input_example=cells[keys].head(3),
                                pip_requirements=["numpy", "pandas"])
    inc_run = run.info.run_id
v_inc = register_and_alias(ctx, inc_run, "model", "disability_incidence_glm")
promote_if_first("disability_incidence_glm", v_inc)
rel = fit.relativities.assign(model_name="disability_incidence_glm", model_version=v_inc, trained_at=now)
spark.createDataFrame(rel).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(ctx.t("disability_incidence_relativities"))
print(fit.relativities[["factor", "level", "relativity"]])

# COMMAND ----------
from lifelines import KaplanMeierFitter, CoxPHFitter
claims = spark.table(ctx.t("silver_disability_claims")).toPandas()
claims["recovered"] = (claims.outcome == "RECOVERED").astype(int)
claims["onset_age_group"] = pd.cut(claims.age_at_onset, [0, 39, 49, 59, 120], labels=["<40", "40-49", "50-59", "60+"]).astype(str)

km_rows = []
for dim in ["sex", "onset_age_group"]:
    for lvl, g in claims.groupby(dim):
        km = KaplanMeierFitter().fit(g.duration_years, g.recovered)
        sf = km.survival_function_.reset_index()
        sf.columns = ["years", "still_disabled"]
        sf = sf[sf.years <= 8].iloc[:: max(1, len(sf) // 80)]
        sf["dimension"], sf["level"], sf["median_years"] = dim, str(lvl), float(km.median_survival_time_)
        km_rows.append(sf)
km_df = pd.concat(km_rows)

X = pd.get_dummies(claims[["duration_years", "recovered", "age_at_onset", "sex", "salary_band"]],
                   columns=["sex", "salary_band"], drop_first=True, dtype=float)
cph = CoxPHFitter(penalizer=0.01).fit(X, "duration_years", "recovered")
hr = cph.summary.reset_index()[["covariate", "exp(coef)", "exp(coef) lower 95%", "exp(coef) upper 95%", "p"]]
hr.columns = ["covariate", "hazard_ratio", "ci_low", "ci_high", "p_value"]

class RecoveryModel(mlflow.pyfunc.PythonModel):
    """Predicts probability of still being disabled after 1, 2 and 5 years."""
    def load_context(self, context):
        self.cph = pickle.load(open(context.artifacts["cph"], "rb"))
    def predict(self, context, df, params=None):
        sf = self.cph.predict_survival_function(df, times=[1, 2, 5]).T
        sf.columns = ["p_disabled_1y", "p_disabled_2y", "p_disabled_5y"]
        return sf.reset_index(drop=True)

with mlflow.start_run(run_name="disability_recovery_cox") as run:
    mlflow.set_tags({"model_family": "disability_recovery", "method": "Cox PH (lifelines)", "data": "synthetic"})
    mlflow.log_metrics({"concordance": float(cph.concordance_index_), "n_claims": len(claims),
                        "recoveries": int(claims.recovered.sum())})
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "cph.pkl"); pickle.dump(cph, open(p, "wb"))
        km_df.to_csv(os.path.join(d, "km_curves.csv"), index=False); mlflow.log_artifact(os.path.join(d, "km_curves.csv"))
        mlflow.pyfunc.log_model(name="model", python_model=RecoveryModel(), artifacts={"cph": p},
                                input_example=X.drop(columns=["duration_years", "recovered"]).head(3),
                                pip_requirements=["lifelines", "pandas", "numpy"])
    rec_run = run.info.run_id
v_rec = register_and_alias(ctx, rec_run, "model", "disability_recovery_cox")
promote_if_first("disability_recovery_cox", v_rec)

spark.createDataFrame(km_df.assign(model_version=v_rec)).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(ctx.t("disability_km_curves"))
spark.createDataFrame(hr.assign(model_version=v_rec, concordance=float(cph.concordance_index_))).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(ctx.t("disability_recovery_hazard_ratios"))
for m, v, r in [("disability_incidence_glm", v_inc, inc_run), ("disability_recovery_cox", v_rec, rec_run)]:
    ctx.audit("MODEL_REGISTERED", "model", ctx.t(m), v, {"alias": "challenger", "run_id": r})
display(hr)
