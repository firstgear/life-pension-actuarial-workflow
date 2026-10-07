"""Section 3 — Assumption models: mortality GLM, disability, lapse."""
import asyncio
import json

from fastapi import APIRouter

from server.common import run_job
from server.config import fqn, get_catalog, get_schema, get_workspace_host
from server.sql import query_safe

router = APIRouter(prefix="/api/assumptions", tags=["assumptions"])


async def _gather(qs: dict) -> dict:
    keys = list(qs)
    res = await asyncio.gather(*[query_safe(qs[k]) for k in keys], return_exceptions=True)
    return {k: (r if isinstance(r, list) else []) for k, r in zip(keys, res)}


@router.get("/mortality")
async def mortality():
    out = await _gather({
        "relativities": f"SELECT * FROM {fqn('mortality_relativities')} WHERE model_version = (SELECT max(cast(model_version AS INT)) FROM {fqn('mortality_relativities')}) ORDER BY factor, level",
        "all_relativities": f"SELECT model_version, label, factor, level, relativity, ci_low, ci_high, is_reference FROM {fqn('mortality_relativities')} ORDER BY cast(model_version AS INT), factor, level",
        "ae": f"SELECT * FROM {fqn('ae_results')} ORDER BY dimension, level",
        "versions": f"SELECT model_version, run_id, trained_at, mart_table_version, code_version, metrics, params FROM {fqn('model_registry_log')} WHERE model_name = 'mortality_glm' ORDER BY cast(model_version AS INT) DESC",
    })
    for v in out["versions"]:
        for k in ("metrics", "params"):
            try:
                v[k] = json.loads(v[k] or "{}")
            except Exception:
                pass
    host = get_workspace_host()
    out["links"] = {"model": f"{host}/explore/data/models/{get_catalog()}/{get_schema()}/mortality_glm",
                    "experiments": f"{host}/ml/experiments"}
    return out


@router.get("/disability")
async def disability():
    return await _gather({
        "incidence": f"SELECT factor, level, relativity, ci_low, ci_high, is_reference, exposure, events, model_version FROM {fqn('disability_incidence_relativities')} ORDER BY factor, level",
        "km": f"SELECT dimension, level, years, still_disabled, median_years FROM {fqn('disability_km_curves')} ORDER BY dimension, level, years",
        "hazard_ratios": f"SELECT * FROM {fqn('disability_recovery_hazard_ratios')}",
    })


@router.get("/lapse")
async def lapse():
    return await _gather({
        "comparison": f"SELECT * FROM {fqn('lapse_model_comparison')}",
        "importance": f"SELECT feature, mean_abs_shap FROM {fqn('lapse_feature_importance')} ORDER BY mean_abs_shap DESC",
        "segments": f"SELECT dimension, segment, n, actual, glm, lgbm FROM {fqn('lapse_segment_fit')} ORDER BY dimension, segment",
        "assumptions": f"SELECT * FROM {fqn('lapse_assumptions')} ORDER BY scheme, product_type",
    })


@router.post("/retrain")
async def retrain():
    return run_job("assumption_training")
