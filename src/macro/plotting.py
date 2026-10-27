"""Chart conventions shared by the dashboard, the PDFs and the LinkedIn exports (BRIEF §7).

- Fixed entity colours across the app; further series in a fixed order.
- ~2px lines, no dual axes (use small multiples or indexing), legend for >= 2 series.
- Title states the finding; footer carries source and as-of date.
- Recession shading and policy-date annotations where relevant.
- Demo mode stamps a SYNTHETIC DATA banner on every figure.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import pandas as pd
import plotly.graph_objects as go

from macro.utils import DISCLAIMER, SYNTHETIC_BANNER, is_demo

ENTITY = {"fed": "#2a78d6", "ecb": "#eb6834", "boj": "#1baf7a"}
ENTITY_BY_REGION = {"US": ENTITY["fed"], "EA": ENTITY["ecb"], "JP": ENTITY["boj"]}
SERIES_ORDER = ["#6250d6", "#e87ba4", "#eda100", "#008300", "#e34948"]
PALETTE = [ENTITY["fed"], ENTITY["ecb"], ENTITY["boj"], *SERIES_ORDER]
STATUS = {
    "good": ("#0ca30c", "✔", "Good"),
    "warning": ("#fab219", "▲", "Warning"),
    "serious": ("#ec835a", "◆", "Serious"),
    "critical": ("#d03b3b", "✖", "Critical"),
}
LINE_WIDTH = 2

THEMES = {
    "light": {
        "bg": "#ffffff",
        "fg": "#1f2328",
        "grid": "#e6e8eb",
        "muted": "#6a737d",
        "shade": "rgba(120,120,120,0.15)",
    },
    "dark": {
        "bg": "#0e1117",
        "fg": "#e6edf3",
        "grid": "#262b33",
        "muted": "#9aa4ae",
        "shade": "rgba(200,200,200,0.12)",
    },
}


def color(i: int) -> str:
    return PALETTE[i % len(PALETTE)]


def fan_colors(base: str = ENTITY["fed"], n: int = 4) -> list[str]:
    """One hue, lightness steps from the outer (lightest) to the inner (darkest) band."""
    r, g, b = (int(base[i : i + 2], 16) for i in (1, 3, 5))
    alphas = [0.12 + 0.12 * k for k in range(n)]
    return [f"rgba({r},{g},{b},{a:.2f})" for a in alphas]


def base_layout(
    fig: go.Figure, title: str, source: str, as_of: str | None, theme: str = "light", height: int = 420
) -> go.Figure:
    t = THEMES[theme]
    footer = f"Source: {source}. As of {as_of or 'n/a'}."
    fig.update_layout(
        title={"text": title, "x": 0.0, "xanchor": "left", "font": {"size": 16}},
        paper_bgcolor=t["bg"],
        plot_bgcolor=t["bg"],
        font={"color": t["fg"], "size": 12},
        height=height,
        margin={"l": 60, "r": 20, "t": 60, "b": 80},
        hovermode="x unified",
        showlegend=len(fig.data) >= 2 or None,
        legend={"orientation": "h", "y": -0.18, "x": 0},
    )
    fig.update_xaxes(gridcolor=t["grid"], zeroline=False, showline=False)
    fig.update_yaxes(gridcolor=t["grid"], zerolinecolor=t["grid"], showline=False)
    fig.add_annotation(
        text=footer,
        xref="paper",
        yref="paper",
        x=0,
        y=-0.32,
        showarrow=False,
        xanchor="left",
        font={"size": 10, "color": t["muted"]},
    )
    if is_demo():
        stamp_synthetic(fig)
    return fig


def stamp_synthetic(fig: go.Figure) -> go.Figure:
    fig.add_annotation(
        text=SYNTHETIC_BANNER,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"size": 18, "color": "rgba(208,59,59,0.35)"},
        textangle=-12,
    )
    return fig


def add_recession_shading(
    fig: go.Figure, rec: pd.Series | None, theme: str = "light", row=None, col=None
) -> go.Figure:
    """Shade periods where `rec` == 1 (e.g. USREC)."""
    if rec is None or rec.empty:
        return fig
    r = rec.fillna(0).astype(int)
    starts = r.index[(r == 1) & (r.shift(1, fill_value=0) == 0)]
    ends = r.index[(r == 1) & (r.shift(-1, fill_value=0) == 0)]
    for s, e in zip(starts, ends, strict=False):
        kw = {"row": row, "col": col} if row is not None else {}
        fig.add_vrect(x0=s, x1=e, fillcolor=THEMES[theme]["shade"], line_width=0, layer="below", **kw)
    return fig


def add_policy_dates(
    fig: go.Figure, dates: Iterable[pd.Timestamp], label: str = "", theme: str = "light"
) -> go.Figure:
    for d in dates:
        fig.add_vline(x=d, line_width=1, line_dash="dot", line_color=THEMES[theme]["muted"])
    return fig


def line_chart(
    df: pd.DataFrame,
    title: str,
    source: str,
    as_of: str | None,
    yaxis: str = "",
    colors: Sequence[str] | None = None,
    rec: pd.Series | None = None,
    theme: str = "light",
    hline: float | None = None,
    height: int = 420,
) -> go.Figure:
    fig = go.Figure()
    for i, c in enumerate(df.columns):
        s = df[c].dropna()
        fig.add_trace(
            go.Scatter(
                x=s.index,
                y=s.values,
                name=str(c),
                mode="lines",
                line={"width": LINE_WIDTH, "color": (colors[i] if colors else color(i))},
            )
        )
    if hline is not None:
        fig.add_hline(y=hline, line_width=1, line_dash="dash", line_color=THEMES[theme]["muted"])
    add_recession_shading(fig, rec, theme)
    fig.update_yaxes(title_text=yaxis)
    return base_layout(fig, title, source, as_of, theme, height)


def band_chart(
    center: pd.Series,
    lower: pd.Series,
    upper: pd.Series,
    title: str,
    source: str,
    as_of: str | None,
    name: str = "estimate",
    band_name: str = "band",
    base_color: str = ENTITY["fed"],
    yaxis: str = "",
    rec: pd.Series | None = None,
    theme: str = "light",
    hline: float | None = None,
) -> go.Figure:
    fill = fan_colors(base_color, 2)[1]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=upper.index, y=upper.values, line={"width": 0}, showlegend=False, hoverinfo="skip")
    )
    fig.add_trace(
        go.Scatter(
            x=lower.index, y=lower.values, fill="tonexty", fillcolor=fill, line={"width": 0}, name=band_name
        )
    )
    fig.add_trace(
        go.Scatter(
            x=center.index, y=center.values, name=name, line={"width": LINE_WIDTH, "color": base_color}
        )
    )
    if hline is not None:
        fig.add_hline(y=hline, line_width=1, line_dash="dash", line_color=THEMES[theme]["muted"])
    add_recession_shading(fig, rec, theme)
    fig.update_yaxes(title_text=yaxis)
    return base_layout(fig, title, source, as_of, theme)


def fan_chart(
    history: pd.Series,
    quantiles: pd.DataFrame,
    title: str,
    source: str,
    as_of: str | None,
    conditioning: str,
    base_color: str = ENTITY["fed"],
    yaxis: str = "",
    theme: str = "light",
) -> go.Figure:
    """BoE-style fan: `quantiles` columns are probabilities (e.g. 0.05..0.95), index = forecast dates.

    Bands are drawn pairwise (q, 1-q) from outer to inner; the central line is the mode
    (column 'mode' if present, else the median).
    """
    probs = sorted(c for c in quantiles.columns if isinstance(c, float))
    pairs = [(lo, hi) for lo, hi in zip(probs, reversed(probs), strict=False) if lo < hi]
    fills = fan_colors(base_color, len(pairs))
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=history.index, y=history.values, name="outturn", line={"width": LINE_WIDTH, "color": "#6a737d"}
        )
    )
    for k, (lo, hi) in enumerate(pairs):
        fig.add_trace(
            go.Scatter(
                x=quantiles.index, y=quantiles[hi], line={"width": 0}, showlegend=False, hoverinfo="skip"
            )
        )
        fig.add_trace(
            go.Scatter(
                x=quantiles.index,
                y=quantiles[lo],
                fill="tonexty",
                fillcolor=fills[k],
                line={"width": 0},
                name=f"{int(round((hi - lo) * 100))}% band",
            )
        )
    central = quantiles["mode"] if "mode" in quantiles else quantiles[0.5]
    fig.add_trace(
        go.Scatter(
            x=central.index,
            y=central.values,
            name="central (mode)",
            line={"width": LINE_WIDTH, "color": base_color},
        )
    )
    fig.update_yaxes(title_text=yaxis)
    base_layout(fig, title, source, as_of, theme, height=460)
    fig.add_annotation(
        text=f"Conditioning: {conditioning}",
        xref="paper",
        yref="paper",
        x=0,
        y=1.0,
        yanchor="bottom",
        showarrow=False,
        xanchor="left",
        font={"size": 10, "color": THEMES[theme]["muted"]},
    )
    return fig


def bar_chart(
    s: pd.Series,
    title: str,
    source: str,
    as_of: str | None,
    yaxis: str = "",
    theme: str = "light",
    err: pd.Series | None = None,
    color_by_sign: bool = False,
) -> go.Figure:
    colors = (
        [(STATUS["critical"][0] if v > 0 else ENTITY["fed"]) for v in s.values] if color_by_sign else color(0)
    )
    fig = go.Figure(
        go.Bar(
            x=[str(i) for i in s.index],
            y=s.values,
            marker_color=colors,
            error_y=({"type": "data", "array": err.values} if err is not None else None),
        )
    )
    fig.update_yaxes(title_text=yaxis)
    return base_layout(fig, title, source, as_of, theme)


def status_badge(level: str) -> str:
    """Text badge for reserved status colours: always icon + label, never colour alone."""
    c, icon, label = STATUS[level]
    return f"{icon} {label}"


def footer_text() -> str:
    return DISCLAIMER
