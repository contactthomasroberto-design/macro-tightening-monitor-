"""Financial conditions: "how much tightening is left" (BRIEF §5.3).

FCI-lite (this project's research series, NOT the Fed Board's FCI-G):

    impulse_t = sum_k beta_k * D x_{k,t}       FCI_t = - impulse_t   (positive = headwind)

where D x_k is the change in variable k over the lookback window (4 quarters, or 12 quarters for
the 3-year lookback) and beta_k is the estimated effect of that change on real GDP growth over the
next 4 quarters, from

    g_{t,t+4} = c + sum_k beta_k D x_{k,t} + phi g_{t-4,t} + e_t

estimated by ridge regression on standardised changes (the four interest-rate variables are highly
collinear; shrinkage stabilises them), with a moving-block bootstrap for uncertainty. The Fed
Board's FCI-G instead takes the weights from the FRB/US structural model and sums 3-month changes
with model lags; we cannot reproduce FRB/US, so the weights here are statistical (stated on the page).

Gap to neutral (practitioner approach): the FCI level that would close the output gap y_t over H
quarters is FCI* = y_t * 4 / H (pp of growth per year). Gap = FCI* - FCI_t; positive = more
tightening needed. Equivalences translate the gap into the change in one variable that alone would
deliver it: D x_k = -gap / beta_k. These are sensitivities, not forecasts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from macro.utils import Result, block_bootstrap_indices, rng

VARIABLES = {
    "policy_rate": ("Policy rate", "pp", "level"),
    "y10": ("10Y Treasury yield", "pp", "level"),
    "mortgage": ("30Y mortgage rate", "pp", "level"),
    "baa": ("Corporate Baa yield", "pp", "level"),
    "equity": ("Equity prices (S&P 500)", "%", "log"),
    "house": ("House prices", "%", "log"),
    "dollar": ("Broad dollar", "%", "log"),
}


def changes(levels_q: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """D x over `lookback` quarters: pp for rates, 100*log change (%) for prices."""
    out = {}
    for k, (_, _, kind) in VARIABLES.items():
        if k not in levels_q:
            continue
        x = levels_q[k]
        out[k] = (100 * (np.log(x) - np.log(x.shift(lookback)))) if kind == "log" else (x - x.shift(lookback))
    return pd.DataFrame(out)


def _ridge_fit(
    X: np.ndarray, y: np.ndarray, alpha: float
) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    """Ridge on standardised X: returns (beta in original units, intercept, mean, sd)."""
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    yc = y - y.mean()
    b = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ yc)
    beta = b / sd
    c = y.mean() - mu @ beta
    return beta, c, mu, sd


def _cv_alpha(
    X: np.ndarray, y: np.ndarray, grid=(0.1, 1, 3, 10, 30, 100, 300, 1000), folds: int = 5
) -> float:
    """Expanding-window (time-series) cross-validation of the ridge penalty."""
    n = len(y)
    edges = np.linspace(n * 0.5, n, folds + 1).astype(int)
    best = None
    for a in grid:
        err = []
        for f in range(folds):
            tr, te = slice(0, edges[f]), slice(edges[f], edges[f + 1])
            if edges[f + 1] - edges[f] < 2:
                continue
            beta, c, *_ = _ridge_fit(X[tr], y[tr], a)
            err.append(np.mean((y[te] - c - X[te] @ beta) ** 2))
        m = float(np.mean(err)) if err else np.inf
        if best is None or m < best[0]:
            best = (m, a)
    return best[1]


def fci_lite(
    levels_q: pd.DataFrame,
    gdp_q: pd.Series,
    lookback: int = 4,
    horizon: int = 4,
    n_boot: int = 500,
    block: int = 8,
    seed: int | None = None,
) -> Result:
    """Estimate growth sensitivities and build the FCI-lite with a variable decomposition."""
    dx = changes(levels_q, lookback)
    lg = 100 * np.log(gdp_q)
    fwd = (lg.shift(-horizon) - lg).rename("g_fwd")
    past = (lg - lg.shift(4)).rename("g_past")
    cols = list(dx.columns)
    df = pd.concat([fwd, dx, past], axis=1).dropna()
    X = df[cols + ["g_past"]].to_numpy()
    y = df["g_fwd"].to_numpy()
    alpha = _cv_alpha(X, y)
    beta, c, *_ = _ridge_fit(X, y, alpha)
    b = pd.Series(beta[: len(cols)], index=cols)
    # block bootstrap of the (y, X) pairs
    idx = block_bootstrap_indices(len(y), block, n_boot, rng(seed))
    draws = np.array([_ridge_fit(X[i], y[i], alpha)[0][: len(cols)] for i in idx])
    bt = pd.DataFrame(draws, columns=cols)
    table = pd.DataFrame(
        {
            "beta": b,
            "lower": bt.quantile(0.05),
            "upper": bt.quantile(0.95),
            "label": [VARIABLES[k][0] for k in cols],
            "unit": [VARIABLES[k][1] for k in cols],
        }
    )
    full_dx = dx.dropna()
    contrib = -(full_dx * b)  # positive = headwind
    fci = contrib.sum(axis=1)
    fci_draws = -(full_dx.iloc[[-1]].to_numpy() @ draws.T).ravel()
    lo, hi = np.quantile(fci_draws, [0.05, 0.95])
    return Result(
        f"fci_lite_{lookback // 4}y",
        fci,
        lower=float(lo),
        upper=float(hi),
        band_level=0.90,
        n_obs=len(y),
        n_specs_tried=2,
        extra={
            "betas": table,
            "beta_draws": bt,
            "contributions": contrib,
            "alpha": alpha,
            "lookback": lookback,
            "horizon": horizon,
            "fci_draws": fci_draws,
            "sample": (df.index[0], df.index[-1]),
        },
        notes=[
            f"FCI-lite ({lookback // 4}-year lookback): statistical growth sensitivities (ridge, penalty {alpha} by "
            "time-series CV), not the Fed Board's FRB/US weights. Research series, may be revised, not an official statistic."
        ],
    )


def gap_to_neutral(fci_now: float, output_gap: float, horizon_q: int = 8) -> dict:
    """FCI* = y * 4/H (pp of growth per year needed to close the gap in H quarters); gap = FCI* - FCI."""
    target = output_gap * 4.0 / horizon_q
    return {
        "fci_now": fci_now,
        "fci_target": target,
        "gap": target - fci_now,
        "output_gap": output_gap,
        "horizon_q": horizon_q,
    }


def equivalences(
    gap: float,
    beta_draws: pd.DataFrame,
    extra_uncertainty: float = 0.0,
    keys=("y10", "equity", "dollar", "baa"),
) -> pd.DataFrame:
    """Change in a single variable that would add `gap` pp of headwind on its own:
    D x_k = -gap / beta_k, distribution over bootstrap draws of beta_k (draws whose sign differs from
    the point estimate are dropped and counted). `extra_uncertainty` widens the band by +/- that
    relative amount (judgemental multiplier uncertainty from assumptions.yaml)."""
    rows = []
    for k in keys:
        if k not in beta_draws:
            continue
        d = beta_draws[k].to_numpy()
        sign = np.sign(np.median(d))
        ok = d[np.sign(d) == sign]
        eq = -gap / ok
        med = float(np.median(eq))
        lo, hi = np.quantile(eq, [0.16, 0.84])
        lo, hi = (
            min(lo, med * (1 - extra_uncertainty), med * (1 + extra_uncertainty)),
            max(hi, med * (1 - extra_uncertainty), med * (1 + extra_uncertainty)),
        )
        unit = VARIABLES[k][1]
        rows.append(
            {
                "variable": VARIABLES[k][0],
                "key": k,
                "central": med * (100 if unit == "pp" else 1),
                "low (16%)": lo * (100 if unit == "pp" else 1),
                "high (84%)": hi * (100 if unit == "pp" else 1),
                "unit": "bp" if unit == "pp" else "%",
                "sign_unstable_share": float(1 - len(ok) / len(d)),
                "reliable": bool(len(ok) / len(d) >= 0.9),
            }
        )
    tab = pd.DataFrame(rows).set_index("variable")
    rel = tab[tab["reliable"]] if not tab.empty else tab
    if len(rel) >= 2:
        # combination: each reliable variable delivers an equal share of the gap
        comb = rel[["central", "low (16%)", "high (84%)"]] / len(rel)
        tab.attrs["combination"] = comb
    return tab


def project_fci(
    levels_q: pd.DataFrame,
    betas: pd.Series,
    paths: dict[str, pd.Series],
    lookback: int = 4,
    quarters: int = 8,
) -> pd.Series:
    """FCI path when some variables follow given quarterly paths (others held at their last level).
    `paths` maps variable key -> Series of future levels indexed by future quarters."""
    last = levels_q.dropna().index[-1]
    fut_idx = pd.date_range(last + pd.offsets.QuarterBegin(1), periods=quarters, freq="QS")
    ext = pd.concat([levels_q.loc[:last], pd.DataFrame(index=fut_idx)]).ffill()
    for k, p in paths.items():
        ext.loc[p.index.intersection(fut_idx), k] = p.reindex(fut_idx).dropna()
    dx = changes(ext, lookback)
    return -(dx[betas.index] * betas).sum(axis=1).loc[last:]


def statistical_fci(panel: pd.DataFrame) -> pd.Series:
    """First principal component of standardised indicators (credit spread, VIX, curve slope,
    dollar, equity drawdown) — a statistical index in the spirit of NFCI-type measures. Sign: positive
    = tighter (positive loading on the credit spread)."""
    df = panel.dropna()
    z = (df - df.mean()) / df.std()
    u, s, vt = np.linalg.svd(z.to_numpy(), full_matrices=False)
    f = pd.Series(u[:, 0] * s[0], index=df.index)
    load = pd.Series(vt[0], index=df.columns)
    if "credit_spread" in load and load["credit_spread"] < 0:
        f = -f
    return f / f.std()


def index_comparison(indices: dict[str, pd.Series]) -> pd.DataFrame:
    """Latest reading, its percentile in own history and the implied verdict for each index."""
    rows = []
    for name, s in indices.items():
        s = s.dropna()
        if s.empty:
            continue
        last = float(s.iloc[-1])
        pct = float((s < last).mean() * 100)
        rows.append(
            {
                "index": name,
                "latest": last,
                "as_of": s.index[-1].strftime("%Y-%m"),
                "percentile": pct,
                "verdict": "tighter than usual"
                if pct > 60
                else "looser than usual"
                if pct < 40
                else "near median",
            }
        )
    return pd.DataFrame(rows).set_index("index")
