"""Section 5 — Model deployment & four-eyes approval (UC aliases + Delta approval table).

Propose (actuary) -> Approve (chief actuary) -> @champion alias moves -> a row lands in
model_champion_events -> the BEL projection job fires (table-update trigger).
"""
import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from server.common import audit, current_user
from server.config import fqn, get_catalog, get_schema, get_workspace_client, get_workspace_host
from server.sql import esc, execute_query, query_safe

router = APIRouter(prefix="/api/deployment", tags=["deployment"])

MODELS = [
    {"key": "mortality_glm", "label": "Mortality — Poisson GLM", "family": "mortality"},
    {"key": "disability_incidence_glm", "label": "Disability incidence — Poisson GLM", "family": "disability"},
    {"key": "disability_recovery_cox", "label": "Disability recovery — Cox PH (lifelines)", "family": "disability"},
    {"key": "lapse_glm", "label": "Lapse — logistic GLM", "family": "lapse"},
    {"key": "lapse_lgbm", "label": "Lapse — LightGBM", "family": "lapse"},
]


def _aliases(full_name: str) -> dict[str, int]:
    w = get_workspace_client()
    info = w.registered_models.get(full_name, include_aliases=True)
    return {a.alias_name: int(a.version_num) for a in (info.aliases or [])}


@router.get("/models")
async def models():
    w = get_workspace_client()
    host = get_workspace_host()
    out = []
    for m in MODELS:
        full = fqn(m["key"])
        try:
            aliases = await asyncio.to_thread(_aliases, full)
            vers = await asyncio.to_thread(lambda: list(w.model_versions.list(full)))
            versions = [{"version": int(v.version), "created_at": v.created_at, "created_by": v.created_by,
                         "run_id": v.run_id, "status": v.status.value if v.status else None,
                         "aliases": [a for a, n in aliases.items() if n == int(v.version)]}
                        for v in sorted(vers, key=lambda x: int(x.version), reverse=True)]
        except Exception as e:
            aliases, versions = {}, []
        out.append({**m, "full_name": full, "aliases": aliases, "versions": versions,
                    "url": f"{host}/explore/data/models/{get_catalog()}/{get_schema()}/{m['key']}"})
    return out


@router.get("/compare")
async def compare(model: str = "mortality_glm"):
    """Champion vs challenger evidence for the approver."""
    full = fqn(model)
    aliases = await asyncio.to_thread(_aliases, full)
    champ, chall = aliases.get("champion"), aliases.get("challenger")
    log = await query_safe(f"SELECT model_version, metrics, params, trained_at, mart_table_version, code_version, run_id FROM {fqn('model_registry_log')} WHERE model_name = '{esc(model)}'")
    by_v = {}
    for r in log:
        try:
            r["metrics"], r["params"] = json.loads(r["metrics"] or "{}"), json.loads(r["params"] or "{}")
        except Exception:
            pass
        by_v[str(r["model_version"])] = r
    rel = []
    if model == "mortality_glm" and champ and chall:
        rel = await query_safe(f"""SELECT factor, level,
              max(CASE WHEN model_version = '{champ}' THEN relativity END) AS champion,
              max(CASE WHEN model_version = '{chall}' THEN relativity END) AS challenger
            FROM {fqn('mortality_relativities')} WHERE model_version IN ('{champ}', '{chall}') GROUP BY ALL ORDER BY factor, level""")
    ae = await query_safe(f"SELECT dimension, level, deaths, ae_champion, ae_challenger, ae_standard_table FROM {fqn('ae_results')} ORDER BY dimension, level") if model == "mortality_glm" else []
    return {"model": model, "champion": champ, "challenger": chall, "previous_champion": aliases.get("previous_champion"),
            "champion_meta": by_v.get(str(champ)), "challenger_meta": by_v.get(str(chall)), "relativities": rel, "ae": ae}


@router.get("/approvals")
async def approvals():
    return await query_safe(f"SELECT * FROM {fqn('model_approvals')} ORDER BY proposed_at DESC")


class Proposal(BaseModel):
    model: str = "mortality_glm"
    version: int
    rationale: str


