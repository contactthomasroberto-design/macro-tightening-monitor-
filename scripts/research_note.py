"""Note de recherche (octobre 2026) — Macro Tightening Monitor, données live.

Tous les chiffres sont calculés ici à partir du cache live et des résultats des modèles du projet ;
le texte est rédigé autour de ces chiffres (f-strings), aucun chiffre n'est saisi à la main.
Le commentaire et la vue ont été écrits pour octobre 2026 : relire et adapter le texte avant de
régénérer la note pour un autre mois.

    MACRO_MODE=live python scripts/research_note.py   # -> docs/research/note_de_recherche_<AAAA-MM>.pdf
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import _bootstrap  # noqa: F401
from macro import pipeline
from macro.config import ROOT
from macro.data import get_series
from macro.utils import is_demo

if is_demo():
    raise SystemExit(
        "La note de recherche se construit uniquement à partir de données live (MACRO_MODE=live)."
    )

START = "2019-01-01"


def last(sid):
    s = get_series(sid).dropna()
    return float(s.iloc[-1]), s.index[-1]


def yoy(sid):
    s = get_series(sid).dropna()
    return float(100 * (s.iloc[-1] / s.iloc[-13] - 1)), s.index[-1]


def ann3m(sid):
    s = get_series(sid).dropna()
    return float(100 * ((s.iloc[-1] / s.iloc[-4]) ** 4 - 1))


def yoy_series(sid):
    s = get_series(sid).dropna()
    return (100 * (s / s.shift(12) - 1)).dropna()


def fr(x, d=1):
    """French number format: comma decimal separator."""
    return f"{x:.{d}f}".replace(".", ",")


def frs(x, d=1):
    return ("+" if x >= 0 else "−") + fr(abs(x), d)


def mois(ts):
    m = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    return f"{m[pd.Timestamp(ts).month - 1]} {pd.Timestamp(ts).year}"


# ------------------------------------------------------------------ chiffres
K: dict = {}
K["cpi"], K["cpi_d"] = yoy("CPIAUCSL")
K["core"], _ = yoy("CPILFESL")
K["core3m"] = ann3m("CPILFESL")
K["pce_core"], K["pce_d"] = yoy("PCEPILFE")
K["hicp"], K["hicp_d"] = yoy("EA_HICP")
K["hicp_core"], _ = yoy("EA_HICP_CORE")
K["hicp_core3m"] = ann3m("EA_HICP_CORE")
K["jp_cpi"], K["jp_d"] = yoy("JP_CPI")
K["brent"], K["brent_d"] = last("DCOILBRENTEU")
b = get_series("DCOILBRENTEU").dropna()
K["brent_12m"] = float(100 * (b.iloc[-1] / b.loc[: b.index[-1] - pd.DateOffset(years=1)].iloc[-1] - 1))
K["dff"], K["dff_d"] = last("DFF")
K["tgt_hi"], _ = last("DFEDTARU")
K["priced"], K["priced_d"] = last("FED_PRICED_12M")
K["dgs2"], _ = last("DGS2")
K["dgs10"], K["dgs10_d"] = last("DGS10")
K["real10"], _ = last("DFII10")
K["be10"], _ = last("T10YIE")
K["t10y3m"], _ = last("T10Y3M")
K["hy"], _ = last("BAMLH0A0HYM2")
K["vix"], _ = last("VIXCLS")
K["unrate"], K["un_d"] = last("UNRATE")
K["payroll_yoy"], _ = yoy("PAYEMS")
K["claims"], _ = last("ICSA")
K["mich"], _ = last("MICH")
K["t5y5y"], _ = last("T5YIFR")
K["ea_dfr"], _ = last("EA_DFR")
K["ea2y"], _ = last("EA_YC_2Y")
K["ea10y"], _ = last("EA_YC_10Y")
K["jp_call"], K["jp_call_d"] = last("JP_CALL_D")
K["jp2y"], _ = last("JP_2Y")
K["jp10y"], _ = last("JP_10Y")
j = get_series("JP_10Y").dropna()
K["jp10y_12m"] = float(100 * (j.iloc[-1] - j.loc[: j.index[-1] - pd.DateOffset(years=1)].iloc[-1]))
K["usdjpy"], _ = last("USDJPY")
K["eurusd"], _ = last("EURUSD")
kw = get_series("THREEFYTP10").dropna()
K["tp"] = float(kw.iloc[-1])
above = kw[kw >= K["tp"]]
prev = above[above.index < kw.index[-1] - pd.DateOffset(months=6)]
K["tp_since"] = prev.index[-1].year if len(prev) else None

# modèles
v = pipeline.build_views()
sc = v["scorecard"].set_index(["bank", "metric"])["value"]
gap = {b: float(sc[(b, "Policy gap (Taylor at r*=0.75 minus actual)")]) for b in ("FED", "ECB", "BOJ")}
K["fci_gap"] = float(sc[("FED", "Financial-conditions gap (FCI-lite)")])
pf = pipeline.policy_bundle("fed")["current"]
K["fed_i_q"], K["fed_pi"], K["fed_y"], K["fed_u"], K["fed_ustar"] = (
    pf["i"],
    pf["pi"],
    pf["y"],
    pf["u"],
    pf["ustar"],
)
K["taylor"] = K["fed_i_q"] + gap["FED"]
pe = pipeline.policy_bundle("ecb")["current"]
K["ecb_y"] = pe["y"]
rf_ecb = pipeline.policy_bundle("ecb")["rf_full"]
K["ecb_b"] = float(rf_ecb.value["estimate"]["b (inflation)"]) if rf_ecb.value is not None else np.nan
K["ecb_rf_n"] = rf_ecb.n_obs
pvm = v["priced_vs_model"].set_index(["bank", "item"])
K["model_med"] = float(pvm.loc[("FED", "Policy rate in 4 quarters"), "model (median)"])
K["model_lo"] = float(pvm.loc[("FED", "Policy rate in 4 quarters"), "model 68% low"])
K["model_hi"] = float(pvm.loc[("FED", "Policy rate in 4 quarters"), "model 68% high"])
infl = {r: pipeline.inflation_bundle(r) for r in ("US", "EA")}
for r in ("US", "EA"):
    pe_ = infl[r]["prob_exceed"]
    K[f"fc12_{r}"], K[f"p25_{r}"], K[f"sig_{r}"] = float(pe_["point"]), float(pe_["p"]), float(pe_["sigma"])
    s12 = infl[r]["oos"]["scores"][12]
    K[f"rel_{r}"] = float(s12.loc["COMB", "rel_rmse_vs_RW"])
    K[f"dmp_{r}"] = float(s12.loc["COMB", "dm_pvalue"])
g = pipeline.growth_bundle()
nc = g["nowcast"]
K["nc"], K["nc_lo"], K["nc_hi"], K["nc_q"] = nc["point"], nc["lo68"], nc["hi68"], str(nc["target"])
K["gdpnow"] = g["external_nowcasts"].get("Atlanta Fed GDPNow", np.nan)
K["wei"] = g["external_nowcasts"].get("Weekly Economic Index (y/y, latest week)", np.nan)
K["gar1"] = float(g["gar"][1].value)
K["gar4"] = float(g["gar"][4].value)
K["rec_us"] = float(g["recession"].value)
ea_rec = g["ea_recession"]["current"]
K["rec_ea"], K["rec_ea_lo"], K["rec_ea_hi"] = ea_rec["p"], ea_rec["lo"], ea_rec["hi"]
sahm = g["sahm"].dropna()
K["sahm"] = float(sahm["sahm"].iloc[-1])
c = pipeline.curves_bundle()
sov = c["sovereign"].dropna()
K["oat"], K["btp"], K["bonos"], K["sov_d"] = (
    *(float(sov[k].iloc[-1]) for k in ("OAT-Bund", "BTP-Bund", "Bonos-Bund")),
    sov.index[-1],
)
K["regime"] = str(c["regimes"].dropna()["regime"].iloc[-1])
t = pipeline.transmission_bundle()
sbr = t["stock_bond"]
sbr = getattr(sbr, "value", sbr)
K["corr_hi"] = float(sbr.loc["core > 3%", "corr"])
K["corr_mid"] = float(sbr.loc["core 2-3%", "corr"])
_roll = t["stock_bond_rolling"].dropna()
K["corr_now"] = float(_roll.iloc[-1] if isinstance(_roll, pd.Series) else _roll.iloc[-1, 0])
rb = getattr(t["real_betas"], "value", t["real_betas"])
spx_hi = rb[(rb["asset"] == "S&P 500") & (rb["regime"] == "core > 3%")].iloc[0]
K["beta_hi"], K["beta_hi_se"] = float(spx_hi["b_real"]), float(spx_hi["se_real"])
pos = pipeline.positioning_bundle()["table"]
K["am_ust_pct"] = float(pos.loc["Asset managers, 10Y Treasury (10Y equiv., contracts)", "percentile (3y)"])
K["lev_eur_pct"] = float(pos.loc["Leveraged funds, euro FX (USD bn)", "percentile (3y)"])
sr = v["scenario"]
bt = pipeline.backtest_bundle()
_fs, _ft = bt["fed"]["scores"], bt["fed"]["tests"]
K["bt_mkt"], K["bt_rule"], K["bt_n"] = (
    float(_fs.loc["market (1Y yield)", "RMSE"]),
    float(_fs.loc["rule", "RMSE"]),
    int(_fs.loc["rule", "n"]),
)
K["bt_b"], K["bt_p"] = float(_ft.loc["rule", "slope b"]), float(_ft.loc["rule", "p (b > 0)"])
K["bt_side"] = float(_ft.loc["rule", "outcome on forecast's side"])
_iv = bt["intervals"].set_index(["model", "h"])
K["cov68"], K["cov95"] = (
    float(_iv.loc[("COMB", 12), "coverage normal 68"]),
    float(_iv.loc[("COMB", 12), "coverage normal 95"]),
)
_is = bt["inflation"]["scores"]
K["spf_dm"] = float(bt["inflation"]["tests"].loc["our combination", "DM p"]) if not _is.empty else np.nan
from macro import note_calls  # noqa: E402
from macro.data import try_series  # noqa: E402

calls = note_calls.evaluate(try_series, note_calls.load())
hb = pipeline.history_bundle()
sim = {k: hb["similar"][k] for k in ("USA", "DEU", "JPN")}
cur = hb["current"]

# ================================================================== mise en page (style institutionnel)
# Inspirations : BlackRock Investment Institute (titre = conclusion, points clés, tableau des vues),
# Goldman Sachs Top of Mind (encadré « notre lecture », graphiques numérotés dont le titre est le
# message), Bridgewater (ce qui est intégré vs ce que nous attendons), J.P. Morgan Guide to the Markets
# (système visuel strict, chiffres clés en grand, un message par graphique), pratique des hedge funds
# macro (scénario central + alternatives probabilisées + signaux d'invalidation).
import os  # noqa: E402
from pathlib import Path  # noqa: E402

from fpdf import FPDF  # noqa: E402

from macro.reports import _font_path, ensure_browser  # noqa: E402

# Palette sobre : encre noire, un seul bleu institutionnel, une échelle de gris. Pas d'aplats colorés ;
# la hiérarchie vient de la typographie et de filets fins, comme dans les notes de banques centrales.
INK = (17, 17, 17)
BLUE = (0, 40, 85)
MUTED = (96, 96, 96)
RULE = (150, 150, 150)
HAIR = (215, 215, 215)
HEX = {
    "blue": "#002855",  # série principale (États-Unis, notre vue)
    "steel": "#7391b5",  # deuxième série (zone euro)
    "dark": "#3a3a3a",
    "grey": "#8c8c8c",
    "light": "#c4c4c4",
    "oxblood": "#7d1d1d",  # réservé au message d'un graphique
}
FONT_DIR = Path("/usr/share/fonts/truetype/liberation")


def _font(name: str, bold: bool) -> str:
    """Liberation Serif / Sans (métriques Times / Arial), DejaVu à défaut."""
    f = FONT_DIR / f"Liberation{name}-{'Bold' if bold else 'Regular'}.ttf"
    return str(f) if f.exists() else _font_path(bold)


ASOF = pd.Timestamp(K["dgs10_d"])
DATE_FR = f"{ASOF.day} {['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'][ASOF.month - 1]} {ASOF.year}"


class Note(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        for fam in ("Sans", "Serif"):
            self.add_font(fam, "", _font(fam, False))
            self.add_font(fam, "B", _font(fam, True))
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(auto=True, margin=20)
        self.exhibit_no = 0
        self.cover = True

    def multi_cell(self, *args, align="L", **kw):
        # left-aligned by default: justified headlines and labels look stretched
        return super().multi_cell(*args, align=align, **kw)

    # -------------------------------------------------- en-tête / pied
    def header(self):
        if self.cover:
            return
        self.set_font("Sans", "B", 7)
        self.set_text_color(*INK)
        self.set_xy(18, 9)
        self.cell(0, 4, "MACRO TIGHTENING MONITOR  ·  NOTE DE RECHERCHE")
        self.set_font("Sans", "", 7)
        self.set_text_color(*MUTED)
        self.set_xy(18, 9)
        self.cell(0, 4, DATE_FR, align="R")
        self.set_draw_color(*INK)
        self.set_line_width(0.25)
        self.line(18, 14, self.w - 18, 14)
        self.set_y(18)

    def footer(self):
        self.set_y(-13)
        self.set_draw_color(*HAIR)
        self.set_line_width(0.2)
        self.line(18, self.get_y() - 1, self.w - 18, self.get_y() - 1)
        self.set_font("Sans", "", 6.5)
        self.set_text_color(*MUTED)
        self.cell(
            0,
            3.5,
            "Produit de recherche éducatif, pas un conseil en investissement ni une vue officielle d'une banque centrale. "
            "Voir l'avertissement en dernière page.",
        )
        self.set_x(18)
        self.cell(0, 3.5, str(self.page_no()), align="R")

    # -------------------------------------------------- briques
    def text(self, s, size=9.2, color=INK, bold=False, lh=4.6, align="J"):
        self.set_font("Sans", "B" if bold else "", size)
        self.set_text_color(*color)
        self.multi_cell(0, lh, s, align=align, new_x="LMARGIN", new_y="NEXT")

    def rich(self, lead, body, size=9.2):
        """Paragraph with a bold lead-in, as in sell-side notes."""
        self.set_text_color(*INK)
        self.set_font("Sans", "B", size)
        self.write(4.6, lead + " ")
        self.set_font("Sans", "", size)
        self.write(4.6, body)
        self.ln(6)

    def need(self, mm):
        if self.get_y() + mm > self.h - 22:
            self.add_page()

    def section(self, n, label, headline):
        self.need(70)
        self.ln(2)
        self.set_draw_color(*INK)
        self.set_line_width(0.25)
        self.line(18, self.get_y(), self.w - 18, self.get_y())
        self.ln(1.5)
        self.set_font("Sans", "B", 7.5)
        self.set_text_color(*BLUE)
        self.cell(0, 4, f"{n}.  {label.upper()}", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Serif", "B", 15)
        self.set_text_color(*INK)
        self.multi_cell(0, 6.6, headline, new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)

    def takeaway(self, title, s):
        """« Notre lecture » between a blue rule and a hairline (no shaded box)."""
        self.ln(1)
        x, y = self.get_x(), self.get_y()
        self.set_font("Sans", "", 8.8)
        lines = self.multi_cell(self.w - 36 - 6, 4.4, s, dry_run=True, output="LINES")
        h = 7 + 4.4 * len(lines) + 2
        self.need(h + 2)
        x, y = self.get_x(), self.get_y()
        self.set_draw_color(*BLUE)
        self.set_line_width(0.5)
        self.line(x, y, x + self.w - 36, y)
        self.set_draw_color(*HAIR)
        self.set_line_width(0.25)
        self.line(x, y + h, x + self.w - 36, y + h)
        self.set_xy(x + 4, y + 2)
        self.set_font("Sans", "B", 7.5)
        self.set_text_color(*BLUE)
        self.cell(0, 4, title.upper(), new_x="LMARGIN", new_y="NEXT")
        self.set_x(x + 4)
        self.set_font("Sans", "", 8.8)
        self.set_text_color(*INK)
        self.multi_cell(self.w - 36 - 6, 4.4, s, align="J", new_x="LMARGIN", new_y="NEXT")
        self.set_y(y + h + 3)

    def exhibit(self, title, fig, source, h_px=430, w_px=1100):
        self.exhibit_no += 1
        h_mm = (self.w - 36) * h_px / w_px
        self.need(h_mm + 16)
        self.set_font("Sans", "B", 8.5)
        self.set_text_color(*INK)
        self.multi_cell(0, 4.4, f"Graphique {self.exhibit_no} : {title}", new_x="LMARGIN", new_y="NEXT")
        self.ln(0.5)
        if isinstance(fig, str):
            self.image(fig, w=self.w - 36)
        else:
            ensure_browser()
            path = str(SCRATCH / f"exhibit_{self.exhibit_no}.png")
            fig.write_image(path, width=w_px, height=h_px, scale=2)
            self.image(path, w=self.w - 36)
            os.unlink(path)
        self.set_font("Sans", "", 6.8)
        self.set_text_color(*MUTED)
        self.multi_cell(0, 3.4, f"Source : {source}.", new_x="LMARGIN", new_y="NEXT")
        self.ln(2.5)

    def table(self, header, rows, widths, size=7.6, zebra=False, bold_first=True, aligns=None):
        self.need(6 + 5.2 * len(rows))
        aligns = aligns or ["L"] * len(header)
        self.set_text_color(*INK)
        self.set_font("Sans", "B", size)
        nh = max(
            len(self.multi_cell(w - 1.5, 3.6, h, dry_run=True, output="LINES"))
            for h, w in zip(header, widths, strict=True)
        )
        hh = 3.6 * nh + 2
        y0 = self.get_y()
        self.set_draw_color(*INK)
        self.set_line_width(0.4)
        self.line(18, y0, 18 + sum(widths), y0)
        self.set_line_width(0.2)
        self.line(18, y0 + hh, 18 + sum(widths), y0 + hh)
        x = 18
        for h, w, a in zip(header, widths, aligns, strict=True):
            self.set_xy(x + 0.8, y0 + 1)
            self.multi_cell(w - 1.5, 3.6, h, align=a)
            x += w
        self.set_y(y0 + hh)
        for k, r in enumerate(rows):
            # row height from the tallest wrapped cell (first column is bold)
            nl = 1
            for j, (c, w) in enumerate(zip(r, widths, strict=True)):
                self.set_font("Sans", "B" if (bold_first and j == 0) else "", size)
                nl = max(nl, len(self.multi_cell(w - 1.5, 3.7, str(c), dry_run=True, output="LINES")))
            hrow = 3.7 * nl + 1.6
            self.need(hrow + 1)
            y0 = self.get_y()
            if zebra and k % 2 == 1:
                self.set_fill_color(245, 245, 245)
                self.rect(18, y0, sum(widths), hrow, style="F")
            x = 18
            for j, (c, w, a) in enumerate(zip(r, widths, aligns, strict=True)):
                self.set_xy(x + 0.8, y0 + 0.8)
                self.set_font("Sans", "B" if (bold_first and j == 0) else "", size)
                self.set_text_color(*INK)
                self.multi_cell(w - 1.5, 3.7, str(c), align=a)
                x += w
            self.set_y(y0 + hrow)
            last = k == len(rows) - 1
            self.set_draw_color(*(INK if last else HAIR))
            self.set_line_width(0.4 if last else 0.15)
            self.line(18, self.get_y(), 18 + sum(widths), self.get_y())
        self.ln(2)

    def tiles(self, items):
        """Key figures on a thin rule: value, label, context line."""
        n = len(items)
        gap_ = 3
        w = (self.w - 36 - gap_ * (n - 1)) / n
        y = self.get_y()
        for k, (val, lab, ctx) in enumerate(items):
            x = 18 + k * (w + gap_)
            self.set_draw_color(*INK)
            self.set_line_width(0.4)
            self.line(x, y, x + w, y)
            self.set_xy(x, y + 2.6)
            self.set_font("Serif", "B", 17)
            self.set_text_color(*INK)
            self.cell(w - 5, 7, val)
            self.set_xy(x, y + 10.2)
            self.set_font("Sans", "B", 6.8)
            self.set_text_color(*INK)
            self.multi_cell(w - 5, 3.2, lab.upper())
            self.set_xy(x, y + 17.2)
            self.set_font("Sans", "", 6.5)
            self.set_text_color(*MUTED)
            self.multi_cell(w - 5, 3, ctx)
        self.set_y(y + 27)


SCRATCH = ROOT / "out" / "live"
SCRATCH.mkdir(parents=True, exist_ok=True)


# ================================================================== graphiques (thème maison)
def theme(fig, ytitle="", height=430, legend=True):
    fig.update_layout(
        template="none",
        font={"family": "Liberation Sans, Arial", "size": 13, "color": "#111111"},
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin={"l": 55, "r": 70, "t": 30, "b": 35},
        height=height,
        showlegend=legend,
        legend={"orientation": "h", "x": 0, "y": 1.08, "font": {"size": 12}, "bgcolor": "rgba(0,0,0,0)"},
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, linecolor="#111111", ticks="outside", tickcolor="#111111")
    fig.update_yaxes(gridcolor="#e4e4e4", zeroline=False, title_text=ytitle, title_font={"size": 12})
    return fig


def end_labels(fig, series: dict, fmt="{:.1f} %", colors=None):
    """Value of each line written at its last point (Guide to the Markets habit)."""
    for k, (_name, s) in enumerate(series.items()):
        s = s.dropna()
        fig.add_annotation(
            x=s.index[-1],
            y=float(s.iloc[-1]),
            text=fmt.format(float(s.iloc[-1])).replace(".", ","),
            showarrow=False,
            xanchor="left",
            xshift=6,
            font={"size": 12, "color": (colors or [])[k] if colors else "#002855"},
        )


def lines_fig(df, colors, ytitle, label_fmt="{:.1f} %", hline=None, height=430, dash=None):
    fig = go.Figure()
    for k, col in enumerate(df.columns):
        s = df[col].dropna()
        fig.add_trace(
            go.Scatter(
                x=s.index,
                y=s.values,
                name=col,
                mode="lines",
                line={
                    "width": 2.6 if k == 0 else 2,
                    "color": colors[k],
                    "dash": (dash or {}).get(col, "solid"),
                },
            )
        )
    if hline is not None:
        fig.add_hline(y=hline, line_dash="dot", line_color="#8c8c8c", line_width=1.2)
    end_labels(fig, {c: df[c] for c in df.columns}, label_fmt, colors)
    return theme(fig, ytitle, height)


# 1. inflation
infl_df = pd.concat(
    {
        "États-Unis, totale": yoy_series("CPIAUCSL"),
        "États-Unis, sous-jacente": yoy_series("CPILFESL"),
        "Zone euro, totale": yoy_series("EA_HICP"),
        "Zone euro, sous-jacente": yoy_series("EA_HICP_CORE"),
    },
    axis=1,
).loc["2020-01-01":]
fig_infl = lines_fig(
    infl_df,
    [HEX["blue"], HEX["blue"], HEX["steel"], HEX["steel"]],
    "% sur un an",
    hline=2.0,
    dash={"États-Unis, sous-jacente": "dash", "Zone euro, sous-jacente": "dash"},
)
fig_infl.add_annotation(
    x=infl_df.index[-1],
    y=2.0,
    text="cible 2 %",
    showarrow=False,
    yshift=-10,
    xanchor="right",
    font={"size": 11, "color": "#8c8c8c"},
)

# 2. Brent
brent_w = get_series("DCOILBRENTEU").resample("W-FRI").last().loc["2021-01-01":].to_frame("Brent")
fig_brent = lines_fig(brent_w, [HEX["blue"]], "USD par baril", label_fmt="{:.0f} $", height=330)
fig_brent.update_layout(showlegend=False)
peak = brent_w["Brent"].loc["2026-01-01":].idxmax()
fig_brent.add_annotation(
    x=peak,
    y=float(brent_w["Brent"].loc[peak]),
    text="Guerre en Iran, détroit d'Ormuz",
    showarrow=True,
    arrowhead=0,
    ax=-120,
    ay=-10,
    font={"size": 11, "color": "#3a3a3a"},
    arrowcolor="#3a3a3a",
)

# 3. Fed : où se situe le marché
FOMC_SEP = 4.1  # médiane du FOMC pour fin 2026 (projections de septembre 2026) — source externe citée
anchors = [
    ("Taux effectif\naujourd'hui", K["dff"], HEX["light"]),
    ("Nos scénarios\n(médiane, 4 trim.)", K["model_med"], HEX["blue"]),
    ("FOMC\n(médiane fin 2026)", FOMC_SEP, HEX["grey"]),
    ("Marché\n(dans 12 mois)", K["priced"], HEX["dark"]),
    ("Règle de Taylor\n(r* = 0,75 %)", K["taylor"], HEX["light"]),
]
fig_fed = go.Figure(
    go.Bar(
        x=[a[0].replace("\n", "<br>") for a in anchors],
        y=[a[1] for a in anchors],
        marker_color=[a[2] for a in anchors],
        text=[fr(a[1], 2) + " %" for a in anchors],
        textposition="outside",
        textfont={"size": 13},
        width=0.6,
    )
)
theme(fig_fed, "%", 360, legend=False)
fig_fed.update_layout(margin={"b": 70})
fig_fed.update_yaxes(range=[0, max(a[1] for a in anchors) * 1.22])

# 4. taux directeurs
rates = pd.concat(
    {
        "Fed": get_series("DFF").resample("W-FRI").last(),
        "BCE": get_series("EA_DFR").resample("W-FRI").last(),
        "BoJ": get_series("JP_CALL_D").resample("W-FRI").last(),
    },
    axis=1,
).loc["2021-01-01":]
fig_rates = lines_fig(rates, [HEX["blue"], HEX["steel"], HEX["grey"]], "%", label_fmt="{:.2f} %", height=360)

# 5. décomposition du 10 ans
dec = (
    pd.concat(
        {
            "10 ans nominal": get_series("DGS10"),
            "Taux réel (TIPS)": get_series("DFII10"),
            "Point mort d'inflation": get_series("T10YIE"),
            "Prime de terme": get_series("THREEFYTP10"),
        },
        axis=1,
    )
    .resample("W-FRI")
    .last()
    .loc["2021-01-01":]
)
fig_dec = lines_fig(
    dec, [HEX["blue"], HEX["steel"], HEX["grey"], HEX["oxblood"]], "%", label_fmt="{:.2f} %", height=400
)

# 6. écarts souverains
sov_m = sov.loc["2021-01-01":].rename(
    columns={"OAT-Bund": "France (OAT)", "BTP-Bund": "Italie (BTP)", "Bonos-Bund": "Espagne (Bonos)"}
)
fig_sov = lines_fig(
    sov_m,
    [HEX["blue"], HEX["steel"], HEX["grey"]],
    "points de base vs Bund",
    label_fmt="{:.0f} pb",
    height=340,
)

# 7. corrélation actions-obligations par régime
sbr_plot = sbr.reindex(["core < 2%", "core 2-3%", "core > 3%"])
fig_corr = go.Figure(
    go.Bar(
        x=["Inflation sous-jacente<br>< 2 %", "2 à 3 %", "> 3 %"],
        y=sbr_plot["corr"],
        error_y={
            "type": "data",
            "symmetric": False,
            "array": sbr_plot["upper"] - sbr_plot["corr"],
            "arrayminus": sbr_plot["corr"] - sbr_plot["lower"],
            "color": "#8c8c8c",
        },
        marker_color=[HEX["light"], HEX["light"], HEX["blue"]],
        text=[frs(x, 2) for x in sbr_plot["corr"]],
        textposition="outside",
        width=0.55,
    )
)
theme(fig_corr, "corrélation", 340, legend=False)
fig_corr.update_layout(margin={"b": 60})
fig_corr.add_hline(y=0, line_color="#8c8c8c", line_width=1)
fig_corr.update_yaxes(range=[-0.8, 1.0])

# 8. éventail du taux directeur
q = sr["q_i"]
hist_ff = get_series("DFF").resample("MS").mean().loc["2022-01-01":]
fig_fan = go.Figure()
xs = [hist_ff.index[-1], *q.index]
for lo, hi, col, lab in (
    (0.05, 0.95, "rgba(0,40,85,0.10)", "90 % des trajectoires"),
    (0.16, 0.84, "rgba(0,40,85,0.24)", "68 % des trajectoires"),
):
    ys_hi = [float(hist_ff.iloc[-1]), *q[hi]]
    ys_lo = [float(hist_ff.iloc[-1]), *q[lo]]
    fig_fan.add_trace(
        go.Scatter(
            x=xs + xs[::-1],
            y=ys_hi + ys_lo[::-1],
            fill="toself",
            mode="lines",
            fillcolor=col,
            line={"width": 0},
            name=lab,
            hoverinfo="skip",
        )
    )
fig_fan.add_trace(
    go.Scatter(
        x=hist_ff.index,
        y=hist_ff.values,
        name="Taux effectif",
        mode="lines",
        line={"color": HEX["grey"], "width": 2.4},
    )
)
fig_fan.add_trace(
    go.Scatter(
        x=xs,
        y=[float(hist_ff.iloc[-1]), *q[0.5]],
        name="Médiane des scénarios",
        mode="lines",
        line={"color": HEX["blue"], "width": 2.6},
    )
)
t12 = hist_ff.index[-1] + pd.DateOffset(months=12)
fig_fan.add_trace(
    go.Scatter(
        x=[t12],
        y=[K["priced"]],
        mode="markers+text",
        name="Marché (12 mois)",
        marker={"color": HEX["dark"], "size": 11, "symbol": "diamond"},
        text=[fr(K["priced"], 2) + " %"],
        textposition="top center",
        textfont={"color": HEX["dark"], "size": 12},
    )
)
fig_fan.add_trace(
    go.Scatter(
        x=[pd.Timestamp("2026-12-31")],
        y=[FOMC_SEP],
        mode="markers",
        name="FOMC (fin 2026)",
        marker={"color": HEX["grey"], "size": 10, "symbol": "square"},
    )
)
theme(fig_fan, "%", 380)

# ================================================================== rédaction
priced_hikes = (K["priced"] - K["dff"]) / 0.25
ecb_priced = (K["ea2y"] - K["ea_dfr"]) * 100
boj_priced = (K["jp2y"] - K["jp_call"]) * 100
fed_gap_now = K["taylor"] - K["dff"]
w_model = dict(zip(sr["table"].index, sr["table"]["probability"], strict=False))
OUR_W = {
    "Soft landing / disinflation": 0.35,
    "Sticky inflation / stagflation-lite": 0.30,
    "Energy supply shock": 0.15,
    "Hard landing": 0.20,
}

n = Note()
n.add_page()
# ---------------------------------------------------------------- couverture
n.set_xy(18, 12)
n.set_font("Sans", "B", 7.5)
n.set_text_color(*BLUE)
n.cell(0, 4, "MACRO TIGHTENING MONITOR  ·  NOTE DE RECHERCHE")
n.set_x(18)
n.set_text_color(*MUTED)
n.set_font("Sans", "", 7.5)
n.cell(0, 4, DATE_FR, align="R")
n.set_draw_color(*INK)
n.set_line_width(0.6)
n.line(18, 18, n.w - 18, 18)
n.set_xy(18, 23)
n.set_font("Serif", "B", 24)
n.set_text_color(*INK)
n.multi_cell(n.w - 36, 10, "Une dernière hausse, pas un nouveau cycle", new_x="LMARGIN", new_y="NEXT")
n.ln(1)
n.set_x(18)
n.set_font("Serif", "", 11.5)
n.set_text_color(*MUTED)
n.multi_cell(
    n.w - 36,
    5.2,
    "Le choc pétrolier justifie le resserrement synchronisé de la Fed, de la BCE et de la BoJ. Pour la Fed, le prix "
    "de marché est notre scénario central : depuis 1990, il prévoit mieux que nos règles.",
    new_x="LMARGIN",
    new_y="NEXT",
)
n.ln(3)
n.set_draw_color(*HAIR)
n.set_line_width(0.25)
n.line(18, n.get_y(), n.w - 18, n.get_y())
n.ln(4)
n.cover = False
n.set_font("Sans", "B", 7.5)
n.set_text_color(*BLUE)
n.cell(0, 4, "POINTS CLÉS", new_x="LMARGIN", new_y="NEXT")
n.ln(1)
n.rich(
    "Le choc est réel et se diffuse.",
    f"Le Brent ({fr(K['brent'], 0)} $, {frs(K['brent_12m'], 0)} % sur un an) a porté l'inflation totale à {fr(K['cpi'])} % "
    f"aux États-Unis et {fr(K['hicp'])} % en zone euro. Aux États-Unis, l'inflation sous-jacente accélère : {fr(K['core3m'])} % "
    f"en rythme annualisé sur 3 mois, contre {fr(K['core'])} % sur un an.",
)
n.rich(
    "Fed : le marché d'abord.",
    f"Le marché intègre {fr(K['priced'], 2)} % dans un an, environ {fr(priced_hikes, 0)} hausses de plus. Nos scénarios "
    f"({fr(K['model_med'], 2)} %) et le FOMC ({fr(FOMC_SEP, 1)} % fin 2026) sont en deçà, mais cet écart n'est pas un signal : "
    f"sur {K['bt_n']} mois depuis 1990, le taux à 1 an prévoit mieux que notre règle (erreur quadratique moyenne {fr(K['bt_mkt'], 2)} contre "
    f"{fr(K['bt_rule'], 2)} pt) et la règle n'y ajoute rien (pente {frs(K['bt_b'], 2)}, p = {fr(K['bt_p'], 2)}). "
    "Erratum : la version précédente disait le marché « trop restrictif » ; le test ne le soutient pas.",
)
n.rich(
    "Les vrais risques sont en dehors des États-Unis.",
    f"En zone euro, l'écart OAT-Bund ({fr(K['oat'], 0)} pb) dépasse celui de l'Italie et limite la marge de la BCE. Au Japon, "
    f"le yen ({fr(K['usdjpy'], 1)} par dollar) pousse la BoJ à poursuivre. Côté marchés, avec une inflation sous-jacente "
    "au-dessus de 3 %, actions et obligations baissent ensemble : la diversification ne protège plus.",
)
n.ln(1)
n.tiles(
    [
        (f"{fr(K['brent'], 0)} $", "Brent", f"{frs(K['brent_12m'], 0)} % sur un an"),
        (f"{fr(K['core3m'])} %", "Inflation sous-jacente US", "rythme 3 mois annualisé"),
        (f"{fr(K['priced'], 2)} %", "Fed attendue à 12 mois", f"vs {fr(K['dff'], 2)} % aujourd'hui"),
        (f"{fr(K['dgs10'], 2)} %", "Taux US à 10 ans", f"dont {fr(K['real10'], 2)} % réel"),
        (f"{fr(K['oat'], 0)} pb", "Écart OAT-Bund", f"Italie : {fr(K['btp'], 0)} pb"),
    ]
)
n.set_font("Sans", "B", 7.5)
n.set_text_color(*BLUE)
n.cell(0, 4, "NOS VUES EN UN COUP D'ŒIL", new_x="LMARGIN", new_y="NEXT")
n.ln(1)
n.table(
    ["Thème", "Notre vue", "Ce qui est intégré", "Conviction", "Ce qui la ferait changer"],
    [
        [
            "Fed",
            "Le prix de marché ; nos règles ne le battent pas",
            f"{fr(K['priced'], 2)} % dans 12 mois (≈ {fr(priced_hikes, 0)} hausses)",
            "Pas d'écart",
            "Inflation sous-jacente < 2,5 % (3 mois) : le marché baisserait",
        ],
        [
            "BCE",
            "Pause, puis une hausse en décembre",
            f"2 ans à {fr(K['ea2y'], 2)} % (≈ {frs(ecb_priced, 0)} pb)",
            "Moyenne",
            "OAT-Bund au-delà de 120 pb",
        ],
        [
            "BoJ",
            "Normalisation graduelle (déc. ou janv.)",
            f"2 ans à {fr(K['jp2y'], 2)} % (≈ {frs(boj_priced, 0)} pb)",
            "Moyenne",
            "USD/JPY au-delà de 160",
        ],
        [
            "Croissance US",
            "Ralentissement sans récession à 12 mois",
            f"Probabilité de récession : {fr(100 * K['rec_us'], 0)} %",
            "Élevée",
            "Règle de Sahm déclenchée",
        ],
        [
            "Taux longs US",
            "Pression haussière tant que l'inflation dépasse 3 %",
            f"10 ans à {fr(K['dgs10'], 2)} %, prime {fr(K['tp'], 2)} %",
            "Moyenne",
            "Brent sous 90 $",
        ],
        [
            "Diversification",
            "Actions et obligations corrélées positivement",
            f"Corrélation actuelle {frs(K['corr_now'], 2)}",
            "Moyenne",
            "Inflation sous-jacente sous 2,5 %",
        ],
    ],
    [27, 44, 41, 19, 43],
    size=7.3,
)
n.text(
    "Les vues décrivent des implications macroéconomiques, pas des positions. « Ce qui est intégré » est lu dans les prix de "
    "marché ; « conviction » reflète l'accord entre nos modèles et la robustesse des estimations.",
    size=6.8,
    color=MUTED,
    lh=3.4,
)

# ---------------------------------------------------------------- 1. inflation
n.add_page()
n.section(
    1,
    "Inflation",
    "Le choc énergétique passe dans l'inflation sous-jacente américaine, pas encore européenne",
)
n.text(
    f"L'inflation totale a nettement remonté depuis le début de l'année : {fr(K['cpi'])} % aux États-Unis ({mois(K['cpi_d'])}) "
    f"et {fr(K['hicp'])} % en zone euro. La cause est connue : la guerre en Iran et les perturbations du détroit d'Ormuz ont "
    f"porté le Brent à {fr(K['brent'], 0)} $. Pour les banques centrales, la question n'est pas le niveau de l'énergie mais sa "
    "diffusion au reste des prix, que l'on lit dans la dynamique de l'inflation sous-jacente."
)
n.exhibit(
    "l'inflation totale remonte avec l'énergie ; la sous-jacente reste au-dessus de la cible",
    fig_infl,
    "BLS (via FRED), Eurostat ; glissement annuel ; calculs Macro Tightening Monitor",
)
n.rich(
    "États-Unis : la diffusion a commencé.",
    f"L'inflation sous-jacente progresse de {fr(K['core3m'])} % en rythme annualisé sur trois mois, au-dessus de son rythme "
    f"annuel ({fr(K['core'])} %). Le PCE sous-jacent, la mesure ciblée par la Fed, est à {fr(K['pce_core'])} %. Les ménages "
    f"anticipent {fr(K['mich'])} % d'inflation à un an, mais le point mort à 5 ans dans 5 ans ({fr(K['t5y5y'], 2)} %) montre "
    "que les marchés croient toujours à la désinflation à long terme.",
)
n.rich(
    "Zone euro : pas encore.",
    f"L'inflation sous-jacente ({fr(K['hicp_core'])} % sur un an) ralentit en rythme récent ({fr(K['hicp_core3m'])} % annualisé "
    "sur trois mois). Le choc y est pour l'instant un choc de niveau, pas de dynamique.",
)
n.exhibit(
    "le pétrole a presque doublé en un an",
    fig_brent,
    "EIA (via FRED), prix hebdomadaire du Brent ; annotation : Macro Tightening Monitor",
    h_px=330,
)
n.takeaway(
    "Notre lecture",
    f"Nos modèles prévoient {fr(K['fc12_US'])} % d'inflation totale américaine dans un an et {fr(K['fc12_EA'])} % en zone euro, "
    f"avec {fr(100 * K['p25_US'], 0)} % et {fr(100 * K['p25_EA'], 0)} % de probabilité de rester au-dessus de 2,5 %. "
    f"Aux États-Unis, la combinaison de modèles bat une prévision naïve de {fr(100 * (1 - K['rel_US']), 0)} % (p = {fr(K['dmp_US'], 2)}). "
    f"En zone euro, elle ne la bat pas (p = {fr(K['dmp_EA'], 2)}) : nous y donnons plus de poids à l'inflation observée qu'aux prévisions.",
)

# ---------------------------------------------------------------- 2. banques centrales
n.section(
    2,
    "Banques centrales",
    "Le marché a fait le chemin vers les règles ; nos modèles n'ont pas de quoi le contester",
)
n.text(
    f"La Fed a relevé ses taux le 16 septembre (fourchette 3,75-4,00 %), une première depuis 2023. Avec un PCE sous-jacent à "
    f"{fr(K['fed_pi'])} %, un écart de production positif ({frs(K['fed_y'])} %, CBO) et un chômage ({fr(K['fed_u'])} %) sous son "
    f"niveau naturel estimé ({fr(K['fed_ustar'])} %), toutes les règles de politique monétaire demandent davantage. La règle de "
    f"Taylor prescrit {fr(K['taylor'], 2)} %, soit {fr(fed_gap_now, 2)} point au-dessus du taux effectif ({fr(K['dff'], 2)} %). "
    "Ce verdict tient pour toute valeur de r* entre 0 et 1,5 %."
)
n.exhibit(
    "le marché s'est rapproché de la règle de Taylor ; nos scénarios et le FOMC restent en deçà",
    fig_fed,
    "FRED ; Atlanta Fed Market Probability Tracker (options sur SOFR, moyenne neutre au risque) ; projections du FOMC de "
    "septembre 2026 ; scénarios Macro Tightening Monitor (Monte Carlo, 10 000 trajectoires)",
    h_px=360,
)
n.rich(
    "Ce qui est intégré, ce que nous attendons.",
    f"Le marché attend {fr(K['priced'], 2)} % dans un an, environ {fr(priced_hikes, 0)} hausses de plus. Notre médiane "
    f"({fr(K['model_med'], 2)} %, intervalle à 68 % de {fr(K['model_lo'], 2)} à {fr(K['model_hi'], 2)} %) intègre l'inertie "
    "historique de la Fed et le risque de récession. Elle est cohérente avec le FOMC, qui ne prévoit qu'une hausse de plus "
    "d'ici fin 2026. Nous ne tirons pas de cet écart une vue contre le marché.",
)
n.takeaway(
    "Le test contre le marché",
    f"Depuis 1990, à chaque mois, nous avons comparé trois prévisions du taux des fed funds moyen des 12 mois suivants : le "
    f"taux à 1 an, notre règle réestimée avec les seules données disponibles alors, et le statu quo. Le marché gagne "
    f"(erreur quadratique moyenne {fr(K['bt_mkt'], 2)} pt contre {fr(K['bt_rule'], 2)} pour la règle, {K['bt_n']} mois). "
    f"Quand la règle et le marché divergent de plus d'un demi-point, le résultat tombe du côté de la règle dans "
    f"{fr(100 * K['bt_side'], 0)} % des cas, à peine mieux qu'à pile ou face, et la régression d'englobement ne lui trouve aucune information propre "
    f"(pente {frs(K['bt_b'], 2)}, p = {fr(K['bt_p'], 2)}). Les données révisées avantagent la règle : le test en temps réel "
    "(ALFRED) sera plus dur encore. Nous utilisons donc les modèles pour comprendre le prix, pas pour le battre.",
)
n.exhibit(
    "un resserrement synchronisé, mais à des niveaux très différents",
    fig_rates,
    "Réserve fédérale (via FRED), BCE, Banque du Japon ; données hebdomadaires",
    h_px=360,
)
n.rich(
    "BCE.",
    f"Le taux de dépôt ({fr(K['ea_dfr'], 2)} %, après les hausses de juin et septembre) est à peine supérieur à l'inflation "
    f"sous-jacente ({fr(K['hicp_core'])} %). Le 2 ans AAA ({fr(K['ea2y'], 2)} %) intègre environ {fr(ecb_priced, 0)} pb de hausses. "
    f"L'écart à la règle de Taylor ({frs(gap['ECB'], 2)} pt) est élevé, mais fragile : il dépend d'un écart de production estimé "
    f"({frs(K['ecb_y'])} %). Surtout, la fonction de réaction estimée ne respecte pas le principe de Taylor (coefficient "
    f"{fr(K['ecb_b'], 2)} sur {K['ecb_rf_n']} trimestres). Nous attendons une pause demain et une hausse en décembre, "
    "sous réserve du marché obligataire français.",
)
n.rich(
    "BoJ.",
    f"Le taux au jour le jour est à {fr(K['jp_call'], 2)} % après la hausse de septembre. Le 2 ans ({fr(K['jp2y'], 2)} %) intègre "
    f"la suite, et le 10 ans a pris {fr(K['jp10y_12m'], 0)} pb en un an. L'inflation publiée ({fr(K['jp_cpi'])} %, {mois(K['jp_d'])}) "
    f"est proche de la cible. Le yen faible ({fr(K['usdjpy'], 1)}) et l'écart de Taylor ({frs(gap['BOJ'], 2)} pt) plaident pour "
    "une nouvelle hausse en décembre ou en janvier.",
)

# ---------------------------------------------------------------- 3. croissance
n.section(
    3,
    "Croissance et récession",
    "L'économie américaine ralentit sans casser ; le risque est dans la queue de distribution",
)
n.table(
    ["Indicateur", "Dernier point", "Lecture"],
    [
        [
            f"Nowcast du PIB {K['nc_q']} (modèle à facteurs)",
            f"{fr(K['nc'])} % annualisé",
            f"Intervalle à 68 % : {fr(K['nc_lo'])} à {fr(K['nc_hi'])} %",
        ],
        ["GDPNow (Fed d'Atlanta)", f"{fr(K['gdpnow'])} %", "Plus optimiste que notre modèle"],
        ["Indice économique hebdomadaire (WEI)", f"{fr(K['wei'])} %", "Activité toujours solide"],
        ["Emploi salarié", f"+{fr(K['payroll_yoy'])} % sur un an", "Ralentissement net des créations"],
        ["Inscriptions au chômage", f"{fr(K['claims'] / 1000, 0)} 000", "Pas de licenciements de masse"],
        ["Règle de Sahm", f"{fr(K['sahm'], 2)} pt", "Seuil de récession : 0,5 pt"],
        [
            "Probabilité de récession à 12 mois",
            f"États-Unis {fr(100 * K['rec_us'], 0)} %, zone euro {fr(100 * K['rec_ea'], 0)} %",
            f"Zone euro : intervalle {fr(100 * K['rec_ea_lo'], 0)}–{fr(100 * K['rec_ea_hi'], 0)} %",
        ],
        [
            "Croissance, pire cas à 5 % (Growth-at-Risk)",
            f"{fr(K['gar1'])} % (1 trim.), {fr(K['gar4'])} % (4 trim.)",
            "Queue défavorable à court terme",
        ],
    ],
    [62, 46, 66],
)
n.takeaway(
    "Notre lecture",
    "Les indicateurs d'activité ne signalent pas de récession à un an. Mais l'emploi ralentit, et le quantile à 5 % de la "
    "croissance du prochain trimestre est négatif. Si les conditions financières se durcissent brutalement, la Fed n'aura "
    f"pas besoin d'aller au bout de ce que le marché intègre. Historiquement, {fr(100 * sim['USA']['share'], 0)} % des cycles "
    f"de hausse comparables à celui des États-Unis (sur {int(sim['USA']['n'])}) ont fini en récession dans les deux ans : un "
    "risque réel, mais pas un destin.",
)

# ---------------------------------------------------------------- 4. marchés
n.section(
    4,
    "Taux, crédit et souverains",
    "Le 10 ans à 5 % : plus de prime de terme, pas de perte de confiance dans la désinflation",
)
n.exhibit(
    f"un 10 ans à {fr(K['dgs10'], 2)} % porté par le taux réel et la prime de terme, pas par les anticipations d'inflation",
    fig_dec,
    "FRED (Trésor américain), Fed Board (prime de terme Kim-Wright) ; données hebdomadaires",
    h_px=400,
)
n.text(
    f"Le 10 ans se décompose en {fr(K['real10'], 2)} % de taux réel et {fr(K['be10'], 2)} % d'inflation anticipée. La prime de "
    f"terme ({fr(K['tp'], 2)} %) est au plus haut depuis {K['tp_since']} : les investisseurs exigent d'être payés pour "
    "l'incertitude sur l'inflation et pour l'offre de titres publics. Le crédit reste calme (écart haut rendement "
    f"{fr(100 * K['hy'], 0)} pb, VIX {fr(K['vix'], 1)}). Selon notre indice de conditions financières, il faudrait encore "
    f"l'équivalent de {fr(K['fci_gap'], 2)} point de croissance de resserrement pour refermer l'écart de production."
)
n.exhibit(
    "la France paie désormais plus que l'Italie face au Bund",
    fig_sov,
    "BCE (taux à long terme harmonisés) ; écarts mensuels face au Bund ; calculs Macro Tightening Monitor",
    h_px=340,
)
n.takeaway(
    "Notre lecture",
    f"L'écart OAT-Bund ({fr(K['oat'], 0)} pb en {mois(K['sov_d'])}) au-dessus du BTP ({fr(K['btp'], 0)} pb) est le fait marquant "
    "du trimestre en Europe. Il ne s'agit pas d'une crise : l'Espagne reste à "
    f"{fr(K['bonos'], 0)} pb, et le marché ne fuit pas la zone euro. Mais c'est une contrainte de premier ordre pour la BCE : "
    "chaque hausse de taux pèse sur la dette française. C'est la principale raison pour laquelle nous attendons une BCE "
    "plus lente que ne le suggère sa règle de Taylor.",
)

# ---------------------------------------------------------------- 5. transmission
n.section(
    5,
    "Transmission et positionnement",
    "Quand l'inflation dépasse 3 %, les obligations ne diversifient plus les actions",
)
n.exhibit(
    "la corrélation actions-obligations change de signe au-dessus de 3 % d'inflation sous-jacente",
    fig_corr,
    "FRED ; corrélation des rendements mensuels du S&P 500 et des variations du 10 ans, par régime d'inflation sous-jacente "
    "depuis 2000 ; barres : intervalle de confiance à 95 % ; calculs Macro Tightening Monitor",
    h_px=340,
)
n.text(
    f"Au-dessus de 3 % d'inflation sous-jacente, la corrélation entre actions et obligations est de {frs(K['corr_hi'], 2)} : les "
    f"deux baissent ensemble. Entre 2 et 3 %, elle est de {frs(K['corr_mid'], 2)}. Aujourd'hui ({frs(K['corr_now'], 2)}), nous "
    f"sommes à la frontière. Dans ce régime, 10 pb de hausse du taux réel coûtent en moyenne {fr(abs(K['beta_hi']) / 10, 2)} % au "
    "S&P 500 sur la semaine, davantage aux semi-conducteurs et aux valeurs liées à l'IA. Le positionnement amplifie le risque : "
    f"les gérants d'actifs détiennent une position longue record sur le 10 ans américain ({fr(K['am_ust_pct'], 0)}e centile sur "
    "trois ans). Une nouvelle hausse des taux pourrait les forcer à vendre."
)

# ---------------------------------------------------------------- 6. scénarios
n.section(6, "Scénarios", "Notre scénario central : une dernière hausse et une désinflation lente")
tab = sr["table"]
names = {
    "Soft landing / disinflation": "Désinflation lente (central)",
    "Sticky inflation / stagflation-lite": "Inflation tenace",
    "Energy supply shock": "Nouveau choc énergétique",
    "Hard landing": "Atterrissage brutal",
}
rows = []
for k, lab in names.items():
    rr = tab.loc[k]
    rows.append(
        [
            lab,
            f"{fr(100 * w_model[k], 0)} %",
            f"{fr(100 * OUR_W[k], 0)} %",
            f"{fr(rr['policy rate 4Q (median)'], 2)} %",
            f"{fr(rr['policy rate 8Q (median)'], 2)} %",
            f"{fr(rr['core PCE 4Q (median)'], 2)} %",
        ]
    )
wm = sum(OUR_W[k] * tab.loc[k, "policy rate 4Q (median)"] for k in names)
rows.append(["Moyenne (notre pondération)", "", "100 %", f"{fr(wm, 2)} %", "", ""])
n.table(
    [
        "Scénario",
        "Poids modèle",
        "Notre poids",
        "Fed dans 4 trim.",
        "Fed dans 8 trim.",
        "PCE sous-jacent 4 trim.",
    ],
    rows,
    [52, 22, 22, 26, 26, 26],
    aligns=["L", "R", "R", "R", "R", "R"],
)
n.text(
    "Médianes de 10 000 trajectoires simulées par scénario. Le poids modèle est l'hypothèse par défaut du projet ; notre "
    f"pondération relève le scénario d'inflation tenace de {fr(100 * (OUR_W['Sticky inflation / stagflation-lite'] - w_model['Sticky inflation / stagflation-lite']), 0)} "
    "points, au vu de l'accélération de l'inflation sous-jacente et du niveau du pétrole. Même ainsi, la moyenne pondérée "
    f"({fr(wm, 2)} %) reste sous le prix de marché ({fr(K['priced'], 2)} %).",
    size=7.8,
    color=MUTED,
    lh=3.9,
)
n.exhibit(
    "un éventail large : nous attendons un plateau, mais avec une asymétrie dans les deux sens",
    fig_fan,
    "FRED ; Atlanta Fed Market Probability Tracker ; projections du FOMC ; scénarios Macro Tightening Monitor (Monte "
    "Carlo, 10 000 trajectoires pondérées ; bandes de 5 à 95 % et de 16 à 84 %)",
    h_px=380,
)

# ---------------------------------------------------------------- 7. signaux
n.section(7, "Ce qui ferait changer notre vue", "Sept signaux, des seuils explicites")
n.table(
    ["Signal", "Dernier point", "Seuil", "Ce que cela changerait"],
    [
        [
            "Inflation sous-jacente US, 3 mois annualisé",
            f"{fr(K['core3m'])} %",
            "< 2,5 % deux mois de suite",
            "Le marché retire des hausses ; le scénario de pause devient central",
        ],
        [
            "Inflation sous-jacente US, 3 mois annualisé",
            f"{fr(K['core3m'])} %",
            "> 3 % jusqu'en mars",
            "Le marché ajoute des hausses ; le risque d'un vrai cycle monte",
        ],
        [
            "Brent",
            f"{fr(K['brent'], 0)} $",
            "< 90 $ ou > 130 $",
            "Désinflation rapide, ou second choc et bascule vers l'inflation tenace",
        ],
        [
            "Règle de Sahm (chômage)",
            f"{fr(K['sahm'], 2)} pt",
            "≥ 0,5 pt",
            "Atterrissage brutal : la Fed s'arrête et baisse ensuite",
        ],
        ["Écart OAT-Bund", f"{fr(K['oat'], 0)} pb", "> 120 pb", "La BCE suspend ses hausses"],
        ["USD/JPY", f"{fr(K['usdjpy'], 1)}", "> 160", "La BoJ accélère la normalisation"],
        [
            "Écart haut rendement",
            f"{fr(100 * K['hy'], 0)} pb",
            "> 500 pb",
            "Les marchés font le resserrement à la place des banques centrales",
        ],
    ],
    [50, 24, 34, 66],
)

# ---------------------------------------------------------------- 8. consensus
n.section(8, "Où nous nous situons", "Sur la Fed, le marché ; sur l'Europe, plus prudents que la règle")
n.table(
    ["", "Fed", "BCE", "BoJ"],
    [
        [
            "Nos modèles",
            f"{fr(K['model_med'], 2)} % dans 4 trim. (médiane)",
            f"Règle : {frs(gap['ECB'], 2)} pt d'écart, fiabilité faible",
            f"Règle : {frs(gap['BOJ'], 2)} pt d'écart",
        ],
        [
            "Marché",
            f"{fr(K['priced'], 2)} % dans 12 mois",
            f"≈ {fr(ecb_priced, 0)} pb de hausses (2 ans AAA)",
            f"≈ {fr(boj_priced, 0)} pb de hausses (2 ans)",
        ],
        [
            "Banque centrale",
            "FOMC : médiane 4,1 % fin 2026 (sept.)",
            "Pause attendue le 29 oct., hausse en déc.",
            "Pause attendue fin oct., hausse en déc. ou janv.",
        ],
        [
            "Grandes maisons",
            "BlackRock : une hausse de plus, marché trop restrictif",
            "Consensus : pause en octobre (32 sur 32)",
            "Standard Chartered : hausse en janvier",
        ],
    ],
    [30, 50, 48, 46],
)
n.text(
    "Sur la Fed, nos modèles, le FOMC et BlackRock voient moins de hausses que le marché. Faute de preuve que nos règles "
    "battent le prix de marché, nous ne prenons pas parti : le marché est le scénario central, nos scénarios en mesurent les "
    "risques. "
    "En Europe, nous sommes plus prudents que la règle de Taylor ne le suggère, à cause du marché obligataire français."
)

# ---------------------------------------------------------------- 9. post-mortem
_st = {"open": "En cours", "right": "Juste", "wrong": "Faux", "no data": "Pas de donnée"}
_done = calls[calls["status"].isin(["right", "wrong"])]
n.section(
    9,
    "Post-mortem",
    f"{len(_done)} appel{'s' if len(_done) > 1 else ''} arrivé{'s' if len(_done) > 1 else ''} à échéance sur {len(calls)} ; "
    + (
        f"{int((_done['status'] == 'right').sum())} juste{'s' if (_done['status'] == 'right').sum() > 1 else ''}"
        if len(_done)
        else "aucun bilan encore"
    ),
)
n.text(
    "Chaque appel de nos notes est enregistré à la publication (config/note_calls.yaml) avec sa mesure, son seuil et son "
    "échéance, puis noté sans retouche. Un appel retiré reste noté.",
)
n.table(
    ["Note", "Appel", "Échéance", "Dernier point", "Statut"],
    [
        [
            r["note"],
            r["statement"] + (" (retiré)" if r["withdrawn"] else ""),
            mois(r["matures"]),
            fr(r["value"], 2),
            _st[r["status"]],
        ]
        for _, r in calls.iterrows()
    ],
    [16, 92, 22, 22, 22],
    size=7.3,
)
n.text(
    f"Hors appels : nos prévisions d'inflation à 12 mois font jeu égal avec la médiane des prévisionnistes professionnels "
    f"(test de Diebold-Mariano, p = {fr(K['spf_dm'], 2)}) ; nous ne revendiquons pas d'avance sur le consensus.",
    size=8.4,
    lh=4.2,
)

# ---------------------------------------------------------------- annexes
n.add_page()
n.section("A", "Méthodologie et limites", "Comment lire cette note")
n.text(
    "Données publiques mises à jour chaque jour : FRED et ALFRED, BCE, Eurostat, BIS, Banque du Japon, ministère japonais des "
    "Finances, CFTC, Fed d'Atlanta, de New York et de Philadelphie, Global Macro Database. Les modèles sont décrits dans les "
    "fiches de modèle du projet : combinaison de modèles d'inflation évaluée hors échantillon ; règles de politique monétaire "
    "et fonction de réaction estimée ; modèle à facteurs dynamiques et Growth-at-Risk ; probit de récession ; scénarios de "
    "Monte Carlo avec graphiques en éventail ; bases de cycles historiques."
)
n.text(
    "Limites. Le r* et l'écart de production sont inobservables. Les évaluations utilisent les données révisées, pas celles "
    "disponibles en temps réel (le test en temps réel attend les millésimes ALFRED). Les intervalles à 95 % de l'inflation "
    f"couvrent {fr(100 * K['cov95'], 0)} % des réalisations à 12 mois au lieu de 95 % : les ratés se concentrent sur les "
    f"ruptures de régime (2008, 2020-2021) ; ceux à 68 % en couvrent {fr(100 * K['cov68'], 0)} %. L'inflation japonaise n'est disponible qu'avec retard. Faute de courbe OIS gratuite, les "
    "anticipations de la BCE et de la BoJ sont approchées par les taux à 2 ans. Les probabilités de scénarios, celles du "
    "modèle comme les nôtres, sont subjectives."
)
n.section("B", "Sources externes citées", "Contexte de marché et consensus")
n.text(
    "Décision du FOMC du 16 septembre 2026 et projections économiques (CNBC, TD Economics). BlackRock Investment Institute, "
    "commentaire hebdomadaire du 26 octobre 2026, « The Mideast energy shock's next phase ». Aperçus de la réunion de la BCE "
    "du 29 octobre 2026 (Funds Europe, RTÉ, finchiefs). Standard Chartered sur la BoJ (via Mitrade, 22 octobre 2026). "
    "Article Wikipédia « 2026 Iran war fuel crisis ». Ces sources servent au contexte ; les chiffres de la note viennent des "
    "données et modèles du projet.",
    size=8.4,
    lh=4.2,
)
n.section("C", "Avertissement", "Produit de recherche")
n.text(
    "Produit de recherche éducatif, susceptible d'être révisé ou interrompu. Ce document ne constitue ni une vue officielle "
    "d'une banque centrale, ni un conseil en investissement, ni une recommandation d'achat ou de vente. Les « vues » décrivent "
    "des implications macroéconomiques, pas des positions. Les données restent la propriété de leurs fournisseurs.",
    size=8.4,
    lh=4.2,
)

path = ROOT / "docs" / "research" / f"note_de_recherche_{ASOF:%Y-%m}.pdf"
n.output(str(path))
print(path, n.page_no(), "pages")
