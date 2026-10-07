"""Nested stochastic valuation kernel.

Outer loop: real-world economic scenarios (short-rate paths from the ESG) x a
longevity-trend shock.  For each outer scenario:
  * the BEL is re-discounted on that scenario's rate path, with mortality scaled by
    the scenario's longevity factor (interpolated on a pre-computed grid), and
  * an INNER risk-neutral Monte Carlo values the interest-rate guarantee on
    average-rate (with-profits) savings: E[ max(0, B(1+g)^T - B*prod(1+R_t)) ].

Each outer scenario is independent -> the work fans out over Spark tasks (data
parallel over scenario chunks) or Ray tasks (logic parallel), or vectorises on a GPU
(the same array code in PyTorch/JAX).  The NumPy kernel below is the reference.
"""
from __future__ import annotations

import time

import numpy as np

LONGEVITY_GRID = np.round(np.linspace(0.70, 1.30, 13), 3)


def guarantee_cost(r0: float, buckets: np.ndarray, n_inner: int, horizon: int,
                   vol: float, seed: int, backend: str = "numpy") -> float:
    """Inner risk-neutral MC. buckets: [k x 2] = (balance_eur, guaranteed_rate)."""
    if backend == "numba":
        try:
            return float(_guarantee_cost_numba(r0, buckets, n_inner, horizon, vol, seed))
        except Exception:
            backend = "numpy"
    if backend == "torch":
        try:
            return _guarantee_cost_torch(r0, buckets, n_inner, horizon, vol, seed)
        except Exception:
            backend = "numpy"
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_inner, horizon))
    log_growth = ((r0 - 0.5 * vol ** 2) + vol * z).sum(axis=1)       # [n_inner]
    fund = np.exp(log_growth)[:, None]                                 # per EUR invested
    g = buckets[:, 1][None, :]
    shortfall = np.maximum(0.0, (1 + g) ** horizon - fund)             # [n_inner x k]
    return float((shortfall.mean(axis=0) * buckets[:, 0]).sum() * np.exp(-r0 * horizon))


def _guarantee_cost_torch(r0, buckets, n_inner, horizon, vol, seed):  # GPU path when CUDA exists
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    g = torch.Generator(device=dev).manual_seed(seed)
    z = torch.randn((n_inner, horizon), generator=g, device=dev, dtype=torch.float64)
    fund = torch.exp(((r0 - 0.5 * vol ** 2) + vol * z).sum(1))[:, None]
    b = torch.as_tensor(buckets, device=dev, dtype=torch.float64)
    short = torch.clamp((1 + b[:, 1])[None, :] ** horizon - fund, min=0.0)
    return float((short.mean(0) * b[:, 0]).sum().cpu()) * float(np.exp(-r0 * horizon))


try:
    from numba import njit

    @njit(cache=False, fastmath=True)
    def _guarantee_cost_numba(r0, buckets, n_inner, horizon, vol, seed):
        np.random.seed(seed)
        k = buckets.shape[0]
        acc = np.zeros(k)
        drift = r0 - 0.5 * vol * vol
        for i in range(n_inner):
            lg = 0.0
            for t in range(horizon):
                lg += drift + vol * np.random.standard_normal()
            f = np.exp(lg)
            for j in range(k):
                s = (1 + buckets[j, 1]) ** horizon - f
                if s > 0:
                    acc[j] += s
        tot = 0.0
        for j in range(k):
            tot += acc[j] / n_inner * buckets[j, 0]
        return tot * np.exp(-r0 * horizon)
except Exception:  # numba not installed -> numpy fallback
    def _guarantee_cost_numba(*a, **k):  # type: ignore
        raise RuntimeError("numba unavailable")


def value_outer_scenarios(scen_rates: np.ndarray, scen_ids: np.ndarray, longevity: np.ndarray,
                          cf_grid: np.ndarray, buckets: np.ndarray, n_inner: int,
                          horizon_guarantee: int = 10, vol: float = 0.12,
                          backend: str = "numpy") -> list[dict]:
    """scen_rates [s x T] short rates; cf_grid [len(LONGEVITY_GRID) x T] portfolio net
    cash flows at each longevity multiplier."""
    out = []
    T = cf_grid.shape[1]
    for i, sid in enumerate(scen_ids):
        t0 = time.perf_counter()
        r = scen_rates[i, :T]
        if len(r) < T:
            r = np.concatenate([r, np.full(T - len(r), r[-1])])
        df = np.cumprod(1 / (1 + r))
        cf = np.array([np.interp(longevity[i], LONGEVITY_GRID, cf_grid[:, t]) for t in range(T)])
        bel = float((cf * df).sum())
        tvog = guarantee_cost(float(r[0]), buckets, n_inner, horizon_guarantee, vol,
                              seed=int(sid) * 7919, backend=backend)
        out.append({"scenario_id": int(sid), "longevity_factor": float(longevity[i]),
                    "r0": float(r[0]), "bel_eur": bel, "tvog_eur": tvog,
                    "total_liability_eur": bel + tvog,
                    "calc_ms": (time.perf_counter() - t0) * 1000})
    return out
