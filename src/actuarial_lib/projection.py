"""Best-estimate liability (BEL) cash-flow projection — vectorised over model points.

Deliberately simple but structurally true to a life & pension liability model:
  * decrements: mortality (from the champion GLM rating table), surrender (lapse),
  * pension schemes pay an annuity from retirement age,
  * disability cover pays a disability annuity on incidence, health cover pays claims,
  * premiums (risk products) are an inflow, expenses an outflow,
  * discounting on a flat rate or a per-year curve.
Arrays are [model points x projection years], so one call projects thousands of
model points in milliseconds — and Spark mapInPandas fans the model points out.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from .glm import predict_rate

PENSION_SCHEMES = ("COMPANY_PENSION", "PRIVATE_PENSION", "LIFE_ANNUITY")
HORIZON = 80
START_YEAR = 2026


@dataclass
class Assumptions:
    discount_rate: float = 0.025
    mortality_mult: float = 1.0
    lapse_mult: float = 1.0
    mass_lapse: float = 0.0          # instantaneous lapse at t=0 (Solvency II mass-lapse stress)
    expense_per_policy: float = 60.0
    expense_mult: float = 1.0
    expense_inflation: float = 0.02
    disability_annuity_years: float = 3.2
    health_loss_ratio: float = 0.72
    discount_shift: float = 0.0      # parallel shift added to rate/curve

    def to_dict(self):
        return asdict(self)


def _mortality_matrix(mp: pd.DataFrame, spec: dict, mult: float, horizon: int) -> np.ndarray:
    """mu[i, t] from the rating table: evaluate at t=0 then roll forward with the
    fitted age slope and calendar-year trend (Gompertz + improvement structure)."""
    base = mp.assign(calendar_year=START_YEAR, duration_band="11+")
    mu0 = predict_rate(spec, base)
    p = spec["params"]
    t = np.arange(horizon)
    slope = p.get("age", 0.09) + p.get("year_c", 0.0)
    mu = mu0[:, None] * np.exp(slope * t)[None, :] * mult
    return np.minimum(mu, 3.0)


def project(mp: pd.DataFrame, spec: dict, lapse_rates: dict[str, float],
            a: Assumptions, curve: np.ndarray | None = None,
            horizon: int = HORIZON, return_cashflows: bool = False):
    """Project model points. mp needs: age, sex, scheme, product_type, salary_band,
    policy_count, annual_benefit_eur, annual_premium_eur, retirement_age."""
    n = len(mp)
    t = np.arange(horizon)
    ages = mp["age"].to_numpy()[:, None] + t[None, :]
    ret = mp["retirement_age"].to_numpy()[:, None]
    scheme = mp["scheme"].to_numpy()
    is_pension = np.isin(scheme, PENSION_SCHEMES)[:, None]
    is_annuity = (scheme == "LIFE_ANNUITY")[:, None]
    is_dis = (scheme == "DISABILITY_COVER")[:, None]
    is_health = (scheme == "HEALTH_COVER")[:, None]

    mu = _mortality_matrix(mp, spec, a.mortality_mult, horizon)
    q = 1 - np.exp(-mu)
    q[ages >= 110] = 1.0
    keys = (mp["scheme"] + "|" + mp["product_type"]).to_numpy()
    w0 = np.array([lapse_rates.get(k, 0.03) for k in keys])[:, None] * a.lapse_mult
    pre_ret = ages < ret
    w = np.where(pre_ret & ~is_annuity, np.minimum(w0, 0.95), 0.0)

    surv = (1 - q) * (1 - w)
    inforce = np.ones((n, horizon))
    inforce[:, 1:] = np.cumprod(surv, axis=1)[:, :-1]
    inforce *= (1 - a.mass_lapse * (~is_annuity))
    mid = inforce * (1 - q / 2)                         # mid-year exposure

    ben = mp["annual_benefit_eur"].to_numpy()[:, None]
    prem = mp["annual_premium_eur"].to_numpy()[:, None]
    in_pay = is_annuity | (is_pension & ~pre_ret)
    benefits = np.where(in_pay, mid * ben, 0.0)
    dis_inc = 0.0028 * np.exp(0.045 * (ages - 40))
    claims = np.where(is_dis & pre_ret, mid * dis_inc * ben * a.disability_annuity_years, 0.0)
    claims += np.where(is_health & pre_ret, mid * prem * a.health_loss_ratio, 0.0)
    premiums = np.where((is_dis | is_health) & pre_ret, mid * prem, 0.0)
    expenses = mid * a.expense_per_policy * a.expense_mult * (1 + a.expense_inflation) ** t[None, :]

    if curve is None:
        r = np.full(horizon, a.discount_rate + a.discount_shift)
    else:
        r = np.asarray(curve[:horizon], float) + a.discount_shift
    df = np.cumprod(1 / (1 + r)) * np.sqrt(1 + r)       # mid-year discounting

    cnt = mp["policy_count"].to_numpy()[:, None]
    net = (benefits + claims + expenses - premiums) * cnt
    pv = net * df[None, :]
    out = mp[["model_point_id"]].copy() if "model_point_id" in mp else pd.DataFrame(index=mp.index)
    out["bel_eur"] = pv.sum(axis=1)
    out["pv_benefits_eur"] = ((benefits + claims) * cnt * df).sum(axis=1)
    out["pv_expenses_eur"] = (expenses * cnt * df).sum(axis=1)
    out["pv_premiums_eur"] = (premiums * cnt * df).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["duration_years"] = np.where(pv.sum(1) != 0, (pv * (t + 0.5)).sum(1) / pv.sum(1), 0.0)
    if return_cashflows:
        return out, net  # net undiscounted cash flows [n x horizon]
    return out


# Solvency II-style life underwriting + interest stresses (standard-formula shaped)
STRESSES = [
    ("Base", {}),
    ("Longevity (-20% mortality)", {"mortality_mult": 0.80}),
    ("Mortality (+15% mortality)", {"mortality_mult": 1.15}),
    ("Lapse up (+50%)", {"lapse_mult": 1.50}),
    ("Lapse down (-50%)", {"lapse_mult": 0.50}),
    ("Mass lapse (40%)", {"mass_lapse": 0.40}),
    ("Expense (+10%, +1% inflation)", {"expense_mult": 1.10, "expense_inflation": 0.03}),
    ("Interest rates down (-100bp)", {"discount_shift": -0.01}),
    ("Interest rates up (+100bp)", {"discount_shift": 0.01}),
]
