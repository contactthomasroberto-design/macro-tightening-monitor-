"""Cross-asset stress testing: conditional scenarios, historical episodes and market factors.

1. Conditional scenarios. Weekly changes x (quoting units: bp, log %, vol points) are treated as
   multivariate normal with zero mean. Given shocks s on some assets over h weeks, the other assets
   move on average by E[x | s] = Σ_xs Σ_ss⁻¹ s, with covariance Σ_xx − Σ_xs Σ_ss⁻¹ Σ_sx (all scaled
   by h: weekly changes treated as independent). The covariance comes from a chosen window: the last
   two years, everything since 2000, or only the weeks when US core inflation was above 3%.
   `coverage_backtest` checks the calibration out of sample (research log H18).
2. Historical episodes: the same universe's moves over dated stress episodes, and how similar the
   current 13-week move is to each (correlation of moves scaled by each asset's typical move).
3. Factors: principal components of standardised weekly changes, with a stability check between the
   two halves of the window (H19).

Pure functions; the bundle is `pipeline.stress_bundle`.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from macro.markets import UNITS, business_daily, change

EPISODES = [
    ("1994 bond rout", "1994-02-03", "1994-11-07", "Fed hikes earlier and faster than priced"),
    ("1998 LTCM and Russia", "1998-08-14", "1998-10-08", "default, deleveraging, flight to quality"),
    ("2008 Lehman", "2008-09-12", "2008-11-20", "systemic banking crisis"),
    ("2013 taper tantrum", "2013-05-21", "2013-06-24", "Fed signals slower bond purchases"),
    ("2015 renminbi devaluation", "2015-08-10", "2015-08-25", "China growth scare"),
    ("2018 Q4 sell-off", "2018-10-03", "2018-12-24", "Fed tightening into slowing growth"),
    ("2020 Covid crash", "2020-02-19", "2020-03-23", "pandemic shock, dash for cash"),
    ("2022 inflation shock", "2022-01-03", "2022-10-14", "fastest Fed hikes since 1980"),
    ("2023 regional banks", "2023-03-08", "2023-03-17", "SVB failure, rate repricing"),
    ("2024 yen carry unwind", "2024-07-31", "2024-08-05", "BoJ hike, crowded carry trades"),
]


def weekly_changes(series: Mapping[str, pd.Series], kinds: Mapping[str, str]) -> pd.DataFrame:
    """Friday-to-Friday changes in quoting units for every series."""
    out = {}
    for k, s in series.items():
        lv = business_daily(s).resample("W-FRI").last()
        out[k] = change(lv, kinds[k], 1)
    return pd.DataFrame(out)


def nearest_psd(c: pd.DataFrame, floor: float = 1e-10) -> pd.DataFrame:
    """Pairwise covariances need not form a valid matrix; clip negative eigenvalues."""
    a = c.to_numpy()
    a = (a + a.T) / 2
    w, v = np.linalg.eigh(a)
    a = (v * np.maximum(w, floor)) @ v.T
    return pd.DataFrame(a, index=c.index, columns=c.columns)


def covariance(W: pd.DataFrame, mask: pd.Series | None = None, min_weeks: int = 52) -> pd.DataFrame:
    """Pairwise covariance of weekly changes (zero mean assumed) on the weeks in `mask`."""
    d = W if mask is None else W.loc[mask.reindex(W.index).fillna(False).astype(bool)]
    keep = d.columns[d.notna().sum() >= min_weeks]
    d = d[keep]
    m = d.notna().astype(float)
    x = d.fillna(0.0)
    num = x.T @ x
    den = m.T @ m
    c = num / den.where(den >= min_weeks)
    return nearest_psd(c.dropna(how="all").dropna(axis=1, how="all"))


def conditional(
    cov: pd.DataFrame, shocks: dict[str, float], h_weeks: float = 1.0, nu: float | None = None
) -> pd.DataFrame:
    """Expected moves of the other assets given `shocks` over h weeks, with 68% and 95% bands.

    nu None: multivariate normal. nu > 2: multivariate Student-t with that many degrees of freedom
    and the same covariance. The conditional is then t with nu + k degrees of freedom and a scale
    that grows with the size of the shock (d² = s'Σ_ss⁻¹s): large shocks widen the bands."""
    s_ids = [k for k in shocks if k in cov.index]
    if not s_ids:
        raise ValueError("no shocked asset is in the covariance matrix")
    o_ids = [k for k in cov.index if k not in s_ids]
    c = cov * h_weeks
    css = c.loc[s_ids, s_ids].to_numpy()
    cos = c.loc[o_ids, s_ids].to_numpy()
    s = np.array([shocks[k] for k in s_ids], float)
    w = np.linalg.solve(css, s)
    mean = cos @ w
    var = np.diag(c.loc[o_ids, o_ids].to_numpy()) - np.einsum("ij,ij->i", cos @ np.linalg.inv(css), cos)
    var = np.maximum(var, 0.0)
    uncond = np.sqrt(np.diag(c.loc[o_ids, o_ids].to_numpy()))
    if nu is None:
        sd68 = sd95 = np.sqrt(var)
        q68, q95 = 1.0, 1.96
        share = 1 - var / uncond**2
    else:
        from scipy.stats import t as student

        k = len(s_ids)
        to_scale = (nu - 2) / nu  # covariance -> scale matrix
        d2 = float(s @ w) / to_scale
        scale = np.sqrt(var * to_scale * (nu + d2) / (nu + k))
        sd68 = sd95 = scale
        q68, q95 = student.ppf(0.84, nu + k), student.ppf(0.975, nu + k)
        share = 1 - var / uncond**2
    return pd.DataFrame(
        {
            "expected move": mean,
            "68% low": mean - q68 * sd68,
            "68% high": mean + q68 * sd68,
            "95% low": mean - q95 * sd95,
            "95% high": mean + q95 * sd95,
            "share of risk explained": share,
        },
        index=o_ids,
    )


def tail_dof(W: pd.DataFrame) -> float:
    """Degrees of freedom of a Student-t matching the median excess kurtosis of weekly changes
    (excess kurtosis of a t is 6 / (nu − 4)); floored at 4.5."""
    k = W.kurt().replace([np.inf, -np.inf], np.nan).dropna()
    k = float(k[k > 0].median()) if (k > 0).any() else np.nan
    return float(max(4.5, 4 + 6 / k)) if k == k else 30.0


def coverage_backtest(
    W: pd.DataFrame,
    cond_ids: tuple[str, ...] = ("SPX", "DGS10"),
    window: int = 104,
    start: str = "2010-01-01",
    nu: float | None = None,
) -> dict:
    """Out-of-sample calibration: each week t from `start`, a covariance from the previous `window`
    weeks only, conditioned on that week's realised moves of `cond_ids`; share of realised moves of
    every other asset inside the 68% and 95% bands (normal, or Student-t when `nu` is given)."""
    rows = []
    idx = W.index
    for i, t in enumerate(idx):
        if t < pd.Timestamp(start) or i < window:
            continue
        hist = W.iloc[i - window : i]
        x_t = W.iloc[i]
        if x_t[list(cond_ids)].isna().any():
            continue
        cov = covariance(hist, min_weeks=int(window * 0.75))
        if not all(c in cov.index for c in cond_ids):
            continue
        try:
            cd = conditional(cov, {c: float(x_t[c]) for c in cond_ids}, nu=nu)
        except np.linalg.LinAlgError:
            continue
        for a in cd.index:
            x = x_t.get(a)
            if pd.isna(x):
                continue
            r = cd.loc[a]
            rows.append(
                {
                    "week": t,
                    "asset": a,
                    "in68": r["68% low"] <= x <= r["68% high"],
                    "in95": r["95% low"] <= x <= r["95% high"],
                    "actual": x,
                    "expected": r["expected move"],
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        return {"pooled": {}, "by_asset": pd.DataFrame(), "n": 0}
    pooled = {
        "inside 68% band": float(df["in68"].mean()),
        "inside 95% band": float(df["in95"].mean()),
        "R² of expected moves": float(
            1 - ((df["actual"] - df["expected"]) ** 2).sum() / (df["actual"] ** 2).sum()
        ),
        "weeks": int(df["week"].nunique()),
        "from": df["week"].min().date(),
    }
    by = df.groupby("asset").agg(
        **{
            "inside 68% band": ("in68", "mean"),
            "inside 95% band": ("in95", "mean"),
            "weeks": ("in68", "size"),
        }
    )
    by["R² of expected moves"] = df.groupby("asset").apply(
        lambda g: 1 - ((g["actual"] - g["expected"]) ** 2).sum() / (g["actual"] ** 2).sum(),
        include_groups=False,
    )
    return {"pooled": pooled, "by_asset": by, "n": len(df)}


def episode_moves(
    series: Mapping[str, pd.Series], kinds: Mapping[str, str], episodes=EPISODES
) -> pd.DataFrame:
    """Move of every asset over every episode (start close to end close), in quoting units."""
    out = {}
    for name, a, b, _ in episodes:
        col = {}
        for k, s in series.items():
            s = s.dropna()
            pa, pb = s.loc[:a], s.loc[:b]
            if pa.empty or pb.empty or pa.index[-1] < pd.Timestamp(a) - pd.Timedelta(days=7):
                continue
            pair = pd.Series([pa.iloc[-1], pb.iloc[-1]])
            col[k] = float(change(pair, kinds[k], 1).iloc[-1])
        out[name] = pd.Series(col)
    return pd.DataFrame(out)


def analogs(
    W: pd.DataFrame, moves: pd.DataFrame, episodes=EPISODES, h: int = 13, min_assets: int = 6
) -> pd.DataFrame:
    """Similarity of the latest h-week cross-asset move with each episode: correlation of moves scaled
    by each asset's weekly standard deviation × sqrt(length in weeks)."""
    sd = np.sqrt((W**2).mean())
    cur = W.iloc[-h:].sum(min_count=h - 2) / (sd * np.sqrt(h))
    rows = []
    for name, a, b, desc in episodes:
        if name not in moves:
            continue
        weeks = max(1.0, (pd.Timestamp(b) - pd.Timestamp(a)).days / 7)
        ep = moves[name] / (sd.reindex(moves.index) * np.sqrt(weeks))
        both = pd.concat([cur, ep], axis=1, keys=["now", "ep"]).dropna()
        if len(both) < min_assets:
            continue
        rows.append(
            {
                "episode": name,
                "what happened": desc,
                "similarity (correlation)": float(both["now"].corr(both["ep"])),
                "assets compared": len(both),
            }
        )
    return pd.DataFrame(rows).set_index("episode").sort_values("similarity (correlation)", ascending=False)


def pca_factors(W: pd.DataFrame, years: int = 5, n: int = 4, anchor: str = "SPX") -> dict:
    """Principal components of standardised weekly changes over the last `years` (assets with full
    data), signs set so that `anchor` loads positively on the first factor. Stability: |cosine| of
    each factor's loadings estimated on the first and second halves of the window."""
    d = (
        W.loc[W.index[-1] - pd.DateOffset(years=years) :]
        .dropna(axis=1, thresh=int(52 * years * 0.9))
        .dropna()
    )
    z = (d - d.mean()) / d.std()

    def eig(x: pd.DataFrame):
        w, v = np.linalg.eigh(np.corrcoef(x.T.to_numpy()))
        o = np.argsort(w)[::-1]
        return w[o], v[:, o]

    w, v = eig(z)
    if anchor in z.columns and v[list(z.columns).index(anchor), 0] < 0:
        v[:, 0] *= -1  # other factors keep the solver's sign: read them from their loadings
    load = pd.DataFrame(v[:, :n], index=z.columns, columns=[f"Factor {k + 1}" for k in range(n)])
    scores = pd.DataFrame(z.to_numpy() @ v[:, :n], index=z.index, columns=load.columns)
    half = len(z) // 2
    _, v1 = eig(z.iloc[:half])
    _, v2 = eig(z.iloc[half:])
    stab = [float(abs(v1[:, k] @ v2[:, k])) for k in range(n)]
    # post hoc (research log H19): factors with close eigenvalues can swap or rotate between samples,
    # so also compare the plane spanned by the first two factors (mean cosine of principal angles)
    plane = float(np.linalg.svd(v1[:, :2].T @ v2[:, :2], compute_uv=False).mean())
    return {
        "explained": pd.Series(w[:n] / w.sum(), index=load.columns),
        "loadings": load,
        "scores_13w": scores.rolling(13).sum().dropna(),
        "stability": pd.Series(stab, index=load.columns),
        "plane_stability": plane,
        "weeks": len(z),
        "from": z.index[0],
        "assets": list(z.columns),
    }


def unit_of(kind: str) -> str:
    return UNITS[kind]
