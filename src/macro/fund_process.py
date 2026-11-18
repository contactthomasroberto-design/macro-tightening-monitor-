"""Investment process controls: a decision registry scored with the Brier score, loss post-mortems,
and forward stress tests with limits.

1. Decision registry (archive/decisions.csv). Every forecast the committee makes is recorded before
   the fact: an instrument or series, a metric ("level" at the horizon or "return" from the decision
   date to the horizon), a direction, a threshold, a horizon and a probability. Once the horizon has
   passed, `resolve` marks the outcome from the data (no human judgement) and the Brier score
   (p − outcome)² is computed per analyst. A forecaster who always says 50% scores 0.25; lower is
   better. The skill score is 1 − Brier / Brier of the base rate.
2. Post-mortems. Any position whose contribution to the book lost more than `threshold` of NAV over
   the review window gets an automatic diagnostic: its move in units of its ex-ante volatility, the
   part explained by the market (beta to SPY), its size against its bounds, and the view families
   behind it. The classification (bad luck, sizing, signal, market) is a starting point for the
   committee, not a verdict.
3. Forward stress tests. Hypothetical scenarios (config/stress_scenarios.yaml) shock a few assets;
   the others move by their conditional expectation from the covariance (stress_test.conditional).
   The book's loss is compared with the benchmark's loss and with an absolute limit per scenario.

Pure functions except the registry's CSV read and write."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from macro.config import ROOT

DECISIONS = ROOT / "archive" / "decisions.csv"
SCENARIOS = ROOT / "config" / "stress_scenarios.yaml"
POSTMORTEMS = ROOT / "docs" / "research" / "postmortems"
COLUMNS = [
    "id",
    "date",
    "agent",
    "claim",
    "target",
    "metric",
    "direction",
    "threshold",
    "horizon",
    "probability",
    "source",
    "status",
    "outcome",
    "realised",
    "resolved_on",
]


# ---------------------------------------------------------------------------- decision registry
def read_decisions(path: Path = DECISIONS) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path)
    for c in ("date", "horizon", "resolved_on"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def validate(d: dict) -> None:
    """Reject a decision that cannot be scored mechanically."""
    if d["metric"] not in ("level", "return"):
        raise ValueError(f"metric must be level or return, not {d['metric']!r}")
    if d["direction"] not in ("above", "below"):
        raise ValueError(f"direction must be above or below, not {d['direction']!r}")
    p = float(d["probability"])
    if not 0.0 <= p <= 1.0:
        raise ValueError("probability must be between 0 and 1")
    if pd.Timestamp(d["horizon"]) <= pd.Timestamp(d["date"]):
        raise ValueError("the horizon must be after the decision date")


def add_decisions(rows: list[dict], path: Path = DECISIONS) -> int:
    """Append new decisions (status open). Ids are date-agent-n; duplicates of an existing claim by
    the same agent on the same day are skipped."""
    old = read_decisions(path)
    out: list[dict] = []
    for d in rows:
        validate(d)
        day = pd.Timestamp(d["date"]).date().isoformat()
        same = old[(pd.to_datetime(old["date"]).dt.date.astype(str) == day) & (old["agent"] == d["agent"])]
        if (same["claim"] == d["claim"]).any() or any(
            o["claim"] == d["claim"] and o["agent"] == d["agent"] and o["date"] == day for o in out
        ):
            continue
        n = len(same) + sum(o["agent"] == d["agent"] and o["date"] == day for o in out) + 1
        out.append(
            {
                **{c: "" for c in COLUMNS},
                **d,
                "date": day,
                "horizon": pd.Timestamp(d["horizon"]).date().isoformat(),
                "id": f"{day}-{d['agent']}-{n}",
                "status": "open",
            }
        )
    if out:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(out, columns=COLUMNS).to_csv(path, mode="a", header=not Path(path).exists(), index=False)
    return len(out)


def _value(s: pd.Series, t: pd.Timestamp) -> float | None:
    s = s.dropna().loc[:t]
    return None if s.empty else float(s.iloc[-1])


def resolve(df: pd.DataFrame, get, today: pd.Timestamp) -> pd.DataFrame:
    """Score the open decisions whose horizon has passed. `get(target)` returns a daily series (price
    or level) or None. A decision stays open while the data for its horizon date is not published
    (last observation before the horizon), and is void if the target is unknown."""
    df = df.copy()
    for i, d in df[df["status"] == "open"].iterrows():
        if pd.Timestamp(d["horizon"]) > today:
            continue
        s = get(str(d["target"]))
        if s is None or s.dropna().empty:
            df.loc[i, ["status", "resolved_on"]] = ["void", today]
            continue
        s = s.dropna()
        if s.index[-1] < pd.Timestamp(d["horizon"]):
            continue  # not published yet
        end = _value(s, pd.Timestamp(d["horizon"]))
        if d["metric"] == "return":
            start = _value(s, pd.Timestamp(d["date"]))
            if start is None or end is None or start == 0:
                df.loc[i, ["status", "resolved_on"]] = ["void", today]
                continue
            x: float | None = end / start - 1
        else:
            x = end
        if x is None:
            df.loc[i, ["status", "resolved_on"]] = ["void", today]
            continue
        hit = x > float(d["threshold"]) if d["direction"] == "above" else x < float(d["threshold"])
        df.loc[i, ["status", "outcome", "realised", "resolved_on"]] = ["resolved", int(hit), x, today]
    return df


def write_decisions(df: pd.DataFrame, path: Path = DECISIONS) -> None:
    out = df.copy()
    for c in ("date", "horizon", "resolved_on"):
        out[c] = pd.to_datetime(out[c], errors="coerce").dt.date
    out[COLUMNS].to_csv(path, index=False)


def brier_table(df: pd.DataFrame) -> pd.DataFrame:
    """Brier score, skill against the base rate, calibration gap and counts per analyst (and 'team')."""
    r = df[df["status"] == "resolved"].copy()
    cols = ["resolved", "open", "Brier", "skill", "mean probability", "hit rate"]
    if r.empty:
        open_n = df[df["status"] == "open"].groupby("agent").size()
        return pd.DataFrame({"resolved": 0, "open": open_n}).reindex(columns=cols)
    r["p"] = r["probability"].astype(float)
    r["o"] = r["outcome"].astype(float)
    r["sq"] = (r["p"] - r["o"]) ** 2

    def row(g: pd.DataFrame) -> pd.Series:
        base = g["o"].mean()
        ref = ((base - g["o"]) ** 2).mean()
        b = g["sq"].mean()
        return pd.Series(
            {
                "resolved": len(g),
                "Brier": b,
                "skill": 1 - b / ref if ref > 0 else np.nan,
                "mean probability": g["p"].mean(),
                "hit rate": base,
            }
        )

    t = r.groupby("agent").apply(row, include_groups=False)
    t.loc["team"] = row(r)
    t["open"] = df[df["status"] == "open"].groupby("agent").size().reindex(t.index).fillna(0)
    t.loc["team", "open"] = (df["status"] == "open").sum()
    return t[cols].sort_values("Brier")


def calibration(df: pd.DataFrame, bins=(0, 0.2, 0.4, 0.6, 0.8, 1.0)) -> pd.DataFrame:
    """Forecast probability against observed frequency by bucket (reliability diagram)."""
    r = df[df["status"] == "resolved"]
    if r.empty:
        return pd.DataFrame(columns=["n", "forecast", "observed"])
    b = pd.cut(r["probability"].astype(float), list(bins), include_lowest=True)
    g = r.assign(p=r["probability"].astype(float), o=r["outcome"].astype(float)).groupby(b, observed=True)
    return pd.DataFrame({"n": g.size(), "forecast": g["p"].mean(), "observed": g["o"].mean()})


# ---------------------------------------------------------------------------- post-mortems
def position_pnl(weights: pd.DataFrame, r: pd.DataFrame, weeks: int) -> pd.Series:
    """Contribution of each position to NAV over the last `weeks` weeks: weights held at the start of
    each week (previous rebalance) times that week's return, summed."""
    w = weights.reindex(r.index).ffill().shift(1)
    c = (w * r.reindex(columns=w.columns)).dropna(how="all").iloc[-weeks:]
    return c.sum()


