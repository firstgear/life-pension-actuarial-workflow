# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Continuous A/E monitor
# MAGIC Runs as a **continuous job**: incrementally processes new silver experience rows
# MAGIC (Structured Streaming, `availableNow` on serverless — the continuous job restarts it
# MAGIC immediately), scoring expected deaths with the current champion. Early warning if
# MAGIC experience drifts away from the assumption.

# COMMAND ----------
from pyspark.sql import functions as F
import pandas as pd
from common import Ctx, DURATION_BAND_SQL, load_champion

ctx = Ctx(spark, dbutils)
champ, version = load_champion(ctx)
spec = champ.unwrap_python_model().spec
policies = spark.table(ctx.t("silver_policies")).select("policy_id", "sex", "scheme", "product_type", "salary_band")

def score(batch_df, batch_id):
    from actuarial_lib.glm import predict_rate
    pdf = (batch_df.join(policies, "policy_id").withColumn("duration_band", F.expr(DURATION_BAND_SQL)).toPandas())
    if pdf.empty:
        return
    pdf["expected"] = predict_rate(spec, pdf) * pdf.exposure_years
    g = pdf.groupby(["source_file", "scheme"]).agg(exposure=("exposure_years", "sum"), deaths=("death", "sum"),
                                                    expected=("expected", "sum")).reset_index()
    g["ae"] = g.deaths / g.expected
    g["champion_version"], g["batch_id"] = str(version), batch_id
    spark.createDataFrame(g).withColumn("scored_at", F.current_timestamp()) \
        .write.mode("append").option("mergeSchema", "true").saveAsTable(ctx.t("ae_monitor"))

(spark.readStream.table(ctx.t("silver_policy_years"))
 .writeStream.foreachBatch(score)
 .option("checkpointLocation", f"/Volumes/{ctx.catalog}/{ctx.schema}/artifacts/_checkpoints/ae_monitor")
 .trigger(availableNow=True).start().awaitTermination())
