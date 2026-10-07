# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Setup — governed tables for approvals, audit and champion events
# MAGIC Runs the same idempotent `scripts/bootstrap.sql` the deploy script uses (single source of truth).
# MAGIC Data tables are created by the pipeline and the jobs. **All data in this demo is synthetic.**

# COMMAND ----------
import os
from common import Ctx
ctx = Ctx(spark, dbutils)
sql = open(os.path.join(os.getcwd(), "..", "..", "scripts", "bootstrap.sql")).read().format(catalog=ctx.catalog, schema=ctx.schema)
body = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
for stmt in [s.strip() for s in body.split(";") if s.strip()]:
    spark.sql(stmt)
    print("ok |", " ".join(stmt.split())[:90])
ctx.audit("SETUP", "schema", f"{ctx.catalog}.{ctx.schema}")
