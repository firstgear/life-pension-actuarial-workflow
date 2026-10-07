"""Section 6 — BEL projection engine."""
import asyncio
import json

from fastapi import APIRouter, Request
from pydantic import BaseModel

from server.common import current_user, run_job
from server.config import fqn
from server.sql import esc, query_safe

router = APIRouter(prefix="/api/projection", tags=["projection"])


@router.get("/runs")
async def runs():
    rows = await query_safe(f"SELECT * FROM {fqn('bel_runs')} ORDER BY run_ts DESC LIMIT 25")
    for r in rows:
        try:
            r["bel_by_scheme"] = json.loads(r.get("bel_by_scheme") or "{}")
        except Exception:
            pass
    return rows


@router.get("/runs/{run_id}")
async def run_detail(run_id: str):
    rid = esc(run_id)
    cf, top = await asyncio.gather(
        query_safe(f"SELECT scheme, projection_year, calendar_year, net_cashflow_eur FROM {fqn('bel_cashflows')} WHERE projection_run_id = '{rid}' ORDER BY projection_year, scheme"),
        query_safe(f"""SELECT scheme, sex, sum(policy_count) policies, round(sum(bel_eur)) bel_eur, round(sum(pv_benefits_eur)) pv_benefits,
                   round(sum(pv_premiums_eur)) pv_premiums, round(sum(bel_eur * duration_years)/nullif(sum(bel_eur),0),1) duration
                   FROM {fqn('bel_results')} WHERE projection_run_id = '{rid}' GROUP BY ALL ORDER BY bel_eur DESC"""))
    return {"cashflows": cf, "by_segment": top}


class WhatIf(BaseModel):
    discount_rate: float = 0.025
    mortality_mult: float = 1.0
    lapse_mult: float = 1.0
    scenario_label: str = "What-if"


@router.post("/run")
async def run(body: WhatIf, request: Request):
    return run_job("bel_projection", {**body.model_dump(), "requested_by": current_user(request)})