@router.post("/propose")
async def propose(body: Proposal, request: Request):
    user = current_user(request)
    full = fqn(body.model)
    aliases = await asyncio.to_thread(_aliases, full)
    pending = await execute_query(f"SELECT request_id FROM {fqn('model_approvals')} WHERE model_name = '{esc(body.model)}' AND status = 'PENDING'")
    if pending:
        raise HTTPException(409, "There is already a pending request for this model")
    rid = uuid.uuid4().hex[:8]
    evidence = await compare(body.model)
    ev = {"challenger_metrics": (evidence.get("challenger_meta") or {}).get("metrics"),
          "champion_metrics": (evidence.get("champion_meta") or {}).get("metrics")}
    await execute_query(f"""INSERT INTO {fqn('model_approvals')} VALUES ('{rid}', '{esc(body.model)}', '{body.version}',
        {f"'{aliases['champion']}'" if 'champion' in aliases else 'NULL'}, 'PENDING', '{esc(user)}', current_timestamp(),
        '{esc(body.rationale)}', NULL, NULL, NULL, '{esc(json.dumps(ev, default=str))}')""")
    await audit("MODEL_PROPOSED", "model", full, str(body.version), user, {"rationale": body.rationale, "request_id": rid})
    return {"request_id": rid}


class Review(BaseModel):
    decision: str            # APPROVED | REJECTED
    notes: str = ""
    acting_as_chief_actuary: bool = True


async def _move_champion(model: str, version: int, actor: str, reason: str) -> int | None:
    w = get_workspace_client()
    full = fqn(model)
    aliases = await asyncio.to_thread(_aliases, full)
    prev = aliases.get("champion")
    if prev is not None and prev != version:
        await asyncio.to_thread(w.registered_models.set_alias, full, "previous_champion", prev)
    await asyncio.to_thread(w.registered_models.set_alias, full, "champion", version)
    await execute_query(f"""INSERT INTO {fqn('model_champion_events')} VALUES ('{uuid.uuid4().hex[:10]}', current_timestamp(),
        '{esc(model)}', '{version}', {f"'{prev}'" if prev is not None else 'NULL'}, '{esc(actor)}', '{esc(reason)}')""")
    await audit("MODEL_PROMOTED", "model", full, str(version), actor, {"alias": "champion", "previous": prev, "reason": reason})
    return prev


@router.post("/approvals/{request_id}/review")
async def review(request_id: str, body: Review, request: Request):
    if body.decision not in ("APPROVED", "REJECTED"):
        raise HTTPException(400, "decision must be APPROVED or REJECTED")
    rows = await execute_query(f"SELECT * FROM {fqn('model_approvals')} WHERE request_id = '{esc(request_id)}'")
    if not rows or rows[0]["status"] != "PENDING":
        raise HTTPException(404, "No pending request with that id")
    req = rows[0]
    user = current_user(request)
    reviewer = f"{user} (as Chief Actuary)" if body.acting_as_chief_actuary else user
    if reviewer == req["proposed_by"]:
        raise HTTPException(403, "Four-eyes rule: the reviewer must differ from the proposer")
    await execute_query(f"""UPDATE {fqn('model_approvals')} SET status = '{body.decision}', reviewed_by = '{esc(reviewer)}',
        reviewed_at = current_timestamp(), reviewer_notes = '{esc(body.notes)}' WHERE request_id = '{esc(request_id)}'""")
    prev = None
    if body.decision == "APPROVED":
        prev = await _move_champion(req["model_name"], int(req["model_version"]), reviewer, body.notes or "Approved in Workbench")
    else:
        await audit("MODEL_REJECTED", "model", fqn(req["model_name"]), req["model_version"], reviewer, {"notes": body.notes})
    return {"ok": True, "previous_champion": prev,
            "hint": "Champion moved; the BEL projection job fires from the model_champion_events table-update trigger (~1 min)."
            if body.decision == "APPROVED" else None}


class Rollback(BaseModel):
    model: str = "mortality_glm"
    reason: str = "Rollback"


@router.post("/rollback")
async def rollback(body: Rollback, request: Request):
    aliases = await asyncio.to_thread(_aliases, fqn(body.model))
    prev = aliases.get("previous_champion")
    if prev is None:
        raise HTTPException(400, "No previous_champion to roll back to")
    await _move_champion(body.model, prev, current_user(request), body.reason)
    return {"ok": True, "champion": prev}
