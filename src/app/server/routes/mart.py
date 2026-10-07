"""Section 2 — Experience mart (Spark-built, GLM-ready)."""
import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel

from server.common import current_user, run_job
from server.config import fqn, get_catalog, get_schema, get_workspace_host
from server.sql import query_safe

router = APIRouter(prefix="/api/mart", tags=["mart"])


@router.get("/summary")
async def summary():
    t = fqn("experience_mart")
    qs = {
        "by_year": f"SELECT calendar_year, round(sum(exposure)) exposure, sum(deaths) deaths, round(sum(expected_deaths_std),1) expected, round(sum(deaths)/sum(expected_deaths_std),3) ae_std, sum(surrenders) surrenders, sum(disabilities) disabilities FROM {t} GROUP BY ALL ORDER BY 1",
        "by_scheme": f"SELECT scheme, round(sum(exposure)) exposure, sum(deaths) deaths, round(sum(deaths)/sum(expected_deaths_std),3) ae_std, round(sum(surrenders)/nullif(sum(exposure_pre_retirement),0),4) lapse_rate, round(sum(disabilities)/nullif(sum(exposure_pre_retirement),0),5) disability_rate FROM {t} GROUP BY ALL ORDER BY exposure DESC",
        "by_age_sex": f"SELECT age_band, sex, round(sum(exposure)) exposure, sum(deaths) deaths, round(1000*sum(deaths)/sum(exposure),2) crude_rate_per_mille FROM {t} GROUP BY ALL ORDER BY 1, 2",
        "totals": f"SELECT count(*) cells, round(sum(exposure)) exposure, sum(deaths) deaths, sum(surrenders) surrenders, sum(paid_ups) paid_ups, sum(disabilities) disabilities FROM {t}",
        "sample": f"SELECT * FROM {t} ORDER BY exposure DESC LIMIT 20",
        "history": f"SELECT version, timestamp, operation, operationMetrics.numOutputRows AS rows, userName FROM (DESCRIBE HISTORY {t}) ORDER BY version DESC LIMIT 10",
        "model_points": f"SELECT scheme, count(*) model_points, sum(policy_count) policies, round(sum(savings_balance_eur)) savings_eur FROM {fqn('model_points')} GROUP BY ALL ORDER BY policies DESC",
        "benchmarks": f"SELECT * FROM {fqn('benchmark_runs')} ORDER BY run_ts DESC LIMIT 5",
    }
    keys = list(qs)
    res = await asyncio.gather(*[query_safe(qs[k]) for k in keys], return_exceptions=True)
    out = {k: (r if isinstance(r, list) else []) for k, r in zip(keys, res)}
    host = get_workspace_host()
    out["links"] = {"table": f"{host}/explore/data/{get_catalog()}/{get_schema()}/experience_mart",
                    "lineage": f"{host}/explore/data/{get_catalog()}/{get_schema()}/experience_mart/lineage"}
    return out


class Rebuild(BaseModel):
    scale_factor: int = 1


@router.post("/rebuild")
async def rebuild(body: Rebuild, request: Request):
    return run_job("experience_mart", {"scale_factor": body.scale_factor})
