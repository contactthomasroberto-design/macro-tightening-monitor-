"""Chart builders shared by the PDF reports and the LinkedIn exports. Titles state the finding and
are generated from current numbers; footers carry sources and as-of dates."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from macro import plotting as pl
from macro import policy as pol
from macro.config import assumptions
from macro.data import source_label, try_series
from macro.fincond import VARIABLES
from macro.growth import GROWTH_SPEC
from macro.panels import FCI_IDS


def policy_rules(pb: dict, start: str = "2015-01-01") -> go.Figure:
    a = assumptions()
    lo, hi = a["rstar"]["user_range"]
    mid = (lo + hi) / 2
    q = pb["panel"]["quarterly"]
    tgt = float(a["central_banks"][pb["bank"]]["inflation_target"])
    paths = pol.rule_paths(q, mid, a["rules"], tgt)
    df = pd.concat(
        [
            q["i"].rename("Actual policy rate"),
            paths[["Taylor (1993)", "Balanced approach", "Inertial Taylor"]],
        ],
        axis=1,
    ).loc[start:]
    cur = pb["current"]
    t93 = pol.taylor(cur["pi"], cur["y"], mid, tgt)
    gap = cur["i"] - t93
    ids = pb["panel"]["ids"]
    return pl.line_chart(
        df,
        f"{pb['bank'].upper()} policy rate is {abs(gap):.2f} pp {'below' if gap < 0 else 'above'} the Taylor (1993) "
        f"prescription (r* = {mid:.2f}%, range {lo:.2f}-{hi:.2f}%)",
        source_label(*[ids[k] for k in ("rate", "infl", "gdp", "pot") if k in ids]),
        pd.Timestamp(cur["date"]).strftime("%Y-%m"),
        yaxis="%",
        colors=[pl.ENTITY[pb["bank"]], *pl.SERIES_ORDER],
        rec=try_series("USREC"),
    )


def fci_decomposition(fcb: dict, n: int = 16) -> go.Figure:
    f1 = fcb["fci_1y"]
    contrib = f1.extra["contributions"].iloc[-n:]
    fig = go.Figure()
    for k, col in enumerate(contrib.columns):
        fig.add_trace(
            go.Bar(x=contrib.index, y=contrib[col], name=VARIABLES[col][0], marker_color=pl.color(k))
        )
    fig.add_trace(
        go.Scatter(
            x=contrib.index,
            y=contrib.sum(axis=1),
            name="FCI-lite 1y",
            mode="lines+markers",
            line={"color": "#1f2328", "width": 2},
        )
    )
    fig.update_layout(barmode="relative")
    fig.update_yaxes(title_text="pp of next-year GDP growth (+ = headwind)")
    g = fcb["gap"]
    return pl.base_layout(
        fig,
        f"Financial conditions: {g['fci_now']:+.2f} pp headwind; {g['gap']:+.2f} pp more needed to close the "
        "output gap (FCI-lite, not the Fed's FCI-G)",
        source_label(*FCI_IDS.values(), "GDPC1"),
        pd.Timestamp(fcb["as_of"]).to_period("Q").strftime("%Y-Q%q"),
        height=460,
    )


def nowcast_news(gb: dict) -> go.Figure:
    w = gb["weekly"]
    cols = [c for c in w.columns if c.startswith("news: ")]
    fig = go.Figure()
    for k, c in enumerate(cols):
        fig.add_trace(
            go.Bar(x=w.index, y=w[c].fillna(0), name=c.replace("news: ", ""), marker_color=pl.color(k))
        )
    fig.update_layout(barmode="relative")
    fig.update_yaxes(title_text="pp contribution to the weekly change")
    nc = gb["nowcast"]
    return pl.base_layout(
        fig,
        f"GDP nowcast for {nc['target']}: {nc['point']:.1f}% (68% band {nc['lo68']:.1f} to {nc['hi68']:.1f}); "
        "weekly news by release category",
        source_label(*GROWTH_SPEC, "GDPC1"),
        pd.Timestamp(gb["as_of"]).strftime("%Y-%m-%d"),
        height=420,
    )


def recession_and_gar(gb: dict) -> go.Figure:
    r = gb["recession"]
    oos = r.extra["oos"].drop(columns="y").loc["2000":]
    return pl.line_chart(
        oos,
        f"12-month recession probability {100 * r.value:.0f}% (90% band {100 * r.lower:.0f}-{100 * r.upper:.0f}%); "
        f"Growth-at-Risk 5% (4Q): {gb['gar'][4].extra['quantiles'][0.05]:.1f}%",
        source_label("T10Y3M", "BAA10Y", "UNRATE", "NFCI", "USREC", "GDPC1"),
        pd.Timestamp(gb["as_of"]).strftime("%Y-%m"),
        yaxis="probability",
        rec=try_series("USREC"),
    )


def term_premium_and_spreads(cvb: dict) -> go.Figure:
    tps = cvb["decomp"]["tp"]
    df = pd.DataFrame({k: v["term premium"] for k, v in tps.items()}).loc["2010":].resample("W-FRI").last()
    lat = cvb["stress"]["latest"]
    tp_txt = ", ".join(f"{k.split(' (')[0]} {v.iloc[-1]:.2f}%" for k, v in df.items())
    return pl.line_chart(
        df,
        f"10Y term premium: {tp_txt}; "
        f"BTP-Bund {lat.loc['BTP-Bund', 'spread (bp)']:.0f}bp ({lat.loc['BTP-Bund', 'percentile']:.0f}th pct)",
        source_label("THREEFYTP10", "ACMTP10", "DE_10Y", "IT_10Y"),
        pd.Timestamp(cvb["as_of"]).strftime("%Y-%m-%d"),
        yaxis="%",
        hline=0,
    )


def fan(sb: dict, sr: dict, key: str = "i", years_hist: int = 5) -> go.Figure:
    fq = sr["fans"][key]
    q = fq[[c for c in fq.columns if isinstance(c, float)]].copy()
    q["mode"] = fq["mode"]
    start = pd.Timestamp(sb["as_of"]) - pd.DateOffset(years=years_hist)
    hist = {"i": sb["policy_hist"], "pi": sb["history"]["pi"]}.get(key, pd.Series(dtype=float)).loc[start:]
    label = {"i": "Fed funds rate", "pi": "Core PCE inflation", "growth": "Real GDP growth (Okun-implied)"}[
        key
    ]
    return pl.fan_chart(
        hist,
        q,
        f"{label}: central projection {fq['mode'].iloc[-1]:.2f}% in 8 quarters; 90% of outcomes "
        f"between {fq[0.05].iloc[-1]:.2f}% and {fq[0.95].iloc[-1]:.2f}%",
        source_label("PCEPILFE", "UNRATE", "NROU", "DCOILBRENTEU", "DFF"),
        pd.Timestamp(sb["as_of"]).to_period("Q").strftime("%Y-Q%q"),
        conditioning="estimated reaction function; probability-weighted scenarios (scenarios.yaml)",
        yaxis="%",
    )


def track_record_chart(rows: pd.DataFrame, variable: str) -> go.Figure:
    d = rows[(rows["variable"] == variable)].dropna(subset=["actual"])
    fig = go.Figure()
    for k, (m, g) in enumerate(d.groupby("model")):
        fig.add_trace(
            go.Scatter(
                x=g["target_date"],
                y=g["point"],
                mode="markers",
                name=f"{m} forecast",
                marker={"color": pl.color(k)},
                error_y={
                    "type": "data",
                    "symmetric": False,
                    "array": g["q84"] - g["point"],
                    "arrayminus": g["point"] - g["q16"],
                },
            )
        )
    if not d.empty:
        a = d.drop_duplicates("target_date").sort_values("target_date")
        fig.add_trace(
            go.Scatter(
                x=a["target_date"],
                y=a["actual"],
                mode="lines+markers",
                name="outcome",
                line={"color": "#1f2328"},
            )
        )
    return pl.base_layout(
        fig, f"Track record: {variable}", "forecast archive (archive/forecasts.csv)", None, height=400
    )
