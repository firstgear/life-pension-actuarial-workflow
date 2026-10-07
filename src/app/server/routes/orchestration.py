"""Section 10 — Orchestration & compute: the job/trigger catalogue, run any job, pause/unpause."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from databricks.sdk.service import jobs as J

from server.common import JOBS, job_id, run_job
from server.config import get_workspace_client, get_workspace_host

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


def _trigger(s: J.JobSettings) -> tuple[str, str | None, str]:
    if s.continuous:
        return "continuous", s.continuous.pause_status.value if s.continuous.pause_status else "UNPAUSED", "Always on; restarts as soon as a run ends"
    if s.schedule:
        return "scheduled", s.schedule.pause_status.value if s.schedule.pause_status else None, f"cron {s.schedule.quartz_cron_expression} ({s.schedule.timezone_id})"
    t = s.trigger
    if t:
        ps = t.pause_status.value if t.pause_status else None
        if t.file_arrival:
            return "file arrival", ps, t.file_arrival.url
        if t.table_update:
            tables = ", ".join(n.split(".")[-1] for n in (t.table_update.table_names or []))
            label = "model update" if "model_champion_events" in tables else "table update"
            return label, ps, f"on change of {tables}"
        if t.periodic:
            return "periodic", ps, f"every {t.periodic.interval} {t.periodic.unit.value if t.periodic.unit else ''}"
    return "manual", None, "Run now / from the Workbench / API"


@router.get("/jobs")
async def jobs():
    w = get_workspace_client()
    host = get_workspace_host()
    out = []
    for key in JOBS:
        try:
            jid = job_id(key)
            j = w.jobs.get(jid)
        except Exception:
            continue
        s = j.settings
        ttype, pause, detail = _trigger(s)
        last = None
        try:
            for r in w.jobs.list_runs(job_id=jid, limit=1):
                st = r.state
                last = {"run_id": r.run_id, "start_time": r.start_time, "run_url": r.run_page_url,
                        "trigger": r.trigger.value if r.trigger else None,
                        "state": (st.result_state.value if st and st.result_state else
                                  (st.life_cycle_state.value if st and st.life_cycle_state else None))}
        except Exception:
            pass
        compute = "serverless (pipeline)" if any(t.pipeline_task for t in (s.tasks or [])) else \
                  ("orchestrator (run_job tasks)" if any(t.run_job_task for t in (s.tasks or [])) else "serverless (jobs)")
        out.append({"key": key, "job_id": jid, "name": s.name, "description": s.description, "trigger_type": ttype,
                    "pause_status": pause, "trigger_detail": detail, "tasks": [t.task_key for t in (s.tasks or [])],
                    "compute": compute, "last_run": last, "url": f"{host}/jobs/{jid}"})
    return out


@router.post("/jobs/{key}/run")
async def run(key: str):
    if key not in JOBS:
        raise HTTPException(404, "unknown job")
    return run_job(key)


class Pause(BaseModel):
    paused: bool


@router.post("/jobs/{key}/pause")
async def pause(key: str, body: Pause):
    """Toggle the continuous A/E monitor or the nightly schedule (note: the next bundle deploy resets it)."""
    w = get_workspace_client()
    jid = job_id(key)
    s = w.jobs.get(jid).settings
    ps = J.PauseStatus.PAUSED if body.paused else J.PauseStatus.UNPAUSED
    if s.continuous:
        w.jobs.update(jid, new_settings=J.JobSettings(continuous=J.Continuous(pause_status=ps)))
    elif s.schedule:
        sch = s.schedule
        w.jobs.update(jid, new_settings=J.JobSettings(schedule=J.CronSchedule(
            quartz_cron_expression=sch.quartz_cron_expression, timezone_id=sch.timezone_id, pause_status=ps)))
    elif s.trigger:
        t = s.trigger
        t.pause_status = ps
        w.jobs.update(jid, new_settings=J.JobSettings(trigger=t))
    else:
        raise HTTPException(400, "job has no trigger to pause")
    return {"ok": True, "paused": body.paused}
