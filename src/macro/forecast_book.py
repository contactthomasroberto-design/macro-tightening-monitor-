"""Scored directional forecasts: a measurable record of what the signals say.

For eight market variables, the probability that the variable is higher in 13 weeks than today,
from a logistic regression on three standard signals fixed in advance (research log H22):

- momentum: the 26-week change, divided by the standard deviation of 26-week changes over the
  previous three years (Moskowitz, Ooi and Pedersen 2012);
- value: the distance of today's level (log level for prices) from its 5-year mean, in 5-year
  standard deviations (Asness, Moskowitz and Pedersen 2013, "Value and Momentum Everywhere");
- carry: a free proxy of what holding the position earns, standardised over five years
  (Koijen, Moskowitz, Pedersen and Vrugt 2018, "Carry"). Fixed mapping in `CARRY`; Brent has none
  (no free futures curve).

Estimation is pseudo out of sample: at each weekly origin t from 2005, the model is fitted only on
origins whose 13-week outcome is known by t. Scores: Brier skill against the expanding base rate,
with a moving-block bootstrap interval, AUC and a reliability table. These are forecasts of
direction with their probability, recorded and scored; they are not recommendations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from macro.markets import business_daily, change

H = 13
VARIABLES = {
    # id: (label, kind)
    "DGS2": ("US 2Y yield", "yield"),
    "DGS10": ("US 10Y yield", "yield"),
    "T10Y2Y": ("US 2s10s slope", "spread"),
    "EURUSD": ("EUR/USD", "price"),
    "USDJPY": ("USD/JPY", "price"),
    "SPX": ("S&P 500", "price"),
    "BAA10Y": ("Baa-Treasury spread", "spread"),
    "BRENT_FUT": ("Brent", "price"),
}
# carry proxy: (a, b) → a − b, in percentage points; None: no free carry measure
CARRY = {
    "DGS2": ("DGS2", "DGS3MO"),  # roll-down of the 2-year over cash
    "DGS10": ("DGS10", "DGS2"),  # term spread
    "T10Y2Y": ("DGS2", "DFF"),  # front end pricing hikes or cuts
    "EURUSD": ("EA_YC_2Y", "DGS2"),  # rate differential
    "USDJPY": ("DGS2", "JP_2Y"),
    "SPX": ("DGS10", "DGS3MO"),  # macro carry: term spread (no free dividend yield)
    "BAA10Y": ("BAA10Y", None),  # the spread is the carry
    "BRENT_FUT": None,
}


def weekly(s: pd.Series) -> pd.Series:
    return business_daily(s).resample("W-FRI").last()


def signals(level: pd.Series, kind: str, carry: pd.Series | None) -> pd.DataFrame:
    """Weekly signal panel (z-scores) for one variable."""
    x = np.log(level) if kind == "price" else level
    mom = change(level, kind, 26)
    mom_z = mom / mom.rolling(156, min_periods=104).std()
    val_z = (x - x.rolling(260, min_periods=156).mean()) / x.rolling(260, min_periods=156).std()
    out = {"momentum": mom_z, "value": val_z}
    if carry is not None:
        c = carry.reindex(level.index).ffill()
        out["carry"] = (c - c.rolling(260, min_periods=156).mean()) / c.rolling(260, min_periods=156).std()
    return pd.DataFrame(out)


def target_up(level: pd.Series, h: int = H) -> pd.Series:
    """1 if the level is higher h weeks later, NaN where not yet known."""
    fwd = level.shift(-h)
    return (fwd > level).astype(float).where(fwd.notna())


def _logit_fit(X: np.ndarray, y: np.ndarray, ridge: float = 1e-3, iters: int = 25) -> np.ndarray:
    """Logistic regression by Newton steps with a tiny ridge (stable when classes nearly separate)."""
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(X @ b)))
        w = p * (1 - p)
        g = X.T @ (y - p) - ridge * b
        Hm = (X * w[:, None]).T @ X + ridge * np.eye(X.shape[1])
        step = np.linalg.solve(Hm, g)
        b += step
        if np.abs(step).max() < 1e-8:
            break
    return b


def pseudo_oos(
    sig: pd.DataFrame, y: pd.Series, start: str = "2005-01-01", min_train: int = 260
) -> pd.DataFrame:
    df = pd.concat([sig, y.rename("y")], axis=1)
    cols = list(sig.columns)
    rows = []
    for i, t in enumerate(df.index):
        if t < pd.Timestamp(start) or df.loc[t, cols].isna().any():
            continue
        train = df.iloc[: max(0, i - H + 1)].dropna()  # outcomes known at t: origins s with s + H <= t
        if len(train) < min_train or train["y"].nunique() < 2:
            continue
        X = np.column_stack([np.ones(len(train)), train[cols].to_numpy()])
        b = _logit_fit(X, train["y"].to_numpy())
        x_t = np.r_[1.0, df.loc[t, cols].to_numpy(dtype=float)]
        rows.append(
            {
                "date": t,
                "p": float(1 / (1 + np.exp(-x_t @ b))),
                "base rate": float(train["y"].mean()),
                "y": df.loc[t, "y"],
            }
        )
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame(columns=["p", "base rate", "y"])


def current_probability(sig: pd.DataFrame, y: pd.Series) -> tuple[float, dict]:
    """Probability today, from a fit on every origin with a known outcome; also the coefficients."""
    df = pd.concat([sig, y.rename("y")], axis=1)
    train = df.dropna()
    cols = list(sig.columns)
    X = np.column_stack([np.ones(len(train)), train[cols].to_numpy()])
    b = _logit_fit(X, train["y"].to_numpy())
    last = sig.dropna().iloc[-1]
    p = float(1 / (1 + np.exp(-(np.r_[1.0, last.to_numpy(dtype=float)] @ b))))
    return p, {
        "coef": dict(zip(["const", *cols], np.round(b, 3), strict=True)),
        "signals": last.round(2).to_dict(),
        "date": sig.dropna().index[-1],
    }


def reliability(oos: pd.DataFrame, bins=(0, 0.35, 0.45, 0.55, 0.65, 1.0)) -> pd.DataFrame:
    """Forecast probability bins against the observed frequency of a rise."""
    o = oos.dropna(subset=["y"])
    cut = pd.cut(o["p"], bins, include_lowest=True)
    return o.groupby(cut, observed=True).agg(
        forecasts=("p", "size"), mean_forecast=("p", "mean"), observed=("y", "mean")
    )


def book(
    levels: dict[str, pd.Series], carries: dict[str, pd.Series | None], start: str = "2005-01-01"
) -> dict:
    """Pseudo-OOS scores and today's probabilities for every variable available."""
    from macro.leading import block_bootstrap_bss, scores

    table, oos_all, rel = [], {}, {}
    for vid, (label, kind) in VARIABLES.items():
        if vid not in levels:
            continue
        lv = weekly(levels[vid]).dropna()
        sig = signals(lv, kind, carries.get(vid)).dropna(how="all")
        sig = sig.dropna(axis=1, how="all")
        y = target_up(lv)
        o = pseudo_oos(sig, y, start).dropna(subset=["y"])
        if o.empty:
            continue
        oos_all[label] = o
        rel[label] = reliability(o)
        sc = scores(o["p"].to_numpy(), o["y"].to_numpy(), o["base rate"].to_numpy())
        lo, hi = block_bootstrap_bss(
            o["p"].to_numpy(), o["y"].to_numpy(), o["base rate"].to_numpy(), block=26
        )
        p_now, info = current_probability(sig, y)
        table.append(
            {
                "variable": label,
                "id": vid,
                "P(higher in 13 weeks)": p_now,
                "signals today": info["signals"],
                "coefficients": info["coef"],
                "AUC": sc["AUC"],
                "Brier skill vs base rate": sc["Brier skill vs base rate"],
                "BSS 90% low": lo,
                "BSS 90% high": hi,
                "hit rate": float(((o["p"] > 0.5) == (o["y"] == 1)).mean()),
                "weeks": len(o),
                "from": o.index[0].date(),
                "as of": info["date"],
            }
        )
    return {
        "table": pd.DataFrame(table).set_index("variable") if table else pd.DataFrame(),
        "oos": oos_all,
        "reliability": rel,
    }


