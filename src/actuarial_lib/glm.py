"""Poisson GLMs for decrement estimation (mortality, disability incidence).

Standard actuarial set-up: one row per risk cell with observed events and central
exposure, log link, log(exposure) as offset. Results are expressed as a transparent
*rating table* (base rate + multiplicative relativities) — the form an actuary and a
regulator can read, and the form the projection engine consumes.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Reference levels: the "base cell" every relativity is quoted against.
REFERENCE = {
    "sex": "F",
    "scheme": "COMPANY_PENSION",
    "product_type": "AVERAGE_RATE",
    "salary_band": "MID",
    "duration_band": "6-10",
    "employer_sector": "PUBLIC",
    "age_band": "40-49",
}
YEAR_CENTRE = 2020


@dataclass
class GlmFit:
    target: str
    factors: list[str]
    continuous: list[str]
    params: dict[str, float]
    bse: dict[str, float]
    relativities: pd.DataFrame
    gof: dict[str, float]
    fit_seconds: float
    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({"target": self.target, "factors": self.factors,
                           "continuous": self.continuous, "params": self.params,
                           "reference": {f: REFERENCE.get(f) for f in self.factors}})


def _formula(target: str, factors: list[str], continuous: list[str]) -> str:
    terms = [f"C({f}, Treatment(reference='{REFERENCE[f]}'))" for f in factors]
    terms += continuous
    return f"{target} ~ " + " + ".join(terms)


def fit_poisson_glm(cells: pd.DataFrame, target: str = "deaths",
                    factors: list[str] | None = None,
                    continuous: list[str] | None = None,
                    exposure_col: str = "exposure") -> GlmFit:
    """Fit log(E[events]) = log(exposure) + X·beta with statsmodels."""
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    factors = factors if factors is not None else ["sex", "scheme", "product_type", "salary_band", "duration_band"]
    continuous = continuous if continuous is not None else ["age", "year_c"]
    df = cells[cells[exposure_col] > 0].copy()
    if "year_c" in continuous and "year_c" not in df:
        df["year_c"] = df["calendar_year"] - YEAR_CENTRE
    t0 = time.perf_counter()
    model = smf.glm(_formula(target, factors, continuous), data=df,
                    family=sm.families.Poisson(), offset=np.log(df[exposure_col]))
    res = model.fit()
    secs = time.perf_counter() - t0

    params = {k: float(v) for k, v in res.params.items()}
    bse = {k: float(v) for k, v in res.bse.items()}
    rows = []
    for f in factors:
        for lvl in sorted(df[f].astype(str).unique()):
            key = f"C({f}, Treatment(reference='{REFERENCE[f]}'))[T.{lvl}]"
            b, se = params.get(key, 0.0), bse.get(key, 0.0)
            sub = df[df[f].astype(str) == lvl]
            rows.append({"factor": f, "level": lvl, "coef": b,
                         "relativity": float(np.exp(b)),
                         "ci_low": float(np.exp(b - 1.96 * se)), "ci_high": float(np.exp(b + 1.96 * se)),
                         "is_reference": key not in params,
                         "exposure": float(sub[exposure_col].sum()), "events": float(sub[target].sum())})
    for c in continuous:
        b, se = params[c], bse[c]
        rows.append({"factor": c, "level": "per unit", "coef": b, "relativity": float(np.exp(b)),
                     "ci_low": float(np.exp(b - 1.96 * se)), "ci_high": float(np.exp(b + 1.96 * se)),
                     "is_reference": False, "exposure": float(df[exposure_col].sum()),
                     "events": float(df[target].sum())})
    null_dev = float(res.null_deviance)
    gof = {"deviance": float(res.deviance), "null_deviance": null_dev,
           "pseudo_r2": float(1 - res.deviance / null_dev) if null_dev else 0.0,
           "aic": float(res.aic), "n_cells": int(len(df)),
           "events": float(df[target].sum()), "exposure": float(df[exposure_col].sum()),
           "dispersion": float(res.pearson_chi2 / res.df_resid)}
    return GlmFit(target, factors, continuous, params, bse, pd.DataFrame(rows), gof, secs)


def predict_rate(spec: dict, df: pd.DataFrame) -> np.ndarray:
    """Evaluate a fitted rating table (JSON spec from GlmFit.to_json) on a frame."""
    p = spec["params"]
    eta = np.full(len(df), p["Intercept"], dtype=float)
    for c in spec["continuous"]:
        x = (df["calendar_year"] - YEAR_CENTRE) if c == "year_c" and "year_c" not in df else df[c]
        eta += p[c] * np.asarray(x, dtype=float)
    for f in spec["factors"]:
        ref = spec["reference"][f]
        lv = df[f].astype(str).to_numpy()
        eta += np.array([p.get(f"C({f}, Treatment(reference='{ref}'))[T.{v}]", 0.0) for v in lv])
    return np.exp(eta)


def fit_segment_gompertz(cells: pd.DataFrame, rng_seed: int | None = None) -> dict:
    """One small GLM per segment (log mu = a + b*age), optionally on a parametric
    bootstrap resample of the deaths. This is the unit of work the Model Factory fans
    out — thousands of independent fits, embarrassingly parallel."""
    import statsmodels.api as sm

    df = cells[cells["exposure"] > 0]
    y = df["deaths"].to_numpy(dtype=float)
    if rng_seed is not None:
        y = np.random.default_rng(rng_seed).poisson(np.maximum(y, 0.0)).astype(float)
    X = sm.add_constant(df["age"].to_numpy(dtype=float))
    t0 = time.perf_counter()
    try:
        res = sm.GLM(y, X, family=sm.families.Poisson(), offset=np.log(df["exposure"].to_numpy())).fit()
        a, b = float(res.params[0]), float(res.params[1])
        dev, ok = float(res.deviance), True
    except Exception:  # sparse segment — report, don't fail the batch
        a = b = dev = float("nan"); ok = False
    return {"intercept": a, "b_age": b, "deviance": dev, "converged": ok,
            "n_cells": int(len(df)), "deaths": float(y.sum()), "exposure": float(df["exposure"].sum()),
            "fit_ms": (time.perf_counter() - t0) * 1000}


try:  # MLflow wrapper — optional so the kernels import without mlflow installed
    import mlflow.pyfunc

    class RatingTableModel(mlflow.pyfunc.PythonModel):
        """A GLM shipped as a transparent rating table. No statsmodels needed at
        inference — the artefact *is* the base rate + relativities."""

        def load_context(self, context):
            with open(context.artifacts["spec"]) as fh:
                self.spec = json.load(fh)

        def predict(self, context, model_input: pd.DataFrame, params=None):
            return pd.Series(predict_rate(self.spec, model_input), name="rate")
except ImportError:  # pragma: no cover
    RatingTableModel = None  # type: ignore
