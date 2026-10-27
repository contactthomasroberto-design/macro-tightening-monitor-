"""Recession risk (BRIEF §5.5): 12-month-ahead probit on the term spread (Estrella-Mishkin),
extended with credit spread, 6-month change in unemployment and NFCI; L2-regularised logit as a
robustness check; Sahm-rule indicator; expanding-window evaluation (ROC AUC, Brier, calibration);
block-bootstrap band on the current probability. The number of recession episodes is always shown.

    P(REC_{t+12} = 1 | x_t) = Phi(a + b' x_t)
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from macro.utils import Result, block_bootstrap_indices, rng

SPECS = {
    "Probit: term spread": ["spread_3m10y"],
    "Probit: extended": ["spread_3m10y", "credit_spread", "d6_unemp", "nfci"],
}
HORIZON = 12


def episodes(rec: pd.Series) -> int:
    r = rec.fillna(0).astype(int)
    return int(((r == 1) & (r.shift(1, fill_value=0) == 0)).sum())


def target(rec: pd.Series, h: int = HORIZON) -> pd.Series:
    """y_t = REC_{t+h} (recession indicator h months ahead)."""
    return rec.shift(-h)


def sahm(unemp: pd.Series) -> pd.DataFrame:
    """Sahm rule: 3-month average unemployment minus its minimum over the previous 12 months;
    triggered at >= 0.50 pp."""
    u3 = unemp.rolling(3).mean()
    val = u3 - u3.shift(1).rolling(12).min()
    return pd.DataFrame({"sahm": val, "triggered": val >= 0.5})


def _probit(y: np.ndarray, X: np.ndarray):
    import statsmodels.api as sm

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sm.Probit(y, sm.add_constant(X, has_constant="add")).fit(disp=False, maxiter=200)


def _logit_l2(y: np.ndarray, X: np.ndarray):
    from sklearn.linear_model import LogisticRegressionCV
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = make_pipeline(
            StandardScaler(),
            LogisticRegressionCV(Cs=10, cv=TimeSeriesSplit(5), scoring="neg_brier_score", max_iter=2000),
        )
        return m.fit(X, y)


def _predict(model, X: np.ndarray) -> np.ndarray:
    import statsmodels.api as sm

    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    return model.predict(sm.add_constant(X, has_constant="add"))


def fit_all(df: pd.DataFrame) -> dict:
    """Full-sample fits. df columns: y (target), and regressors."""
    out = {}
    for name, cols in SPECS.items():
        d = df[["y", *cols]].dropna()
        out[name] = {
            "model": _probit(d["y"].to_numpy(), d[cols].to_numpy()),
            "cols": cols,
            "n": len(d),
            "start": d.index[0],
            "end": d.index[-1],
        }
    cols = SPECS["Probit: extended"]
    d = df[["y", *cols]].dropna()
    out["Logit L2: extended"] = {
        "model": _logit_l2(d["y"].to_numpy().astype(int), d[cols].to_numpy()),
        "cols": cols,
        "n": len(d),
        "start": d.index[0],
        "end": d.index[-1],
    }
    return out


def roc_auc(y: np.ndarray, p: np.ndarray) -> float:
    """AUC = P(p_recession > p_expansion) (Mann-Whitney form, ties count 1/2)."""
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    gt = (pos[:, None] > neg[None, :]).mean()
    eq = (pos[:, None] == neg[None, :]).mean()
    return float(gt + 0.5 * eq)


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 5) -> pd.DataFrame:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    b = np.digitize(p, edges[1:-1])
    rows = [
        {
            "bin": k,
            "mean predicted": float(p[b == k].mean()),
            "observed frequency": float(y[b == k].mean()),
            "n": int((b == k).sum()),
        }
        for k in range(bins)
        if (b == k).any()
    ]
    return pd.DataFrame(rows)


def expanding_oos(
    df: pd.DataFrame, start: str = "1998-01-01", h: int = HORIZON, step: int = 3, step_logit: int = 12
) -> pd.DataFrame:
    """Expanding-window out-of-sample probabilities: at origin t, fit on pairs (x_s, y_s) with
    s + h <= t (outcome known), predict y_t. Probits refit every `step` months, the cross-validated
    logit every `step_logit` months."""
    rows = []
    models = {}
    origins = df.loc[start:].index
    for k, t in enumerate(origins):
        known = df.loc[: t - pd.DateOffset(months=h)]
        if k % step == 0:
            for name, cols in SPECS.items():
                d = known[["y", *cols]].dropna()
                if d["y"].sum() >= 2 and len(d) > 60:
                    models[name] = (_probit(d["y"].to_numpy(), d[cols].to_numpy()), cols)
        if k % step_logit == 0:
            cols = SPECS["Probit: extended"]
            d = known[["y", *cols]].dropna()
            if d["y"].sum() >= 2 and len(d) > 60:
                models["Logit L2: extended"] = (
                    _logit_l2(d["y"].to_numpy().astype(int), d[cols].to_numpy()),
                    cols,
                )
        row = {"origin": t, "y": df.loc[t, "y"]}
        for name, (m, cols) in models.items():
            x = df.loc[[t], cols].to_numpy()
            row[name] = float(_predict(m, x)[0]) if not np.isnan(x).any() else np.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("origin")


def oos_scores(oos: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name in [c for c in oos.columns if c != "y"]:
        d = oos[["y", name]].dropna()
        y, p = d["y"].to_numpy(), d[name].to_numpy()
        rows.append(
            {
                "model": name,
                "n": len(d),
                "recession months": int(y.sum()),
                "AUC": roc_auc(y, p),
                "Brier": brier(y, p),
                "Brier (climatology)": brier(y, np.full(len(y), y.mean())),
            }
        )
    return pd.DataFrame(rows).set_index("model")


def current_probability(
    df: pd.DataFrame, cols: list[str], n_boot: int = 300, block: int = 12, seed: int | None = None
) -> dict:
    """Probit probability at the latest x with a moving-block bootstrap band (refit on resampled pairs)."""
    d = df[["y", *cols]].dropna()
    x_now = df[cols].dropna().iloc[[-1]].to_numpy()
    m = _probit(d["y"].to_numpy(), d[cols].to_numpy())
    p = float(_predict(m, x_now)[0])
    idx = block_bootstrap_indices(len(d), block, n_boot, rng(seed))
    Y, X = d["y"].to_numpy(), d[cols].to_numpy()
    draws = []
    for i in idx:
        if Y[i].sum() < 2:
            continue
        try:
            draws.append(float(_predict(_probit(Y[i], X[i]), x_now)[0]))
        except (np.linalg.LinAlgError, ValueError):
            continue
    draws = np.array(draws)
    return {
        "p": p,
        "lo": float(np.quantile(draws, 0.05)),
        "hi": float(np.quantile(draws, 0.95)),
        "n_boot": len(draws),
        "date": df[cols].dropna().index[-1],
    }


def recession_model(df: pd.DataFrame, rec: pd.Series, start_oos: str = "1998-01-01") -> Result:
    full = fit_all(df)
    oos = expanding_oos(df, start=start_oos)
    sc = oos_scores(oos)
    cur = {name: current_probability(df, cols) for name, cols in SPECS.items()}
    lx = df[SPECS["Probit: extended"]].dropna().iloc[[-1]].to_numpy()
    cur["Logit L2: extended"] = {
        "p": float(_predict(full["Logit L2: extended"]["model"], lx)[0]),
        "lo": np.nan,
        "hi": np.nan,
    }
    head = cur["Probit: extended"]
    coefs = {
        name: pd.Series(f["model"].params, index=["const", *f["cols"]])
        for name, f in full.items()
        if "Probit" in name
    }
    return Result(
        "recession_prob_12m",
        head["p"],
        lower=head["lo"],
        upper=head["hi"],
        band_level=0.90,
        n_obs=full["Probit: extended"]["n"],
        n_specs_tried=3,
        extra={
            "current": cur,
            "oos": oos,
            "scores": sc,
            "coefficients": coefs,
            "episodes": episodes(rec),
            "oos_start": start_oos,
            "calibration": {
                n: calibration(oos[["y", n]].dropna()["y"].to_numpy(), oos[["y", n]].dropna()[n].to_numpy())
                for n in oos.columns
                if n != "y" and oos[n].notna().sum() > 30
            },
        },
        notes=[
            "12-month-ahead recession probability; NBER dates are known with a lag, so the most recent months of the "
            "target are provisional. Few recession episodes: estimates are imprecise."
        ],
    )
