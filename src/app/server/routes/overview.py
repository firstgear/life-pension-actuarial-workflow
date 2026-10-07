"""Home page KPIs, app config and generic run status."""
import asyncio
import os

from fastapi import APIRouter

from server.common import run_status
from server.config import fqn, get_catalog, get_schema, get_workspace_client, get_workspace_host
from server.sql import query_safe

router = APIRouter(prefix="/api", tags=["overview"])
GENIE_TITLE = "Actuarial Genie — Life & Pension (synthetic)"  # matches scripts/create_genie_space.py
_genie_id: str | None = None


def _genie_space_id() -> str:
    """GENIE_SPACE_ID if set, else the space created by create_genie_space.py (looked up by title)."""
    global _genie_id
    if os.getenv("GENIE_SPACE_ID"):
        return os.environ["GENIE_SPACE_ID"]
    if not _genie_id:
        try:
            spaces = get_workspace_client().api_client.do("GET", "/api/2.0/genie/spaces").get("spaces", [])
            _genie_id = next((sp["space_id"] for sp in spaces if sp.get("title") == GENIE_TITLE), "")
        except Exception:
            return ""
    return _genie_id or ""


@router.get("/config")
async def config():
    host = get_workspace_host()
    genie = _genie_space_id()
    return {"workspace_host": host, "catalog": get_catalog(), "schema": get_schema(),
            "genie_space_id": genie, "genie_url": f"{host}/genie/rooms/{genie}" if genie else None,
            "catalog_url": f"{host}/explore/data/{get_catalog()}/{get_schema()}",
            "jobs_url": f"{host}/jobs?search=Actuarial%20Workbench"}


@router.get("/overview")
async def overview():
    q = [
        f"SELECT count(*) AS policies, sum(CASE WHEN status IN ('ACTIVE','PAID_UP','IN_PAYMENT','DISABLED') THEN 1 ELSE 0 END) AS in_force FROM {fqn('silver_policies')}",
        f"SELECT round(sum(exposure)) AS life_years, sum(deaths) AS deaths, round(sum(deaths)/sum(expected_deaths_std),3) AS ae_std, min(calendar_year) AS first_year, max(calendar_year) AS last_year FROM {fqn('experience_mart')}",
        f"SELECT total_bel_eur, model_version, scenario_label, run_ts, seconds, model_points FROM {fqn('bel_runs')} ORDER BY run_ts DESC LIMIT 1",
        f"SELECT (SELECT count(*) FROM {fqn('extract_approvals')} WHERE status='PENDING') AS pending_extracts, (SELECT count(*) FROM {fqn('model_approvals')} WHERE status='PENDING') AS pending_models",
        f"SELECT n_fits, parallel_seconds, sequential_seconds_est, speedup, run_ts FROM {fqn('factory_runs')} ORDER BY run_ts DESC LIMIT 1",
        f"SELECT event_ts, event_type, entity_id, entity_version, actor FROM {fqn('audit_log')} ORDER BY event_ts DESC LIMIT 8",
        f"SELECT model_name, new_version, event_ts FROM {fqn('model_champion_events')} ORDER BY event_ts DESC LIMIT 20",
    ]
    res = await asyncio.gather(*[query_safe(s) for s in q], return_exceptions=True)
    res = [r if isinstance(r, list) else [] for r in res]
    champions = {}
    for r in res[6]:
        champions.setdefault(r["model_name"], r["new_version"])
    first = lambda r: r[0] if r else {}
    return {"book": first(res[0]), "experience": first(res[1]), "bel": first(res[2]),
            "pending": first(res[3]), "factory": first(res[4]), "activity": res[5], "champions": champions}


@router.get("/runs/{run_id}")
async def get_run(run_id: int):
    return run_status(run_id)
