"""Section 1 — Policy extract ingestion: drop an extract (starts job 01), DQ, approve."""
import io
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from server.common import audit, current_user, run_job
from server.config import fqn, get_catalog, get_schema, get_workspace_client, get_workspace_host
from server.sql import esc, execute_query, query_safe

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


def _vol() -> str:
    return f"/Volumes/{get_catalog()}/{get_schema()}/extract_landing"


@router.get("/extracts")
async def extracts():
    return await query_safe(f"SELECT * FROM {fqn('extract_approvals')} ORDER BY requested_at DESC")


@router.get("/landing")
async def landing():
    w = get_workspace_client()
    out = {}
    for d in ("incoming", "staging", "reference"):
        try:
            out[d] = [{"name": f.name, "size": f.file_size, "modified": f.last_modified}
                      for f in w.files.list_directory_contents(f"{_vol()}/{d}") if not f.is_directory]
        except Exception:
            out[d] = []
    return out


@router.get("/quality")
async def quality():
    by_file = await query_safe(f"""
        SELECT b.source_file, b.rows_received, coalesce(q.quarantined, 0) AS quarantined
        FROM (SELECT source_file, count(*) AS rows_received FROM {fqn('bronze_policy_years')} GROUP BY source_file) b
        LEFT JOIN (SELECT source_file, count(*) AS quarantined FROM {fqn('quarantine_policy_years')} GROUP BY source_file) q
          USING (source_file) ORDER BY b.source_file""")
    by_rule = await query_safe(f"""
        SELECT source_file,
          sum(CASE WHEN policy_id IS NULL THEN 1 ELSE 0 END) AS policy_id_present,
          sum(CASE WHEN NOT coalesce(exposure_years > 0 AND exposure_years <= 1, false) THEN 1 ELSE 0 END) AS exposure_in_range,
          sum(CASE WHEN NOT coalesce(age BETWEEN 15 AND 115, false) THEN 1 ELSE 0 END) AS age_plausible
        FROM {fqn('quarantine_policy_years')} GROUP BY source_file""")
    sample = await query_safe(f"SELECT * EXCEPT (ingested_at) FROM {fqn('quarantine_policy_years')} ORDER BY source_file DESC LIMIT 25")
    return {"by_file": by_file, "by_rule": by_rule, "sample": sample}


@router.post("/drop-extract")
async def drop_extract(request: Request):
    """Copy the staged quarterly extract into incoming/ and start job 01 straight away
    (DQ pipeline + approval request). In a workspace with file events enabled, a
    file-arrival trigger on incoming/ does the same thing without the button."""
    w = get_workspace_client()
    src = f"{_vol()}/staging/policy_extract_2026_q3.csv"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dst = f"{_vol()}/incoming/policy_extract_2026_q3_{ts}.csv"
    try:
        data = w.files.download(src).contents.read()
        w.files.upload(dst, io.BytesIO(data), overwrite=True)
    except Exception as e:
        raise HTTPException(500, f"Could not copy extract: {str(e)[:300]}")
    user = current_user(request)
    await audit("EXTRACT_DROPPED", "policy_extract", dst.rsplit("/", 1)[-1], actor=user, details={"bytes": len(data)})
    run = run_job("extract_ingest")
    await audit("JOB_TRIGGERED", "job", "extract_ingest", actor=user, details={"file": dst.rsplit("/", 1)[-1], **run})
    host = get_workspace_host()
    return {"path": dst, "bytes": len(data), "run": run,
            "hint": "Job 01 started: the DQ pipeline validates the extract and raises an approval request below (~3 min).",
            "volume_url": f"{host}/explore/data/volumes/{get_catalog()}/{get_schema()}/extract_landing"}


class Decision(BaseModel):
    decision: str            # APPROVED | REJECTED
    notes: str = ""
    rebuild_mart: bool = True


@router.post("/extracts/{extract_id}/decision")
async def decide(extract_id: str, body: Decision, request: Request):
    if body.decision not in ("APPROVED", "REJECTED"):
        raise HTTPException(400, "decision must be APPROVED or REJECTED")
    user = current_user(request)
    rows = await execute_query(f"SELECT source_file, status FROM {fqn('extract_approvals')} WHERE extract_id = '{esc(extract_id)}'")
    if not rows:
        raise HTTPException(404, "extract not found")
    await execute_query(f"""UPDATE {fqn('extract_approvals')} SET status = '{body.decision}', reviewed_by = '{esc(user)}',
        reviewed_at = current_timestamp(), reviewer_notes = '{esc(body.notes)}' WHERE extract_id = '{esc(extract_id)}'""")
    await audit(f"EXTRACT_{body.decision}", "policy_extract", rows[0]["source_file"], actor=user, details={"notes": body.notes})
    run = None
    if body.decision == "APPROVED" and body.rebuild_mart:
        run = run_job("experience_mart", {"scale_factor": 1})
    return {"ok": True, "run": run}