def post_mortem(
    asset: str,
    weights: pd.DataFrame,
    r: pd.DataFrame,
    cfg: dict,
    weeks: int,
    views: pd.DataFrame | None = None,
) -> dict:
    """Automatic diagnostic of a losing position over the last `weeks` weeks."""
    seg = r.iloc[-weeks:]
    hist = r.iloc[:-weeks].iloc[-156:]
    w = weights.reindex(r.index).ffill().shift(1).iloc[-weeks:][asset]
    move = float((1 + seg[asset].fillna(0)).prod() - 1)
    vol = float(hist[asset].std() * np.sqrt(weeks)) if hist[asset].notna().sum() > 26 else np.nan
    z = move / vol if vol and vol > 0 else np.nan
    beta = np.nan
    mkt = float((1 + seg["SPY"].fillna(0)).prod() - 1) if "SPY" in seg else np.nan
    if "SPY" in hist and asset != "SPY":
        h = hist[[asset, "SPY"]].dropna()
        if len(h) > 26 and h["SPY"].var() > 0:
            beta = float(h.cov().iloc[0, 1] / h["SPY"].var())
    explained = beta * mkt if np.isfinite(beta) and np.isfinite(mkt) else np.nan
    u = cfg["universe"].get(asset, {})
    size = float(w.abs().mean())
    at_bound = bool(
        np.isclose(w.iloc[-1], u.get("max", np.inf)) or np.isclose(w.iloc[-1], u.get("min", -np.inf))
    )
    if np.isfinite(z) and abs(z) < 1.5 and not at_bound:
        verdict = "malchance probable : mouvement inférieur à 1,5 écart-type, taille dans les bornes"
    elif at_bound:
        verdict = "taille : position à sa borne, la contrainte a fixé l'exposition"
    elif np.isfinite(explained) and abs(explained) > 0.6 * abs(move):
        verdict = "marché : plus de 60 % du mouvement s'explique par le bêta au S&P 500"
    else:
        verdict = "signal : mouvement extrême et propre au titre, revoir les vues qui le portaient"
    fam = {}
    if views is not None and asset in views.index:
        fam = {k: round(float(v), 4) for k, v in views.loc[asset].dropna().items()}
    return {
        "asset": asset,
        "weeks": weeks,
        "average weight": float(w.mean()),
        "average size": size,
        "asset move": move,
        "move in sigmas": z,
        "beta to SPY": beta,
        "market-explained move": explained,
        "at a bound": at_bound,
        "view families now": fam,
        "verdict": verdict,
    }


