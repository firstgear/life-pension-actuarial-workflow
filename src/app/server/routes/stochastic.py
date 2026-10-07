"""Section 7 — Nested stochastic valuation and stress tests."""
import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from server.common import current_user, run_job
from server.config import fqn
from server.sql import esc, query_safe

router = APIRouter(prefix="/api/stochastic", tags=["stochastic"])


@router.get("/summary")
async def summary():
    runs, stress, fan = await asyncio.gather(
        query_safe(f"SELECT * FROM {fqn('stochastic_runs')} ORDER BY run_ts DESC LIMIT 20"),
        query_safe(f"SELECT * FROM {fqn('stress_results')} WHERE stress_run_id = (SELECT max_by(stress_run_id, run_ts) FROM {fqn('stress_results')}) ORDER BY delta_eur DESC"),
        query_safe(f"""SELECT projection_year, percentile(short_rate, 0.05) p05, percentile(short_rate, 0.25) p25,
                   percentile(short_rate, 0.5) p50, percentile(short_rate, 0.75) p75, percentile(short_rate, 0.95) p95
                   FROM {fqn('silver_economic_scenarios')} GROUP BY projection_year ORDER BY projection_year"""))
    hist = []
    if runs:
        rid = esc(runs[0]["stochastic_run_id"])
        hist = await query_safe(f"""WITH r AS (SELECT total_liability_eur v FROM {fqn('stochastic_results')} WHERE stochastic_run_id = '{rid}'),
            b AS (SELECT min(v) lo, max(v) hi FROM r)
            SELECT bucket, count(*) n, min(lo + (hi - lo) * (bucket - 0.5) / 40) AS mid FROM (
              SELECT width_bucket(v, lo, hi + 1, 40) bucket, lo, hi FROM r, b) GROUP BY bucket ORDER BY bucket""")
    return {"runs": runs, "stress": stress, "rate_fan": fan, "histogram": hist}


class StochRun(BaseModel):
    n_outer: int = 1000
    n_inner: int = 500000
    backend: str = "numpy"


@router.post("/run")
async def run(body: StochRun, request: Request):
    if body.backend not in ("numpy", "numba", "torch"):
        raise HTTPException(400, "backend must be numpy, numba or torch")
    return run_job("stochastic_stress", {"n_outer": min(body.n_outer, 1000), "n_inner": body.n_inner,
                                          "backend": body.backend, "requested_by": current_user(request)})
