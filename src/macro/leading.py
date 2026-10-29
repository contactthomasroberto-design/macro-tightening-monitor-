"""Market-based recession signals, compared out of sample.

Target: y_t = 1 if the NBER dates a recession in any of the 12 months after month t (the target of
the Fed Board's excess-bond-premium model). Candidate signals, each a monthly average:

- `spread`: 10-year minus 3-month Treasury yield (Estrella-Mishkin; the New York Fed's model);
- `ntfs`: near-term forward spread (Engstrom-Sharpe): the forward rate about six quarters ahead
  minus the 3-month bill. The six-quarter forward is not published free; it is approximated by the
  one-year rate one year ahead implied by 1- and 2-year yields, 2·y2 − y1, centred 18 months ahead;
- `ebp`: excess bond premium (Gilchrist-Zakrajšek, Fed Board staff).

Models are probits fixed in advance (research log H17). They are compared by pseudo-out-of-sample
forecasts: at each monthly origin t from 1990, a model is estimated only on months s whose 12-month
outcome window has closed by t (s + 12 ≤ t), then predicts at t. Scores: AUC, Brier, log score, and
the Brier skill score against the expanding unconditional frequency, with moving-block bootstrap
intervals. Two known optimisms remain and are stated on the page: NBER dates are announced months
after the fact, and the EBP history is revised every month (latest vintage used).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MODELS: dict[str, list[str]] = {
    "10Y-3M spread": ["spread"],
    "Near-term forward spread": ["ntfs"],
    "Excess bond premium": ["ebp"],
    "Near-term forward spread + EBP": ["ntfs", "ebp"],
    "10Y-3M spread + EBP": ["spread", "ebp"],
}
HORIZON = 12


def features(dgs10, dgs3mo, dgs2, dgs1, ebp) -> pd.DataFrame:
    """Monthly averages of the three signals (percentage points)."""
    m = lambda s: s.dropna().resample("MS").mean()  # noqa: E731
    out = pd.DataFrame(
        {
            "spread": m(dgs10) - m(dgs3mo),
            "ntfs": (2 * m(dgs2) - m(dgs1)) - m(dgs3mo),
            "ebp": ebp.dropna().resample("MS").last(),
        }
    )
    return out


def target_within(usrec: pd.Series, h: int = HORIZON) -> pd.Series:
    """1 if a recession month falls in t+1..t+h; NaN where that window is not fully observed."""
    r = usrec.dropna().resample("MS").last()
    fwd = pd.concat([r.shift(-k) for k in range(1, h + 1)], axis=1)
    y = (fwd.max(axis=1) > 0).astype(float)
    return y.where(fwd.notna().all(axis=1))


def _probit(y: pd.Series, X: pd.DataFrame, hac: bool = False):
    import statsmodels.api as sm

    kw = {"cov_type": "HAC", "cov_kwds": {"maxlags": HORIZON}} if hac else {}
    return sm.Probit(y, sm.add_constant(X, has_constant="add")).fit(disp=0, **kw)


def _auc(p: np.ndarray, y: np.ndarray) -> float:
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def scores(p: np.ndarray, y: np.ndarray, clim: np.ndarray) -> dict[str, float]:
    eps = 1e-6
    pc = np.clip(p, eps, 1 - eps)
    brier = float(np.mean((p - y) ** 2))
    brier_c = float(np.mean((clim - y) ** 2))
    return {
        "AUC": _auc(p, y),
        "Brier": brier,
        "Brier skill vs base rate": 1 - brier / brier_c if brier_c > 0 else np.nan,
        "log score": float(np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc))),
    }


def block_bootstrap_bss(
    p: np.ndarray, y: np.ndarray, clim: np.ndarray, block: int = 24, reps: int = 500, seed: int = 0
) -> tuple[float, float]:
    """90% interval of the Brier skill score by moving-block bootstrap (blocks of `block` months keep
    the serial dependence that overlapping 12-month targets create)."""
    g = np.random.default_rng(seed)
    n = len(y)
    if n < 2 * block:
        return np.nan, np.nan
    starts = np.arange(n - block + 1)
    out = []
    for _ in range(reps):
        idx = np.concatenate([np.arange(s, s + block) for s in g.choice(starts, int(np.ceil(n / block)))])[:n]
        bc = np.mean((clim[idx] - y[idx]) ** 2)
        if bc > 0:
            out.append(1 - np.mean((p[idx] - y[idx]) ** 2) / bc)
    return float(np.quantile(out, 0.05)), float(np.quantile(out, 0.95))


def pseudo_oos(
    X: pd.DataFrame, y: pd.Series, cols: list[str], start: str = "1990-01-01", min_train: int = 120
) -> pd.DataFrame:
    """Expanding-window forecasts: at origin t, fit on months s with s + HORIZON <= t (outcome known)."""
    df = pd.concat([X[cols], y.rename("y")], axis=1)
    rows = []
    for t in df.loc[start:].index:
        if df.loc[t, cols].isna().any():
            continue
        cutoff = t - pd.DateOffset(months=HORIZON)
        train = df.loc[:cutoff].dropna()
        if len(train) < min_train or train["y"].sum() < 2 or train["y"].sum() == len(train):
            continue
        try:
            fit = _probit(train["y"], train[cols])
        except Exception:
            continue
        x_t = pd.DataFrame([df.loc[t, cols].to_numpy()], columns=cols)
        p = float(fit.predict(np.column_stack([np.ones(1), x_t.to_numpy()]))[0])
        rows.append({"date": t, "p": p, "base rate": float(train["y"].mean()), "y": df.loc[t, "y"]})
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame(columns=["p", "base rate", "y"])


def suite(X: pd.DataFrame, y: pd.Series, start: str = "1990-01-01") -> dict:
    """Every model: full-sample fit (coefficients with HAC errors, current probability) and
    pseudo-out-of-sample scores. Returns {'table', 'oos', 'current', 'fits'}."""
    table, oos, current, fits = [], {}, {}, {}
    for name, cols in MODELS.items():
        d = pd.concat([X[cols], y.rename("y")], axis=1).dropna()
        if len(d) < 120 or d["y"].sum() < 2:
            continue
        fit = _probit(d["y"], d[cols], hac=True)
        fits[name] = fit
        last = X[cols].dropna()
        p_now = float(fit.predict(np.column_stack([np.ones(1), last.iloc[[-1]].to_numpy()]))[0])
        current[name] = (p_now, last.index[-1])
        o = pseudo_oos(X, y, cols, start)
        o = o.dropna(subset=["y"])
        oos[name] = o
        sc = scores(o["p"].to_numpy(), o["y"].to_numpy(), o["base rate"].to_numpy()) if len(o) else {}
        lo, hi = (
            block_bootstrap_bss(o["p"].to_numpy(), o["y"].to_numpy(), o["base rate"].to_numpy())
            if len(o)
            else (np.nan, np.nan)
        )
        coefs = "; ".join(f"{c} {fit.params[c]:+.2f} (t {fit.tvalues[c]:+.1f})" for c in cols)
        table.append(
            {
                "model": name,
                "probability now": p_now,
                "data month": last.index[-1],
                "coefficients (HAC t)": coefs,
                "months": int(fit.nobs),
                "pseudo R²": float(fit.prsquared),
                **sc,
                "BSS 90% low": lo,
                "BSS 90% high": hi,
                "OOS months": len(o),
                "OOS from": o.index[0].date() if len(o) else None,
            }
        )
    tab = pd.DataFrame(table).set_index("model") if table else pd.DataFrame()
    return {"table": tab, "oos": oos, "current": current, "fits": fits}