def losers(weights: pd.DataFrame, r: pd.DataFrame, threshold: float = 0.01, weeks: int = 4) -> pd.Series:
    pnl = position_pnl(weights, r, weeks)
    return pnl[pnl < -threshold].sort_values()


def post_mortem_markdown(pm: dict, loss: float, day: str) -> str:
    def f(x: float, pct: bool = True) -> str:
        if x is None or not np.isfinite(x):
            return "n.d."
        return f"{100 * x:+.1f} %".replace(".", ",") if pct else f"{x:+.2f}".replace(".", ",")

    fam = ", ".join(f"{k} {v:+.2%}" for k, v in pm["view families now"].items()) or "n.d."
    return "\n".join(
        [
            f"# Revue de perte : {pm['asset']} ({day})",
            "",
            f"Perte de la position sur {pm['weeks']} semaines : **{f(loss)} de la VL**.",
            "",
            "| Diagnostic | Valeur |",
            "|---|---|",
            f"| Poids moyen | {f(pm['average weight'])} |",
            f"| Mouvement du titre | {f(pm['asset move'])} |",
            f"| Mouvement en écarts-types ex ante | {f(pm['move in sigmas'], False)} |",
            f"| Bêta au S&P 500 (3 ans) | {f(pm['beta to SPY'], False)} |",
            f"| Part expliquée par le marché | {f(pm['market-explained move'])} |",
            f"| Position à sa borne | {'oui' if pm['at a bound'] else 'non'} |",
            f"| Vues actuelles par famille (rendement attendu) | {fam} |",
            "",
            f"**Classement automatique** : {pm['verdict']}.",
            "",
            "## À compléter par le comité",
            "- Erreur de donnée ? (prix, change, saut non expliqué)",
            "- Erreur de signal ? (quelle famille, depuis quand, test pré-enregistré concerné)",
            "- Erreur de taille ? (volatilité sous-estimée, corrélation instable)",
            "- Malchance ? (événement non prévisible, thèse intacte)",
            "- Décision : rien / hypothèse à pré-enregistrer / correction de données",
            "",
        ]
    )