# ------------------------------------------------------------------ live archive (scored at maturity)
ARCHIVE_COLUMNS = ["week", "id", "variable", "p_up", "level", "horizon_end"]


def archive_rows(tab: pd.DataFrame, levels: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for label, r in tab.iterrows():
        lv = weekly(levels[r["id"]]).dropna()
        wk = lv.index[-1]
        rows.append(
            {
                "week": wk.date(),
                "id": r["id"],
                "variable": label,
                "p_up": round(r["P(higher in 13 weeks)"], 4),
                "level": float(lv.iloc[-1]),
                "horizon_end": (wk + pd.Timedelta(weeks=H)).date(),
            }
        )
    return pd.DataFrame(rows, columns=ARCHIVE_COLUMNS)


def append_archive(path, new: pd.DataFrame) -> int:
    """Append this week's forecasts once (key: week, id). Returns rows written."""
    from pathlib import Path

    path = Path(path)
    old = pd.read_csv(path, dtype={"week": str}) if path.exists() else pd.DataFrame(columns=ARCHIVE_COLUMNS)
    keys = set(zip(old["week"].astype(str), old["id"], strict=True))
    add = new[[(str(w), i) not in keys for w, i in zip(new["week"], new["id"], strict=True)]]
    if add.empty:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    add.to_csv(path, mode="a", header=not path.exists() or path.stat().st_size == 0, index=False)
    return len(add)


def score_archive(archive: pd.DataFrame, levels: dict[str, pd.Series]) -> pd.DataFrame:
    """Matured live forecasts: outcome, Brier score, and whether the direction was right."""
    rows = []
    for _, r in archive.iterrows():
        if r["id"] not in levels:
            continue
        lv = weekly(levels[r["id"]]).dropna()
        end = pd.Timestamp(r["horizon_end"])
        if lv.index[-1] < end:
            continue
        out = float(lv.loc[:end].iloc[-1] > r["level"])
        rows.append(
            {
                **r.to_dict(),
                "outcome up": out,
                "brier": (r["p_up"] - out) ** 2,
                "right side": (r["p_up"] > 0.5) == (out == 1),
            }
        )
    return pd.DataFrame(rows)
