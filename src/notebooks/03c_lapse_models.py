# Databricks notebook source
# MAGIC %md
# MAGIC # 03c · Lapse (surrender) — GLM vs LightGBM
# MAGIC The regulator-friendly logistic GLM stays the **champion**; LightGBM is the **challenger** used
# MAGIC to find what the GLM misses (here: the 2022 rate-rise effect on guaranteed products and a
# MAGIC balance x product interaction). SHAP values come straight from LightGBM (`pred_contrib`).

# COMMAND ----------
from datetime import datetime, timezone
import mlflow, numpy as np, pandas as pd
import lightgbm as lgb
import statsmodels.formula.api as smf, statsmodels.api as sm
from mlflow import MlflowClient
from mlflow.models import infer_signature
from sklearn.metrics import roc_auc_score, log_loss
from common import Ctx, experiment, register_and_alias, has_alias

ctx = Ctx(spark, dbutils, sample_rows="400000")
exp_id = experiment(ctx, "assumption-models")
df = spark.sql(f"""
  SELECT y.age, y.duration_years, y.calendar_year, y.surrender, p.scheme, p.product_type, p.salary_band,
         p.guaranteed_rate, log1p(p.savings_balance_eur) AS log_balance
  FROM {ctx.t('silver_policy_years')} y JOIN {ctx.t('silver_policies')} p USING (policy_id)
  WHERE y.age < p.retirement_age AND p.scheme <> 'LIFE_ANNUITY'
""").limit(int(ctx.p["sample_rows"])).toPandas()
cat_cols = ["scheme", "product_type", "salary_band"]
for c in cat_cols:
    df[c] = df[c].astype("category")
rng = np.random.default_rng(42)
test = rng.random(len(df)) < 0.25
tr, te = df[~test], df[test]
features = ["age", "duration_years", "calendar_year", "guaranteed_rate", "log_balance"] + cat_cols
print(len(df), "policy-years;", df.surrender.mean().round(4), "lapse rate")

# COMMAND ----------
glm = smf.glm("surrender ~ age + duration_years + calendar_year + guaranteed_rate + log_balance + C(scheme) + C(product_type) + C(salary_band)",
              data=tr, family=sm.families.Binomial()).fit()
p_glm = glm.predict(te)
gbm = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=200, subsample=0.8,
                         subsample_freq=1, colsample_bytree=0.8, verbose=-1)
gbm.fit(tr[features], tr.surrender)
p_gbm = gbm.predict_proba(te[features])[:, 1]
metrics = {}
for name, p in [("glm", p_glm), ("lgbm", p_gbm)]:
    auc = roc_auc_score(te.surrender, p)
    metrics[name] = {"auc": auc, "gini": 2 * auc - 1, "log_loss": log_loss(te.surrender, np.clip(p, 1e-6, 1 - 1e-6))}
print(metrics)

class GlmWrapper(mlflow.pyfunc.PythonModel):
    def __init__(self, res): self.res = res
    def predict(self, context, df, params=None): return np.asarray(self.res.predict(df))

example = te[features].head(50).astype({c: str for c in cat_cols})
sig_glm = infer_signature(example, np.asarray(p_glm[:50], dtype=float))
sig_gbm = infer_signature(example, p_gbm[:50].astype(float))

with mlflow.start_run(run_name="lapse_glm (logistic)") as run:
    mlflow.set_tags({"model_family": "lapse", "method": "Logistic GLM (statsmodels)", "data": "synthetic"})
    mlflow.log_metrics(metrics["glm"])
    glm.remove_data()
    mlflow.pyfunc.log_model(name="model", python_model=GlmWrapper(glm), signature=sig_glm,
                            pip_requirements=["statsmodels", "pandas", "numpy"])
    glm_run = run.info.run_id
with mlflow.start_run(run_name="lapse_lgbm (LightGBM)") as run:
    mlflow.set_tags({"model_family": "lapse", "method": "LightGBM", "data": "synthetic"})
    mlflow.log_params(gbm.get_params())
    mlflow.log_metrics(metrics["lgbm"])
    mlflow.lightgbm.log_model(gbm, name="model", signature=sig_gbm)
    gbm_run = run.info.run_id

v_glm = register_and_alias(ctx, glm_run, "model", "lapse_glm", "challenger")
v_gbm = register_and_alias(ctx, gbm_run, "model", "lapse_lgbm", "challenger")
for m, v in [("lapse_glm", v_glm), ("lapse_lgbm", v_gbm)]:
    if not has_alias(ctx, m, "champion"):
        MlflowClient().set_registered_model_alias(ctx.t(m), "champion", v)
    ctx.audit("MODEL_REGISTERED", "model", ctx.t(m), v, {"alias": "challenger", **metrics[m.split("_")[1]]})

# COMMAND ----------
# MAGIC %md ### Explainability: SHAP (mean |contribution|) and actual vs predicted by segment

# COMMAND ----------
now = datetime.now(timezone.utc)
contrib = gbm.predict(te[features], pred_contrib=True)[:, :-1]
shap = pd.DataFrame({"feature": features, "mean_abs_shap": np.abs(contrib).mean(0)}).sort_values("mean_abs_shap", ascending=False)
spark.createDataFrame(shap.assign(model_version=v_gbm, computed_at=now)).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(ctx.t("lapse_feature_importance"))

seg = te.assign(p_glm=np.asarray(p_glm), p_lgbm=p_gbm, regime=np.where(te.calendar_year >= 2022, "2022+", "pre-2022"))
rows = []
for dims in [["product_type", "regime"], ["scheme"], ["salary_band"]]:
    g = seg.groupby(dims, observed=True).agg(n=("surrender", "size"), actual=("surrender", "mean"),
                                              glm=("p_glm", "mean"), lgbm=("p_lgbm", "mean")).reset_index()
    g["segment"] = g[dims].astype(str).agg(" · ".join, axis=1)
    rows.append(g[["segment", "n", "actual", "glm", "lgbm"]].assign(dimension="+".join(dims)))
cmp = pd.concat(rows)
spark.createDataFrame(cmp.assign(computed_at=now)).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(ctx.t("lapse_segment_fit"))
summary = pd.DataFrame([{"model": k, **v} for k, v in metrics.items()]).assign(
    model_version=lambda d: np.where(d.model == "glm", v_glm, v_gbm), computed_at=now)
spark.createDataFrame(summary).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(ctx.t("lapse_model_comparison"))
display(cmp)