# ---------------------------------------------------------------------------- forward stress tests
def load_scenarios(path: Path = SCENARIOS) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def forward_stress(
    target: pd.Series,
    bench_w: pd.Series,
    cov_annual: pd.DataFrame,
    spec: dict,
    hedge: dict | None = None,
) -> pd.DataFrame:
    """Loss of the book and of the benchmark in each scenario, with the limit check.

    Moves in percent: shocked assets take the scenario's moves, the others their conditional
    expectation given the shocks (weekly covariance; the mean is linear in the shocks, so the horizon
    does not change it). The tail-hedge puts pay max(K − S, 0) on the hedged share when the S&P 500
    falls below the strike (moneyness)."""
    from macro import stress_test as stt

    wk = cov_annual / 52 * 1e4  # (% per week)²
    lim = spec.get("limits", {})
    rows = {}
    for key, sc in spec["scenarios"].items():
        sh = {k: float(v) for k, v in sc["shocks"].items() if k in wk.index}
        if not sh:
            continue
        others = (
            stt.conditional(wk, sh, 1.0)["expected move"] if len(sh) < len(wk) else pd.Series(dtype=float)
        )
        moves = pd.concat([pd.Series(sh), others]) / 100
        port = float((target.reindex(moves.index).fillna(0) * moves).sum())
        hedge_pay = 0.0
        if hedge and "SPY" in moves:
            k = float(hedge.get("moneyness", 0.95))
            hedge_pay = float(hedge.get("hedged share of NAV", 0.0)) * max(k - (1 + moves["SPY"]), 0.0)
        bench = float((bench_w.reindex(moves.index).fillna(0) * moves).sum())
        total = port + hedge_pay
        cap = float(sc.get("limit", lim.get("absolute", 0.15)))
        rel = float(lim.get("relative_to_benchmark", 1.0))
        tol = float(lim.get("tolerance", 0.0))
        breach = []
        if -total > cap:
            breach.append(f"perte > {100 * cap:.0f} %")
        if bench < 0 and total < rel * bench - tol - 1e-9:
            breach.append(f"perte > benchmark + {100 * tol:.0f} pts" if tol else "perte > benchmark")
        worst = (target.reindex(moves.index).fillna(0) * moves).sort_values().head(3)
        rows[sc.get("label", key)] = {
            "book": total,
            "of which tail hedge": hedge_pay,
            "benchmark": bench,
            "limit": -cap,
            "breach": "; ".join(breach),
            "largest losses": ", ".join(f"{a} {100 * v:+.1f}%" for a, v in worst.items() if v < 0),
        }
    return pd.DataFrame(rows).T


