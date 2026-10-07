"""Shared helpers: identity, audit, job lookup and run status."""
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import Request

from server.config import fqn, get_workspace_client, get_workspace_host
from server.sql import esc, execute_query

logger = logging.getLogger(__name__)

# job key -> (env var set via app.yaml valueFrom, name prefix fallback)
JOBS = {
    "setup":               ("JOB_SETUP",               "Actuarial Workbench · 00"),
    "extract_ingest":         ("JOB_EXTRACT_INGEST",         "Actuarial Workbench · 01"),
    "experience_mart":     ("JOB_EXPERIENCE_MART",     "Actuarial Workbench · 02"),
    "assumption_training": ("JOB_ASSUMPTION_TRAINING", "Actuarial Workbench · 03"),
    "model_factory":       ("JOB_MODEL_FACTORY",       "Actuarial Workbench · 04"),
    "bel_projection":      ("JOB_BEL_PROJECTION",      "Actuarial Workbench · 05"),
    "stochastic_stress":   ("JOB_STOCHASTIC_STRESS",   "Actuarial Workbench · 06"),
    "ae_monitor":          ("JOB_AE_MONITOR",          "Actuarial Workbench · 07"),
    "full_pipeline":       ("JOB_FULL_PIPELINE",       "Actuarial Workbench · 99"),
}
_job_cache: dict[str, int] = {}


def job_id(key: str) -> int:
    if key in _job_cache:
        return _job_cache[key]
    env, prefix = JOBS[key]
    val = os.getenv(env, "")
    if val.isdigit():
        _job_cache[key] = int(val)
        return _job_cache[key]
    for j in get_workspace_client().jobs.list(name=None):
        name = (j.settings.name if j.settings else "") or ""
        if name.startswith(prefix):
            _job_cache[key] = int(j.job_id)
            return _job_cache[key]
    raise KeyError(f"Job '{key}' not found (env {env} / prefix '{prefix}')")


def current_user(request: Request | None) -> str:
    if request is not None:
        for h in ("x-forwarded-email", "x-forwarded-preferred-username", "x-forwarded-user"):
            v = request.headers.get(h)
            if v:
                return v
    return os.getenv("DEMO_USER", "actuary@demo")


def run_job(key: str, params: dict | None = None) -> dict:
    w = get_workspace_client()
    jid = job_id(key)
    run = w.jobs.run_now(job_id=jid, job_parameters={k: str(v) for k, v in (params or {}).items()})
    host = get_workspace_host()
    return {"job_key": key, "job_id": jid, "run_id": run.run_id,
            "run_url": f"{host}/jobs/{jid}/runs/{run.run_id}"}


def run_status(run_id: int) -> dict:
    w = get_workspace_client()
    r = w.jobs.get_run(run_id)
    st = r.state
    life = st.life_cycle_state.value if st and st.life_cycle_state else None
    result = st.result_state.value if st and st.result_state else None
    tasks = [{"task_key": t.task_key,
              "state": (t.state.result_state.value if t.state and t.state.result_state else
                        (t.state.life_cycle_state.value if t.state and t.state.life_cycle_state else None))}
             for t in (r.tasks or [])]
    dur = None
    if r.start_time:
        end = r.end_time or int(datetime.now(timezone.utc).timestamp() * 1000)
        dur = (end - r.start_time) / 1000
    return {"run_id": run_id, "job_id": r.job_id, "life_cycle_state": life, "result_state": result,
            "state_message": st.state_message if st else None, "run_url": r.run_page_url,
            "start_time": r.start_time, "duration_seconds": dur, "tasks": tasks,
            "done": life in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR")}


async def audit(event_type: str, entity_type: str, entity_id: str, version: str = "",
                actor: str = "app", details: dict | None = None) -> None:
    sql = f"""INSERT INTO {fqn('audit_log')} VALUES ('{uuid.uuid4()}', current_timestamp(), '{esc(event_type)}',
        '{esc(entity_type)}', '{esc(entity_id)}', '{esc(version)}', '{esc(actor)}',
        '{esc(json.dumps(details or {}, default=str))}', 'workbench app', NULL)"""
    try:
        await execute_query(sql)
    except Exception:
        logger.exception("audit insert failed")
