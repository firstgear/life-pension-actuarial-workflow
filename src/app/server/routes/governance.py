"""Section 8 — Model governance: audit trail, reproducibility, model card."""
import asyncio
import json

from fastapi import APIRouter

from server.config import fqn
from server.sql import esc, query_safe

router = APIRouter(prefix="/api/governance", tags=["governance"])


@router.get("/audit")
async def audit_log(event_type: str | None = None, limit: int = 200):
    where = f"WHERE event_type = '{esc(event_type)}'" if event_type else ""
    return await query_safe(f"SELECT * FROM {fqn('audit_log')} {where} ORDER BY event_ts DESC LIMIT {int(limit)}")


@router.get("/reproducibility")
async def reproducibility():
    rows, events, approvals = await asyncio.gather(
        query_safe(f"SELECT * FROM {fqn('model_registry_log')} ORDER BY trained_at DESC"),
        query_safe(f"SELECT * FROM {fqn('model_champion_events')} ORDER BY event_ts DESC"),
        query_safe(f"SELECT * FROM {fqn('model_approvals')} ORDER BY proposed_at DESC"))
    for r in rows:
        for k in ("metrics", "params"):
            try:
                r[k] = json.loads(r[k] or "{}")
            except Exception:
                pass
    return {"versions": rows, "champion_events": events, "approvals": approvals}