# ---------------------------------------------------------------------------- performance tables
def _compound(r: pd.Series) -> float:
    r = r.dropna()
    return float((1 + r).prod() - 1) if len(r) else np.nan


def period_returns(ret: pd.Series, asof: pd.Timestamp | None = None) -> pd.Series:
    """Return over the usual reporting periods, from a weekly (or daily) return series.

    Last week, month to date, last month (previous calendar month), quarter to date, year to date,
    last 12 months, the previous calendar year, and since inception (annualised)."""
    ret = ret.dropna()
    if ret.empty:
        return pd.Series(dtype=float)
    t = asof or ret.index[-1]
    ret = ret.loc[:t]
    m0 = t.to_period("M").start_time
    pm = t.to_period("M") - 1
    q0 = t.to_period("Q").start_time
    y0 = t.to_period("Y").start_time
    per_year = 52 if (ret.index.to_series().diff().median() >= pd.Timedelta(days=5)) else 252
    years = len(ret) / per_year
    return pd.Series(
        {
            "week": float(ret.iloc[-1]) if per_year == 52 else _compound(ret.loc[t - pd.Timedelta(days=7) :]),
            "month to date": _compound(ret.loc[m0:]),
            f"last month ({pm.strftime('%b %Y')})": _compound(ret.loc[pm.start_time : pm.end_time]),
            "quarter to date": _compound(ret.loc[q0:]),
            "year to date": _compound(ret.loc[y0:]),
            "last 12 months": _compound(ret.loc[t - pd.DateOffset(years=1) + pd.Timedelta(days=1) :]),
            f"{t.year - 1}": _compound(ret.loc[f"{t.year - 1}"]),
            "since inception (annualised)": (1 + _compound(ret)) ** (1 / years) - 1 if years > 0 else np.nan,
        }
    )


def performance_summary(series: dict[str, pd.Series], asof: pd.Timestamp | None = None) -> pd.DataFrame:
    """Period returns (rows) for each series (columns), plus the excess of the first over the second."""
    t = asof or max(s.dropna().index[-1] for s in series.values() if not s.dropna().empty)
    out = pd.DataFrame({k: period_returns(v, t) for k, v in series.items()})
    if out.shape[1] >= 2:
        a, b = out.columns[:2]
        out[f"{a} − {b}"] = out[a] - out[b]
    return out


def calendar_table(ret: pd.Series, bench: pd.Series | None = None) -> pd.DataFrame:
    """Monthly returns by year (rows) and month (columns), with the year's total, and the benchmark's
    year and the excess when given. The current year is year to date."""
    ret = ret.dropna()
    if ret.empty:
        return pd.DataFrame()
    m = ret.groupby([ret.index.year, ret.index.month]).apply(_compound).unstack()
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    m = m.reindex(columns=range(1, 13))
    m.columns = names
    m["year"] = ret.groupby(ret.index.year).apply(_compound)
    if bench is not None:
        b = bench.dropna().loc[ret.index[0] :]
        m["benchmark"] = b.groupby(b.index.year).apply(_compound)
        m["excess"] = m["year"] - m["benchmark"]
    m.index.name = None
    return m.sort_index(ascending=False)


# ---------------------------------------------------------------------------- committee powers
ACTIONS = ROOT / "archive" / "committee_actions.csv"
ACTION_COLUMNS = ["date", "agent", "action", "target", "scale", "reason", "expires"]
MAX_DAYS = 14  # every action lapses after two weeks unless the committee renews it with a new reason
MIN_SCALE = 0.5  # de-risking can at most halve the risk budget


