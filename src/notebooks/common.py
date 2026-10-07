"""Helpers shared by the job notebooks (plain module, imported from the notebook folder)."""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

SRC = os.path.abspath(os.path.join(os.getcwd(), ".."))
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def params(dbutils, **defaults):
    """Read job parameters (exposed as widgets) with defaults."""
    out = {}
    base = {"catalog": "main", "schema": "lp_actuarial", **defaults}
    for k, v in base.items():
        try:
            dbutils.widgets.text(k, str(v))
            out[k] = dbutils.widgets.get(k)
        except Exception:
            out[k] = str(v)
    return out


class Ctx:
    def __init__(self, spark, dbutils, **defaults):
        self.spark, self.dbutils = spark, dbutils
        self.p = params(dbutils, **defaults)
        self.catalog, self.schema = self.p["catalog"], self.p["schema"]
        spark.sql(f"USE CATALOG {self.catalog}")
        spark.sql(f"USE SCHEMA {self.schema}")

    def t(self, name: str) -> str:
        return f"{self.catalog}.{self.schema}.{name}"

    @property
    def user(self) -> str:
        try:
            return self.spark.sql("SELECT current_user()").first()[0]
        except Exception:
            return "unknown"

    def job_run_id(self) -> str:
        try:
            ctx = json.loads(self.dbutils.notebook.entry_point.getDbutils().notebook().getContext().safeToJson())
            return str(ctx["attributes"].get("multitaskParentRunId") or ctx["attributes"].get("currentRunId") or "")
        except Exception:
            return ""

    def audit(self, event_type: str, entity_type: str, entity_id: str, version: str = "",
              details: dict | None = None, actor: str | None = None, source: str = "job"):
        row = [(str(uuid.uuid4()), datetime.now(timezone.utc), event_type, entity_type, entity_id,
                str(version), actor or self.user, json.dumps(details or {}, default=str), source,
                self.job_run_id())]
        df = self.spark.createDataFrame(row, "event_id string, event_ts timestamp, event_type string, entity_type string, entity_id string, entity_version string, actor string, details string, source string, job_run_id string")
        df.write.mode("append").saveAsTable(self.t("audit_log"))


def register_lib_for_udfs():
    """Ship actuarial_lib to Spark workers by value (no wheel needed on serverless)."""
    import actuarial_lib
    from pyspark import cloudpickle
    for mod in (actuarial_lib, actuarial_lib.glm, actuarial_lib.projection, actuarial_lib.stochastic):
        cloudpickle.register_pickle_by_value(mod)


DURATION_BAND_SQL = """CASE WHEN duration_years <= 2 THEN '0-2' WHEN duration_years <= 5 THEN '3-5'
    WHEN duration_years <= 10 THEN '6-10' ELSE '11+' END"""


def load_champion(ctx, model: str = "mortality_glm", alias: str = "champion"):
    """Return (pyfunc_model, version) for the alias, or (None, None) if not set yet."""
    import mlflow
    from mlflow import MlflowClient
    mlflow.set_registry_uri("databricks-uc")
    name = ctx.t(model)
    try:
        mv = MlflowClient().get_model_version_by_alias(name, alias)
    except Exception:
        return None, None
    return mlflow.pyfunc.load_model(f"models:/{name}@{alias}"), mv.version


def experiment(ctx, name: str):
    """MLflow experiment under the deploying user's folder (also declared in the bundle)."""
    import mlflow
    mlflow.set_registry_uri("databricks-uc")
    exp = mlflow.set_experiment(f"/Users/{ctx.user}/lp-actuarial-{name}")
    return exp.experiment_id


def register_and_alias(ctx, run_id: str, artifact: str, model: str, alias: str = "challenger") -> str:
    import mlflow
    from mlflow import MlflowClient
    name = ctx.t(model)
    mv = mlflow.register_model(f"runs:/{run_id}/{artifact}", name)
    c = MlflowClient()
    c.set_registered_model_alias(name, alias, mv.version)
    return str(mv.version)


def has_alias(ctx, model: str, alias: str) -> bool:
    from mlflow import MlflowClient
    try:
        MlflowClient().get_model_version_by_alias(ctx.t(model), alias)
        return True
    except Exception:
        return False


def mart_version(ctx) -> int:
    return int(ctx.spark.sql(f"DESCRIBE HISTORY {ctx.t('experience_mart')} LIMIT 1").first().version)


def champion_event(ctx, model: str, new_version: str, previous: str | None, actor: str, reason: str):
    """Publish an @champion move. The BEL projection job listens to this table (table-update
    trigger) — the stand-in for the model-update trigger where that preview isn't enabled."""
    from datetime import datetime, timezone
    row = [(uuid.uuid4().hex[:10], datetime.now(timezone.utc), model, str(new_version),
            None if previous is None else str(previous), actor, reason)]
    ctx.spark.createDataFrame(row, "event_id string, event_ts timestamp, model_name string, new_version string, previous_version string, actor string, reason string") \
        .write.mode("append").saveAsTable(ctx.t("model_champion_events"))
