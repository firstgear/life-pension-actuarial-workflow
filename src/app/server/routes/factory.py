"""Section 4 — Model factory: thousands of segment GLMs in parallel."""
import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel

from server.common import current_user, job_id, run_job
from server.config import fqn, get_workspace_client
from server.sql import query_safe

router = APIRouter(prefix="/api/factory", tags=["factory"])


@router.get("/runs")
async def runs():
    res = await asyncio.gather(
        query_safe(f"SELECT * FROM {fqn('factory_runs')} ORDER BY run_ts DESC LIMIT 20"),
        query_safe(f"SELECT segment, mu65, mu65_p025, mu65_p975, relative_to_book, deaths, exposure, b_age, converged FROM {fqn('factory_segment_summary')} ORDER BY relative_to_book DESC"),
        return_exceptions=True)
    res = [r if isinstance(r, list) else [] for r in res]
    active = []
    try:
        for r in get_workspace_client().jobs.list_runs(job_id=job_id("model_factory"), active_only=True):
            active.append({"run_id": r.run_id, "run_url": r.run_page_url, "start_time": r.start_time})
    except Exception:
        pass
    return {"runs": res[0], "segments": res[1], "active": active}


class FactoryRun(BaseModel):
    n_bootstrap: int = 50
    segment_by: str = "scheme,sex,product_type,region,period"


@router.post("/run")
async def run(body: FactoryRun, request: Request):
    return run_job("model_factory", {"n_bootstrap": body.n_bootstrap, "segment_by": body.segment_by,
                                     "requested_by": current_user(request)})