def read_actions(path: Path = ACTIONS) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=ACTION_COLUMNS)
    df = pd.read_csv(path)
    for c in ("date", "expires"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def add_action(row: dict, universe: dict, path: Path = ACTIONS) -> dict:
    """Record a committee action. Two powers, both able only to reduce risk:
    - "derisk": multiply the book's volatility budget by `scale` (0.5 to 1, target "ALL");
    - "freeze": no trade on one instrument (target = a universe ticker) while data or news are in doubt.
    "lift" ends an earlier action on the same target early. Each action needs a written reason and lapses
    after at most 14 days."""
    act = row["action"]
    if act not in ("derisk", "freeze", "lift"):
        raise ValueError("action must be derisk, freeze or lift")
    if not str(row.get("reason", "")).strip():
        raise ValueError("an action needs a written reason")
    day = pd.Timestamp(row["date"]).normalize()
    exp = pd.Timestamp(row.get("expires") or day + pd.Timedelta(days=MAX_DAYS)).normalize()
    exp = min(exp, day + pd.Timedelta(days=MAX_DAYS))
    scale = 1.0
    if act == "derisk":
        scale = float(row.get("scale", 0.75))
        if not MIN_SCALE <= scale <= 1.0:
            raise ValueError(f"de-risk scale must be between {MIN_SCALE} and 1 (never above: no added risk)")
        target = "ALL"
    else:
        target = str(row["target"])
        if target != "ALL" and target not in universe:
            raise ValueError(f"unknown instrument {target}")
    out = {
        "date": day.date().isoformat(),
        "agent": row.get("agent", "chief-investment-officer"),
        "action": act,
        "target": target,
        "scale": scale,
        "reason": str(row["reason"]).strip(),
        "expires": exp.date().isoformat(),
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([out], columns=ACTION_COLUMNS).to_csv(
        path, mode="a", header=not Path(path).exists(), index=False
    )
    return out


def active_actions(df: pd.DataFrame, today: pd.Timestamp) -> dict:
    """Actions in force today: the de-risk scale (the strictest active one) and the frozen instruments.
    A later "lift" on the same target cancels earlier actions on it."""
    today = pd.Timestamp(today).normalize()
    out: dict = {"derisk": 1.0, "frozen": [], "rows": []}
    if df is None or df.empty:
        return out
    df = df.sort_values("date")
    live: list[dict] = []
    for _, r in df.iterrows():
        if r["action"] == "lift":
            live = [
                x
                for x in live
                if x["target"] != r["target"] and not (r["target"] == "ALL" and x["action"] == "derisk")
            ]
            continue
        if pd.Timestamp(r["date"]) <= today < pd.Timestamp(r["expires"]) + pd.Timedelta(days=1):
            live.append(r.to_dict())
    for r in live:
        if r["action"] == "derisk":
            out["derisk"] = min(out["derisk"], max(MIN_SCALE, float(r["scale"])))
        elif r["action"] == "freeze":
            out["frozen"].append(r["target"])
    out["rows"] = live
    return out


def apply_freeze(target: pd.Series, current: pd.Series, frozen: list[str], cash: str = "BIL") -> pd.Series:
    """Hold frozen instruments at their current weight; the difference goes to cash."""
    if not frozen:
        return target
    t = target.copy()
    for a in frozen:
        cur = (
            float(current.get(a, 0.0)) if current is not None and not current.empty else float(t.get(a, 0.0))
        )
        diff = float(t.get(a, 0.0)) - cur
        t[a] = cur
        t[cash] = float(t.get(cash, 0.0)) + diff
    return t


def committee_impact(with_c: pd.Series, without_c: pd.Series, n: int = 8) -> pd.DataFrame:
    """Weight changes caused by the committee's views: target with them minus target without them."""
    d = with_c.reindex(with_c.index.union(without_c.index)).fillna(0) - without_c.reindex(
        with_c.index.union(without_c.index)
    ).fillna(0)
    d = d[d.abs() > 1e-4]
    top = d.reindex(d.abs().sort_values(ascending=False).index).head(n)
    return pd.DataFrame(
        {
            "with committee": with_c.reindex(top.index).fillna(0),
            "without": without_c.reindex(top.index).fillna(0),
            "change": top,
        }
    )
