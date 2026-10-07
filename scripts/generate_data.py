"""
Seeded synthetic life & pension book for the Actuarial Workbench demo.

Everything here is SYNTHETIC and ILLUSTRATIVE — no real customer data. Amounts are in EUR
and sized for a generic European life & pension insurer. The generator is
fully seeded, so the same command always produces the same CSVs (demos must be
reproducible to the number).

The "true" decrement rates are written down explicitly below (TRUE_* constants) so the
demo is defensible: the GLMs on Databricks should recover what we planted.

Outputs (./data):
  policies.csv              one row per policy (static attributes + status at 2025-12-31)
  policy_years.csv          one row per policy x calendar year 2015-2025 (exposure + events)
  disability_claims.csv     one row per disability claim (duration, outcome) — survival data
  base_mortality.csv        standard table qx by age x sex + annual improvement
  economic_scenarios.csv    1,000 real-world scenarios x 60 years (rates, equity, inflation)
  policy_extract_2026_q3.csv a NEW quarterly extract, dropped live to fire the file-arrival trigger
                            (contains a handful of deliberately bad rows for the DQ gate)

Usage:  python scripts/generate_data.py [--policies 100000]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20261006
OUT = Path(__file__).resolve().parents[1] / "data"
FIRST_YEAR, LAST_YEAR = 2015, 2025
VALUATION_DATE = "2025-12-31"

# --------------------------------------------------------------------------- #
# Dimensions                                                                   #
# --------------------------------------------------------------------------- #
# scheme code, label, mix weight, entry-age range, mortality mult, lapse mult
SCHEMES = [
    ("COMPANY_PENSION", "Company Pension", 0.45, (25, 55), 1.00, 1.00),
    ("PRIVATE_PENSION", "Private Pension", 0.20, (25, 60), 1.05, 1.40),
    ("LIFE_ANNUITY",    "Life Annuity",    0.15, (60, 75), 0.82, 0.10),
    ("DISABILITY_COVER", "Disability Cover", 0.12, (25, 55), 1.55, 1.60),
    ("HEALTH_COVER",    "Health Cover",    0.08, (25, 60), 1.20, 2.00),
]
SCHEME_CODES = [s[0] for s in SCHEMES]
PRODUCT_TYPES = ["AVERAGE_RATE", "MARKET_RATE"]       # with-profits guarantee vs unit-linked
SALARY_BANDS = ["LOW", "MID", "HIGH"]
SECTORS = ["PUBLIC", "FINANCE", "INDUSTRY", "HEALTHCARE", "CONSTRUCTION", "IT"]
REGIONS = ["CAPITAL", "NORTH", "SOUTH", "EAST", "WEST"]

# --------------------------------------------------------------------------- #
# Ground truth                                                                 #
# --------------------------------------------------------------------------- #
# Gompertz mortality: mu(x) = B * exp(C * x)   (log-linear in age -> a Poisson GLM
# with age as a covariate is correctly specified and recovers C exactly)
TRUE_B, TRUE_C = 2.2e-5, 0.092
TRUE_MALE = 1.33
TRUE_DURATION = {"0-2": 0.85, "3-5": 0.95, "6-10": 1.00, "11+": 1.00}
TRUE_PRODUCT = {"AVERAGE_RATE": 1.00, "MARKET_RATE": 0.95}
TRUE_SALARY = {"LOW": 1.20, "MID": 1.00, "HIGH": 0.85}
TRUE_IMPROVEMENT = 0.015          # 1.5% p.a. mortality improvement by calendar year

# Disability incidence (active members below retirement)
DIS_BASE, DIS_AGE = 0.0028, 0.045
DIS_FEMALE = 1.15
DIS_SECTOR = {"PUBLIC": 1.0, "FINANCE": 0.7, "INDUSTRY": 1.4, "HEALTHCARE": 1.3,
              "CONSTRUCTION": 1.8, "IT": 0.6}
DIS_SALARY = {"LOW": 1.4, "MID": 1.0, "HIGH": 0.7}


def duration_band(d: np.ndarray) -> np.ndarray:
    return np.select([d <= 2, d <= 5, d <= 10], ["0-2", "3-5", "6-10"], "11+")


def mortality(age, sex, scheme_mult, dur_band, product, salary, year):
    mu = TRUE_B * np.exp(TRUE_C * age)
    mu = mu * np.where(sex == "M", TRUE_MALE, 1.0) * scheme_mult
    mu = mu * pd.Series(dur_band).map(TRUE_DURATION).to_numpy()
    mu = mu * pd.Series(product).map(TRUE_PRODUCT).to_numpy()
    mu = mu * pd.Series(salary).map(TRUE_SALARY).to_numpy()
    mu = mu * (1 - TRUE_IMPROVEMENT) ** (year - 2020)
    return np.minimum(mu, 0.6)


def lapse_prob(age, duration, scheme_lapse, product, balance, year, salary):
    """Surrender probability — deliberately non-linear (U-shape in duration, interest-rate
    regime shift in 2022, balance x product interaction) so a GBM has something to find
    that a main-effects GLM misses."""
    z = -3.6 + np.log(scheme_lapse)
    z += 0.55 * np.exp(-duration / 2.0)                       # early-duration lapses
    z += 0.25 * (duration > 15)                               # late "reshuffle" bump
    z += -0.03 * np.clip(age - 30, 0, None)                   # older members lapse less
    z += np.where(product == "MARKET_RATE", 0.25, -0.15)
    z += np.where((product == "AVERAGE_RATE") & (year >= 2022), 0.45, 0.0)  # rates up -> leave guarantee
    z += np.where((balance > 200_000) & (product == "MARKET_RATE"), 0.4, 0.0)
    z += np.where(salary == "LOW", 0.2, 0.0)
    return 1 / (1 + np.exp(-z))


def generate(n_policies: int, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    # ---------------- policies ----------------
    w = np.array([s[2] for s in SCHEMES])
    sch_idx = rng.choice(len(SCHEMES), size=n_policies, p=w / w.sum())
    scheme = np.array(SCHEME_CODES)[sch_idx]
    entry_year = rng.integers(1990, 2025, size=n_policies)
    lo = np.array([SCHEMES[i][3][0] for i in sch_idx])
    hi = np.array([SCHEMES[i][3][1] for i in sch_idx])
    entry_age = rng.integers(lo, hi + 1)
    birth_year = entry_year - entry_age
    sex = np.where(rng.random(n_policies) < 0.49, "M", "F")
    product = np.where(scheme == "LIFE_ANNUITY", "AVERAGE_RATE",
                       np.where(rng.random(n_policies) < 0.45, "AVERAGE_RATE", "MARKET_RATE"))
    salary = rng.choice(SALARY_BANDS, size=n_policies, p=[0.3, 0.5, 0.2])
    sector = rng.choice(SECTORS, size=n_policies, p=[0.30, 0.15, 0.20, 0.15, 0.10, 0.10])
    region = rng.choice(REGIONS, size=n_policies, p=[0.33, 0.15, 0.21, 0.23, 0.08])
    retirement_age = rng.choice([65, 67, 68, 69], size=n_policies, p=[0.15, 0.35, 0.35, 0.15])
    sal_mult = pd.Series(salary).map({"LOW": 0.6, "MID": 1.0, "HIGH": 1.9}).to_numpy()
    annual_premium = np.round(rng.lognormal(np.log(7_000), 0.35, n_policies) * sal_mult, -2)
    annual_premium = np.where(scheme == "LIFE_ANNUITY", 0.0, annual_premium)
    annual_premium = np.where(np.isin(scheme, ["DISABILITY_COVER", "HEALTH_COVER"]),
                              np.round(annual_premium * 0.08, -1), annual_premium)
    years_paid = np.clip(2025 - entry_year, 0, None)
    balance = np.round(annual_premium * years_paid * rng.lognormal(0.15, 0.25, n_policies), -3)
    balance = np.where(scheme == "LIFE_ANNUITY", np.round(rng.lognormal(np.log(240_000), 0.5, n_policies), -3), balance)
    balance = np.where(np.isin(scheme, ["DISABILITY_COVER", "HEALTH_COVER"]), 0.0, balance)
    guaranteed_rate = np.where(product == "AVERAGE_RATE",
                               rng.choice([0.0, 0.005, 0.015, 0.025, 0.045], size=n_policies,
                                          p=[0.25, 0.25, 0.2, 0.2, 0.1]), 0.0)
    # Annual benefit: annuity from retirement (pensions), or disability annuity (cover)
    annual_benefit = np.where(np.isin(scheme, ["COMPANY_PENSION", "PRIVATE_PENSION", "LIFE_ANNUITY"]),
                              np.round(np.maximum(balance, 7_000) / 16.0 * rng.lognormal(0.2, 0.15, n_policies), -2),
                              np.where(scheme == "DISABILITY_COVER",
                                       np.round(annual_premium / 0.08 * 2.2, -2),
                                       np.round(annual_premium * 0.75, -2)))

    # ---------------- policy-years simulation (vectorised over policies) ----------------
    alive = np.ones(n_policies, bool)
    status = np.array(["ACTIVE"] * n_policies, dtype=object)
    paid_up_flag = np.zeros(n_policies, bool)
    disabled = np.zeros(n_policies, bool)
    scheme_mort = np.array([SCHEMES[i][4] for i in sch_idx])
    scheme_lapse = np.array([SCHEMES[i][5] for i in sch_idx])
    pid = np.array([f"P{i:07d}" for i in range(n_policies)])

    rows, claims = [], []
    claim_seq = 0
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        inforce = alive & (entry_year <= year)
        idx = np.where(inforce)[0]
        if idx.size == 0:
            continue
        age = year - birth_year[idx]
        dur = year - entry_year[idx]
        dband = duration_band(dur)
        # partial first year of exposure
        expo = np.where(entry_year[idx] == year, rng.uniform(0.1, 1.0, idx.size), 1.0)
        mu = mortality(age, sex[idx], scheme_mort[idx], dband, product[idx], salary[idx], year)
        death = rng.random(idx.size) < 1 - np.exp(-mu * expo)

        pre_ret = age < retirement_age[idx]
        can_lapse = pre_ret & ~np.isin(scheme[idx], ["LIFE_ANNUITY"]) & ~death & ~disabled[idx]
        lp = lapse_prob(age, dur, scheme_lapse[idx], product[idx], balance[idx], year, salary[idx])
        surrender = can_lapse & (rng.random(idx.size) < lp * expo)
        # paid-up (stop contributing, stay insured)
        pu_rate = 0.02 * np.where(salary[idx] == "LOW", 1.6, 1.0) * np.where(year >= 2020, 1.25, 1.0)
        paid_up = can_lapse & ~surrender & ~paid_up_flag[idx] & (rng.random(idx.size) < pu_rate * expo)

        dis_rate = (DIS_BASE * np.exp(DIS_AGE * (age - 40))
                    * np.where(sex[idx] == "F", DIS_FEMALE, 1.0)
                    * pd.Series(sector[idx]).map(DIS_SECTOR).to_numpy()
                    * pd.Series(salary[idx]).map(DIS_SALARY).to_numpy())
        at_risk_dis = pre_ret & ~disabled[idx] & ~death & ~surrender & (age >= 25)
        dis = at_risk_dis & (rng.random(idx.size) < 1 - np.exp(-dis_rate * expo))

        # actual exposure: half-year for decrements that exit the book
        exit_ = death | surrender
        expo_out = np.where(exit_, expo * 0.5, expo)
        rows.append(pd.DataFrame({
            "policy_id": pid[idx], "calendar_year": year, "age": age,
            "duration_years": dur, "exposure_years": np.round(expo_out, 4),
            "death": death.astype(int), "disability_incidence": dis.astype(int),
            "surrender": surrender.astype(int), "paid_up": paid_up.astype(int),
            "status_start": status[idx],
        }))

        # disability claims (survival data for recovery modelling)
        for j in np.where(dis)[0]:
            p = idx[j]
            onset_age = age[j]
            start = pd.Timestamp(year=year, month=1, day=1) + pd.Timedelta(days=int(rng.integers(0, 365)))
            # competing risks: recovery (Weibull, slower at older ages) vs death
            rec_scale = 2.2 * np.exp(0.03 * (onset_age - 40)) * (0.85 if sex[p] == "F" else 1.0)
            t_rec = rec_scale * rng.weibull(0.8)
            t_die = rng.exponential(1 / (8 * TRUE_B * np.exp(TRUE_C * onset_age)))
            t = min(t_rec, t_die)
            end = start + pd.Timedelta(days=int(t * 365.25))
            if end > pd.Timestamp(VALUATION_DATE):
                outcome, end_date = "ONGOING", None
                t = (pd.Timestamp(VALUATION_DATE) - start).days / 365.25
            else:
                outcome = "RECOVERED" if t_rec <= t_die else "DIED"
                end_date = end.date().isoformat()
            claim_seq += 1
            claims.append({
                "claim_id": f"C{claim_seq:06d}", "policy_id": pid[p], "start_date": start.date().isoformat(),
                "end_date": end_date, "duration_years": round(max(t, 1 / 365), 4), "outcome": outcome,
                "age_at_onset": int(onset_age), "sex": sex[p], "employer_sector": sector[p],
                "salary_band": salary[p], "monthly_benefit_eur": round(annual_benefit[p] / 12, 0),
            })

        # state transitions
        alive[idx[death]] = False
        alive[idx[surrender]] = False
        status[idx[death]] = "DECEASED"
        status[idx[surrender]] = "SURRENDERED"
        paid_up_flag[idx[paid_up]] = True
        status[idx[paid_up]] = "PAID_UP"
        disabled[idx[dis]] = True
        status[idx[dis]] = "DISABLED"
        in_pay = alive[idx] & ~pre_ret & np.isin(scheme[idx], ["COMPANY_PENSION", "PRIVATE_PENSION", "LIFE_ANNUITY"])
        status[idx[in_pay]] = "IN_PAYMENT"

    policy_years = pd.concat(rows, ignore_index=True)
    status = np.where(entry_year > LAST_YEAR, "ACTIVE", status)

    policies = pd.DataFrame({
        "policy_id": pid, "member_id": [f"M{i:07d}" for i in rng.permutation(n_policies)],
        "birth_date": [f"{y}-{m:02d}-{d:02d}" for y, m, d in zip(birth_year, rng.integers(1, 13, n_policies), rng.integers(1, 29, n_policies))],
        "sex": sex, "scheme": scheme, "product_type": product,
        "entry_date": [f"{y}-{m:02d}-01" for y, m in zip(entry_year, rng.integers(1, 13, n_policies))],
        "status": status, "salary_band": salary, "employer_sector": sector, "region": region,
        "savings_balance_eur": balance, "guaranteed_rate": guaranteed_rate,
        "annual_premium_eur": annual_premium, "annual_benefit_eur": annual_benefit,
        "retirement_age": retirement_age,
    })

    # ---------------- standard table + improvement ----------------
    ages = np.arange(18, 111)
    base = []
    for s, m in (("F", 1.0), ("M", TRUE_MALE)):
        mu = np.minimum(TRUE_B * np.exp(TRUE_C * ages) * m * 1.03, 0.6)   # table is 3% "heavier" than truth
        base.append(pd.DataFrame({"age": ages, "sex": s, "qx": np.round(1 - np.exp(-mu), 7),
                                  "annual_improvement": np.round(np.where(ages < 90, 0.015, 0.008), 4),
                                  "table_name": "STANDARD_2020", "base_year": 2020}))
    base_mortality = pd.concat(base, ignore_index=True)

    # ---------------- economic scenarios (Vasicek short rate + lognormal equity) ----------------
    n_scen, n_years = 1000, 60
    r = np.empty((n_scen, n_years)); r[:, 0] = 0.025
    a, theta, sigma = 0.12, 0.028, 0.009
    eps = rng.standard_normal((n_scen, n_years))
    for t in range(1, n_years):
        r[:, t] = r[:, t - 1] + a * (theta - r[:, t - 1]) + sigma * eps[:, t]
    eq = r + 0.04 + 0.16 * (0.6 * eps + 0.8 * rng.standard_normal((n_scen, n_years)))
    infl = 0.02 + 0.4 * (r - theta) + 0.006 * rng.standard_normal((n_scen, n_years))
    economic_scenarios = pd.DataFrame({
        "scenario_id": np.repeat(np.arange(1, n_scen + 1), n_years),
        "projection_year": np.tile(np.arange(1, n_years + 1), n_scen),
        "short_rate": np.round(r.ravel(), 6), "equity_return": np.round(eq.ravel(), 6),
        "inflation": np.round(infl.ravel(), 6), "esg_version": "ESG_2025Q4",
    })

    # ---------------- the new quarterly extract (2026 Q1-Q3) ----------------
    last = policy_years[policy_years.calendar_year == LAST_YEAR]
    last = last[(last.death == 0) & (last.surrender == 0)].sample(frac=0.6, random_state=7).copy()
    last["calendar_year"] = 2026
    last["age"] += 1
    last["duration_years"] += 1
    last["exposure_years"] = 0.75
    pol = policies.set_index("policy_id").loc[last.policy_id]
    mu = mortality(last.age.to_numpy(), pol.sex.to_numpy(),
                   pd.Series(pol.scheme.to_numpy()).map({s[0]: s[4] for s in SCHEMES}).to_numpy(),
                   duration_band(last.duration_years.to_numpy()), pol.product_type.to_numpy(),
                   pol.salary_band.to_numpy(), 2026) * 1.08   # a slightly heavier year -> A/E moves
    last["death"] = (rng.random(len(last)) < 1 - np.exp(-mu * 0.75)).astype(int)
    last["surrender"] = (rng.random(len(last)) < 0.03).astype(int)
    last["paid_up"] = (rng.random(len(last)) < 0.015).astype(int)
    last["disability_incidence"] = (rng.random(len(last)) < 0.002).astype(int)
    bad = last.sample(37, random_state=11).index
    last.loc[bad[:15], "exposure_years"] = -0.75         # DQ: negative exposure
    last.loc[bad[15:27], "age"] = 141                    # DQ: impossible age
    last.loc[bad[27:], "policy_id"] = None               # DQ: missing key
    extract = last

    return {
        "policies": policies, "policy_years": policy_years, "disability_claims": pd.DataFrame(claims),
        "base_mortality": base_mortality, "economic_scenarios": economic_scenarios,
        "policy_extract_2026_q3": extract,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policies", type=int, default=100_000)
    args = ap.parse_args()
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, df in generate(args.policies, rng).items():
        path = OUT / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"{name:24s} {len(df):>9,} rows  {path.stat().st_size / 1e6:6.1f} MB")


if __name__ == "__main__":
    main()
