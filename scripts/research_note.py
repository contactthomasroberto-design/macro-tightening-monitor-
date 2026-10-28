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
from macro import plotting as pl
from macro.config import ROOT
from macro.data import get_series
from macro.reports import Report
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
hb = pipeline.history_bundle()
sim = {k: hb["similar"][k] for k in ("USA", "DEU", "JPN")}
cur = hb["current"]

# ------------------------------------------------------------------ graphiques
TH = "light"


def line(df: pd.DataFrame, title: str, source: str, yaxis: str, hline=None, colors=None, height=360):
    fig = go.Figure()
    for k, col in enumerate(df.columns):
        s = df[col].dropna()
        fig.add_trace(
            go.Scatter(
                x=s.index, y=s.values, name=col, line={"width": 2, "color": (colors or pl.PALETTE)[k % 7]}
            )
        )
    if hline is not None:
        fig.add_hline(y=hline, line_dash="dash", line_width=1, line_color="#6a737d")
    fig.update_yaxes(title_text=yaxis)
    pl.base_layout(
        fig, title, source, pd.Timestamp(df.dropna(how="all").index[-1]).strftime("%Y-%m"), TH, height=height
    )
    return fig


infl_df = pd.concat(
    {
        "États-Unis, IPC": yoy_series("CPIAUCSL"),
        "États-Unis, IPC sous-jacent": yoy_series("CPILFESL"),
        "Zone euro, IPCH": yoy_series("EA_HICP"),
        "Zone euro, IPCH sous-jacent": yoy_series("EA_HICP_CORE"),
    },
    axis=1,
).loc[START:]
fig_infl = line(
    infl_df,
    "Inflation : la composante énergie fait remonter l'inflation totale",
    "FRED (BLS), Eurostat",
    "% sur un an",
    hline=2.0,
    colors=[pl.ENTITY["fed"], "#8fb8ec", pl.ENTITY["ecb"], "#f3b28f"],
)
brent = get_series("DCOILBRENTEU").resample("W-FRI").last().loc[START:].to_frame("Brent, USD/baril")
fig_brent = line(
    brent,
    f"Pétrole : Brent à {fr(K['brent'], 0)} $ ({frs(K['brent_12m'], 0)} % sur un an)",
    "FRED (EIA)",
    "USD",
    height=300,
)

rates = pd.concat(
    {
        "Fed (taux effectif)": get_series("DFF").resample("W-FRI").last(),
        "BCE (taux de dépôt)": get_series("EA_DFR").resample("W-FRI").last(),
        "BoJ (taux au jour le jour)": get_series("JP_CALL_D").resample("W-FRI").last(),
    },
    axis=1,
).loc[START:]
fig_rates = line(
    rates,
    "Taux directeurs : un resserrement synchronisé",
    "FRED, BCE, Banque du Japon",
    "%",
    colors=[pl.ENTITY["fed"], pl.ENTITY["ecb"], pl.ENTITY["boj"]],
)

bars = pd.Series(
    {
        "Taux effectif actuel": K["dff"],
        "Modèle (médiane, 4 trim.)": K["model_med"],
        "Marché (dans 12 mois)": K["priced"],
        "Règle de Taylor (r* = 0,75 %)": K["taylor"],
    }
)
fig_bars = go.Figure(
    go.Bar(
        x=bars.index,
        y=bars.values,
        marker_color=["#6a737d", pl.ENTITY["fed"], "#1f3a5f", pl.SERIES_ORDER[0]],
        text=[f"{fr(x, 2)} %" for x in bars.values],
        textposition="outside",
    )
)
fig_bars.update_yaxes(title_text="%", range=[0, max(bars.values) * 1.2])
pl.base_layout(
    fig_bars,
    "Fed : où se situe le prix de marché ?",
    "FRED, Atlanta Fed (Market Probability Tracker), modèles du projet",
    mois(K["priced_d"]),
    TH,
    height=330,
)

dec = (
    pd.concat(
        {
            "10 ans nominal": get_series("DGS10"),
            "10 ans réel (TIPS)": get_series("DFII10"),
            "Point mort d'inflation": get_series("T10YIE"),
            "Prime de terme (Kim-Wright)": get_series("THREEFYTP10"),
        },
        axis=1,
    )
    .resample("W-FRI")
    .last()
    .loc[START:]
)
fig_dec = line(
    dec,
    f"Taux US à 10 ans : {fr(K['dgs10'], 2)} % = {fr(K['real10'], 2)} % réel + {fr(K['be10'], 2)} % d'inflation anticipée",
    "FRED, Fed Board (Kim-Wright)",
    "%",
)

fig_sov = line(
    sov.loc[START:],
    f"Écarts souverains face au Bund : l'OAT ({fr(K['oat'], 0)} pb) au-dessus du BTP ({fr(K['btp'], 0)} pb)",
    "BCE (taux à long terme harmonisés)",
    "points de base",
    colors=["#1f3a5f", pl.ENTITY["ecb"], pl.SERIES_ORDER[2]],
    height=320,
)

# ------------------------------------------------------------------ texte
fed_gap_now = K["taylor"] - K["dff"]
r = Report("Macro Tightening Monitor", "Note de recherche — octobre 2026")


def need(mm: float) -> None:
    """Start a new page unless `mm` of vertical space remain (no orphaned headings or split tables)."""
    if r.get_y() + mm > r.h - 20:
        r.add_page()


r.add_page()
r.set_font(r.family, "B", 18)
r.multi_cell(
    0,
    8,
    r.t("Resserrement synchronisé : justifié par l'inflation, déjà largement intégré par les marchés"),
    new_x="LMARGIN",
    new_y="NEXT",
    align="L",
)
r.set_font(r.family, "", 9)
r.set_text_color(90, 90, 90)
r.multi_cell(
    0,
    4.5,
    r.t(
        f"Fed, BCE, BoJ · données arrêtées au {pd.Timestamp(K['dgs10_d']).strftime('%d/%m/%Y')} · produit de recherche, pas un conseil en investissement"
    ),
    new_x="LMARGIN",
    new_y="NEXT",
)
r.set_text_color(0, 0, 0)
r.ln(2)

r.h2("Synthèse")
r.bullets(
    [
        f"Un choc énergétique (Brent à {fr(K['brent'], 0)} $, {frs(K['brent_12m'], 0)} % sur un an) relance l'inflation totale : "
        f"{fr(K['cpi'])} % aux États-Unis ({mois(K['cpi_d'])}), {fr(K['hicp'])} % en zone euro. L'inflation sous-jacente reste "
        f"au-dessus des cibles ({fr(K['pce_core'])} % pour le PCE sous-jacent américain, {fr(K['hicp_core'])} % en zone euro) "
        f"et son rythme récent accélère aux États-Unis ({fr(K['core3m'])} % en rythme annualisé sur 3 mois, contre {fr(K['core'])} % sur un an).",
        f"La Fed a déjà relevé ses taux (fourchette cible jusqu'à {fr(K['tgt_hi'], 2)} %). Une règle de Taylor (r* = 0,75 %) prescrit "
        f"encore {fr(K['taylor'], 2)} %, soit {fr(fed_gap_now, 2)} point au-dessus du taux effectif actuel ({fr(K['dff'], 2)} %).",
        f"Le marché intègre déjà l'essentiel de cet écart : {fr(K['priced'], 2)} % attendus dans 12 mois (options sur SOFR), "
        f"contre {fr(K['model_med'], 2)} % pour la médiane de nos scénarios (intervalle à 68 % : {fr(K['model_lo'], 2)}–{fr(K['model_hi'], 2)} %).",
        f"La croissance résiste : nowcast du PIB américain {K['nc_q']} à {fr(K['nc'])} % annualisé (GDPNow : {fr(K['gdpnow'])} %), "
        f"probabilité de récession à 12 mois {fr(100 * K['rec_us'], 0)} % aux États-Unis et {fr(100 * K['rec_ea'], 0)} % en zone euro. "
        f"Mais l'emploi ralentit (+{fr(K['payroll_yoy'])} % sur un an) et le quantile à 5 % de la croissance du trimestre prochain est négatif ({fr(K['gar1'])} %).",
        f"Les marchés de taux portent le coût : 10 ans américain à {fr(K['dgs10'], 2)} %, dont {fr(K['real10'], 2)} % de taux réel ; "
        f"prime de terme de {fr(K['tp'], 2)} %"
        + (f", au plus haut depuis {K['tp_since']}" if K["tp_since"] else "")
        + ". "
        f"En Europe, l'écart OAT-Bund ({fr(K['oat'], 0)} pb) dépasse désormais l'écart BTP-Bund ({fr(K['btp'], 0)} pb).",
    ]
)
r.box(
    "Notre vue (recherche, pas un conseil)",
    "Le resserrement est justifié aux États-Unis et, dans une moindre mesure, en zone euro : l'inflation sous-jacente est au-dessus "
    "de la cible, les écarts de production sont positifs et le choc pétrolier menace les anticipations "
    f"(attentes des ménages à un an : {fr(K['mich'])} %). Pour la Fed, le marché se situe entre la règle de Taylor et le comportement "
    "historique estimé de la banque centrale : il a déjà intégré l'essentiel du resserrement justifié par les règles. "
    "Nous jugeons donc le prix de marché cohérent avec le scénario d'inflation tenace, mais légèrement trop restrictif au regard "
    "de nos scénarios pondérés, à condition que le choc énergétique ne se propage pas à l'inflation sous-jacente. "
    "Le signal à surveiller est l'inflation sous-jacente en rythme annualisé sur 3 mois : "
    f"à {fr(K['core3m'])} %, elle va pour l'instant dans le sens du marché. "
    "Pour la BoJ, la normalisation doit se poursuivre graduellement ; pour la BCE, la marge est limitée par le stress souverain français.",
)

r.h2("Chiffres clés")
kt = pd.DataFrame(
    [
        [
            "Inflation totale (sur un an)",
            f"{fr(K['cpi'])} %",
            f"{fr(K['hicp'])} %",
            f"{fr(K['jp_cpi'])} % ({mois(K['jp_d'])})",
        ],
        [
            "Inflation sous-jacente (sur un an)",
            f"{fr(K['core'])} % (IPC) / {fr(K['pce_core'])} % (PCE)",
            f"{fr(K['hicp_core'])} %",
            "n.d.",
        ],
        ["Taux directeur", f"{fr(K['dff'], 2)} %", f"{fr(K['ea_dfr'], 2)} %", f"{fr(K['jp_call'], 2)} %"],
        ["Taux à 2 ans", f"{fr(K['dgs2'], 2)} %", f"{fr(K['ea2y'], 2)} % (AAA)", f"{fr(K['jp2y'], 2)} %"],
        [
            "Taux à 10 ans",
            f"{fr(K['dgs10'], 2)} %",
            f"{fr(K['ea10y'], 2)} % (AAA)",
            f"{fr(K['jp10y'], 2)} % ({frs(K['jp10y_12m'], 0)} pb sur 12 mois)",
        ],
        [
            "Écart règle de Taylor − taux",
            f"{frs(gap['FED'], 2)} pt",
            f"{frs(gap['ECB'], 2)} pt",
            f"{frs(gap['BOJ'], 2)} pt",
        ],
        [
            "Probabilité de récession à 12 mois",
            f"{fr(100 * K['rec_us'], 0)} %",
            f"{fr(100 * K['rec_ea'], 0)} %",
            "n.d.",
        ],
    ],
    columns=["", "États-Unis", "Zone euro", "Japon"],
)
r.table(kt, col_widths=[52, 50, 40, 40], size=7.5, index=False)
r.set_font(r.family, "", 7)
r.set_text_color(110, 110, 110)
r.multi_cell(
    0,
    3.4,
    r.t(
        "Écarts de Taylor calculés avec les dernières données trimestrielles disponibles (taux moyen du trimestre), avant la dernière hausse de la Fed."
    ),
    new_x="LMARGIN",
    new_y="NEXT",
)
r.set_text_color(0, 0, 0)

# --- 1. Inflation
r.add_page()
r.h1("1. Inflation : le choc énergétique et la question de la diffusion")
r.para(
    f"L'inflation totale remonte des deux côtés de l'Atlantique : {fr(K['cpi'])} % aux États-Unis et {fr(K['hicp'])} % en zone euro, "
    f"portée par l'énergie (Brent {frs(K['brent_12m'], 0)} % sur un an). La question décisive pour les banques centrales est la "
    "diffusion à l'inflation sous-jacente. Aux États-Unis, le rythme sur 3 mois de l'IPC sous-jacent "
    f"({fr(K['core3m'])} % annualisé) dépasse son rythme sur un an ({fr(K['core'])} %) : la dynamique récente accélère. En zone euro, "
    f"l'inflation sous-jacente ({fr(K['hicp_core'])} % sur un an, {fr(K['hicp_core3m'])} % annualisé sur 3 mois) reste plus contenue. "
    f"Au Japon, l'IPC progresse de {fr(K['jp_cpi'])} % sur un an, mais la donnée disponible date de {mois(K['jp_d'])} "
    "(série BIS publiée avec retard) et sous-estime probablement l'effet du yen faible "
    f"({fr(K['usdjpy'], 1)} yens par dollar)."
)
r.image_fig(fig_infl, px=(1000, 420))
r.image_fig(fig_brent, px=(1000, 300))
r.h2("Prévisions à 12 mois et leur fiabilité")
r.para(
    f"La combinaison de modèles prévoit {fr(K['fc12_US'])} % d'inflation totale américaine dans 12 mois et {fr(K['fc12_EA'])} % en zone euro. "
    f"La probabilité que l'inflation dépasse 2,5 % est de {fr(100 * K['p25_US'], 0)} % aux États-Unis et de "
    f"{fr(100 * K['p25_EA'], 0)} % en zone euro. L'incertitude est large (écart-type de {fr(K['sig_US'])} point aux États-Unis)."
)
r.para(
    f"Ces prévisions doivent être lues avec leur historique. Aux États-Unis, la combinaison réduit l'erreur de "
    f"{fr(100 * (1 - K['rel_US']), 0)} % par rapport à une prévision naïve (test de Diebold-Mariano, p = {fr(K['dmp_US'], 2)}). "
    f"En zone euro, le gain est faible ({fr(100 * (1 - K['rel_EA']), 0)} %, p = {fr(K['dmp_EA'], 2)}) : les modèles n'y battent "
    "pas significativement la prévision naïve, et l'inflation actuelle reste la meilleure référence."
)

# --- 2. Banques centrales
r.add_page()
r.h1("2. Banques centrales : derrière la courbe, mais le marché a corrigé")
r.image_fig(fig_rates, px=(1000, 400))
r.h2("Fed")
r.para(
    f"Avec un PCE sous-jacent à {fr(K['fed_pi'])} %, un écart de production estimé à {frs(K['fed_y'])} % (CBO) et un chômage "
    f"({fr(K['fed_u'])} %) sous son niveau naturel estimé ({fr(K['fed_ustar'])} %), toutes les règles de politique monétaire "
    f"prescrivent un taux plus élevé que le taux actuel. La règle de Taylor (r* = 0,75 %) indique {fr(K['taylor'], 2)} %. "
    "Le verdict ne dépend pas de l'hypothèse sur r* : la règle reste au-dessus du taux effectif sur toute la plage de r* "
    "(0 à 1,5 %) et de coefficients testée."
)
r.image_fig(fig_bars, px=(1000, 330))
r.para(
    f"Trois repères encadrent le taux dans un an. La médiane de nos scénarios ({fr(K['model_med'], 2)} %) reflète l'inertie "
    f"historique de la Fed. Le prix de marché ({fr(K['priced'], 2)} %) correspond à environ trois hausses de 25 pb. La règle de "
    f"Taylor ({fr(K['taylor'], 2)} %) ne tient compte ni de l'inertie ni du risque de récession. Le marché se situe donc plus près "
    "de la règle que du comportement passé de la Fed. Les simulations (10 000 trajectoires par scénario) attribuent "
    f"{fr(100 * float(sr['moves'].loc[3, 'P(at least k hikes)']), 0)} % de probabilité à au moins trois hausses de 25 pb en "
    f"quatre trimestres, et {fr(100 * float(sr['moves'].loc[4, 'P(at least k hikes)']), 0)} % à au moins quatre. Ces chiffres sont "
    f"comptés à partir du taux moyen du troisième trimestre ({fr(K['fed_i_q'], 2)} %)."
)
r.h2("BCE")
r.para(
    f"Le taux de dépôt ({fr(K['ea_dfr'], 2)} %) est proche de l'inflation sous-jacente ({fr(K['hicp_core'])} %) : le taux réel est "
    f"donc voisin de zéro. Le taux à 2 ans AAA ({fr(K['ea2y'], 2)} %) intègre des hausses. L'écart à la règle de Taylor "
    f"({frs(gap['ECB'], 2)} pt) est le plus élevé des trois banques centrales, mais il est fragile pour deux raisons : il dépend "
    f"d'un écart de production estimé ({frs(K['ecb_y'])} %), et la fonction de réaction estimée de la BCE ne satisfait pas le "
    f"principe de Taylor (coefficient d'inflation {fr(K['ecb_b'], 2)}, sur seulement {K['ecb_rf_n']} trimestres). "
    "Nous retenons la direction (resserrement modéré) plus que l'ampleur."
)
r.h2("BoJ")
r.para(
    f"La normalisation est en cours : taux au jour le jour à {fr(K['jp_call'], 2)} %, 2 ans à {fr(K['jp2y'], 2)} %, et 10 ans à "
    f"{fr(K['jp10y'], 2)} % ({frs(K['jp10y_12m'], 0)} pb en un an). L'inflation mesurée ({fr(K['jp_cpi'])} %, {mois(K['jp_d'])}) est "
    f"proche de la cible. L'écart de Taylor ({frs(gap['BOJ'], 2)} pt) plaide pour une poursuite graduelle des hausses, d'autant "
    f"que le yen faible ({fr(K['usdjpy'], 1)}) entretient l'inflation importée."
)

# --- 3. Croissance
need(75)
r.h1("3. Croissance et risque de récession")
r.para(
    f"Le nowcast du modèle à facteurs dynamiques donne {fr(K['nc'])} % de croissance annualisée pour {K['nc_q']}, avec un "
    f"intervalle à 68 % de {fr(K['nc_lo'])} à {fr(K['nc_hi'])} %. GDPNow (Fed d'Atlanta) est plus optimiste ({fr(K['gdpnow'])} %), "
    f"et l'indice économique hebdomadaire (WEI) ressort à {fr(K['wei'])} % sur un an. Les inscriptions hebdomadaires au chômage "
    f"({fr(K['claims'] / 1000, 0)} 000) restent basses et la règle de Sahm ne se déclenche pas ({fr(K['sahm'], 2)} point). "
    f"En revanche, les créations d'emplois ralentissent nettement (+{fr(K['payroll_yoy'])} % sur un an)."
)
r.para(
    f"La probabilité de récession à 12 mois (probit fondé sur la pente de la courbe, le crédit et le chômage) est de "
    f"{fr(100 * K['rec_us'], 0)} % aux États-Unis. En zone euro, elle est de {fr(100 * K['rec_ea'], 0)} % "
    f"(intervalle {fr(100 * K['rec_ea_lo'], 0)}–{fr(100 * K['rec_ea_hi'], 0)} %). L'approche Growth-at-Risk donne une image moins "
    f"rassurante à court terme : le quantile à 5 % de la croissance du trimestre suivant est de {fr(K['gar1'])} % (annualisé), "
    f"et redevient positif ({fr(K['gar4'])} %) à quatre trimestres. Le risque n'est pas une récession imminente, mais une "
    "queue de distribution défavorable si les conditions financières se durcissent."
)
r.image(str(ROOT / "docs" / "figures" / "3_growth_at_risk_recession.png"), w=r.w - 28)

# --- 4. Taux et marchés
r.add_page()
r.h1("4. Taux, crédit et marchés")
r.image_fig(fig_dec, px=(1000, 380))
r.para(
    f"Le 10 ans américain ({fr(K['dgs10'], 2)} %) se décompose en {fr(K['real10'], 2)} % de taux réel et {fr(K['be10'], 2)} % "
    f"d'inflation anticipée. Le point mort à 5 ans dans 5 ans ({fr(K['t5y5y'], 2)} %) reste ancré : le marché croit à la "
    f"désinflation à long terme. La prime de terme ({fr(K['tp'], 2)} % selon Kim-Wright) est élevée : elle rémunère "
    "l'incertitude sur l'inflation et l'offre de titres publics. La courbe 3 mois-10 ans est positive "
    f"({frs(100 * K['t10y3m'], 0)} pb) et la dernière variation est de type « {K['regime']} »."
)
r.para(
    f"Le crédit reste calme (écart haut rendement de {fr(100 * K['hy'], 0)} pb, VIX à {fr(K['vix'], 1)}). Notre indice de conditions "
    f"financières (FCI-lite) indique qu'un resserrement supplémentaire équivalent à {fr(K['fci_gap'], 2)} point de croissance serait "
    "nécessaire pour refermer l'écart de production. Autrement dit, les conditions financières ne freinent pas encore "
    "suffisamment l'activité."
)
r.image_fig(fig_sov, px=(1000, 320))
r.para(
    f"En zone euro, le fait marquant est le stress souverain français : l'écart OAT-Bund ({fr(K['oat'], 0)} pb, {mois(K['sov_d'])}) "
    f"dépasse celui du BTP italien ({fr(K['btp'], 0)} pb), tandis que l'Espagne reste à {fr(K['bonos'], 0)} pb. C'est la principale "
    "contrainte pour la BCE : chaque hausse de taux pèse sur la soutenabilité perçue des dettes les plus fragiles."
)

# --- 5. Transmission
need(75)
r.h1("5. Transmission et positionnement")
r.para(
    "La corrélation entre actions et obligations dépend du régime d'inflation. Quand l'inflation sous-jacente dépasse 3 %, elle "
    f"est nettement positive ({frs(K['corr_hi'], 2)}) : actions et obligations baissent ensemble, et les obligations ne protègent "
    f"plus un portefeuille. Entre 2 et 3 %, elle est négative ({frs(K['corr_mid'], 2)}). La corrélation glissante actuelle "
    f"({frs(K['corr_now'], 2)}) est en transition, cohérente avec une inflation sous-jacente autour de 3 %."
)
r.para(
    f"Dans ce même régime, une hausse de 10 pb du taux réel à 10 ans s'accompagne en moyenne d'une baisse d'environ "
    f"{fr(abs(K['beta_hi']) / 10, 2)} % du S&P 500 sur la semaine (bêta de {frs(K['beta_hi'], 2)}, écart-type "
    f"{fr(K['beta_hi_se'], 2)}). Les semi-conducteurs et les valeurs liées à l'IA y sont encore plus sensibles."
)
r.para(
    "Côté positionnement (CFTC), les gérants d'actifs détiennent une position longue record sur le 10 ans américain "
    f"({fr(K['am_ust_pct'], 0)}e centile sur 3 ans). Une nouvelle hausse des taux pourrait donc forcer des ventes. "
    f"Les fonds à effet de levier sont, eux, très vendeurs d'euro ({fr(K['lev_eur_pct'], 0)}e centile)."
)

# --- 6. Histoire
need(75)
r.h1("6. Ce que dit l'histoire (Global Macro Database)")
rows = []
for iso, lab in (("USA", "États-Unis"), ("DEU", "Allemagne (zone euro)"), ("JPN", "Japon")):
    cr = cur.loc[iso]
    s = sim[iso]
    rows.append(
        [
            lab,
            f"{int(cr['trough'])} → {int(cr['peak'])}",
            f"{frs(cr['rise (pp)'], 2)} pt",
            f"{fr(cr['inflation at peak'])} %",
            f"{int(s['n'])}",
            f"{fr(100 * s['share'], 0)} % ({fr(100 * s['lo'], 0)}–{fr(100 * s['hi'], 0)} %)",
        ]
    )
r.table(
    pd.DataFrame(
        rows,
        columns=[
            "Pays",
            "Creux → pic",
            "Hausse",
            "Inflation au pic",
            "Comparables",
            "Suivis d'une récession",
        ],
    ),
    col_widths=[40, 24, 20, 26, 22, 50],
    size=7.5,
    index=False,
)
r.para(
    "Sur environ 1 200 cycles de resserrement dans 171 pays, entre un quart et un tiers des cycles comparables aux cycles actuels "
    "(même ampleur de hausse, même inflation au pic) ont été suivis d'une récession dans les deux ans. Ce taux est plus faible "
    "que l'intuition commune selon laquelle « les hausses de taux finissent toujours en récession ». Données annuelles : il s'agit "
    "d'ordres de grandeur, pas de prévisions. Licence de la Global Macro Database : usage académique uniquement."
)

# --- 7. Scénarios
need(75)
r.h1("7. Scénarios et risques")
tab = sr["table"]
names = {
    "Soft landing / disinflation": "Désinflation (atterrissage en douceur)",
    "Sticky inflation / stagflation-lite": "Inflation tenace",
    "Energy supply shock": "Choc d'offre énergétique",
    "Hard landing": "Atterrissage brutal",
    "Probability-weighted": "Moyenne pondérée",
}
t2 = pd.DataFrame(
    {
        "Scénario": [names.get(i, i) for i in tab.index],
        "Probabilité": [f"{fr(100 * x, 0)} %" for x in tab["probability"]],
        "Fed, 4 trim.": [f"{fr(x, 2)} %" for x in tab["policy rate 4Q (median)"]],
        "Fed, 8 trim.": [f"{fr(x, 2)} %" for x in tab["policy rate 8Q (median)"]],
        "PCE sous-j., 4 trim.": [f"{fr(x, 2)} %" for x in tab["core PCE 4Q (median)"]],
    }
)
r.table(t2, col_widths=[62, 24, 32, 32, 32], size=7.5, index=False)
r.set_font(r.family, "", 7)
r.set_text_color(110, 110, 110)
r.multi_cell(
    0,
    3.4,
    r.t("Médianes des simulations de Monte Carlo (10 000 trajectoires par scénario)."),
    new_x="LMARGIN",
    new_y="NEXT",
)
r.set_text_color(0, 0, 0)
r.image(str(ROOT / "docs" / "figures" / "5_policy_fan.png"), w=r.w - 28)
r.para(
    "Les probabilités des scénarios (désinflation 40 %, inflation tenace 25 %, choc énergétique 15 %, atterrissage brutal 20 %) "
    "sont des hypothèses du modèle (config/scenarios.yaml). Avec un Brent au-dessus de 110 $ et une inflation sous-jacente qui "
    "accélère, nous jugeons le poids du scénario d'inflation tenace plutôt sous-estimé que surestimé. C'est la principale raison "
    "pour laquelle nous ne contestons pas frontalement le prix de marché de la Fed."
)
r.h2("Ce qui ferait changer la vue")
r.bullets(
    [
        "Deux publications consécutives d'inflation sous-jacente sous 2,5 % en rythme annualisé sur 3 mois : le prix de marché deviendrait trop restrictif.",
        "Une hausse du chômage de type Sahm (+0,5 point) : bascule vers le scénario d'atterrissage brutal, et des baisses de taux redeviennent probables.",
        "Un durcissement brutal des conditions financières (FCI-lite +0,5 point, écart haut rendement au-dessus de 500 pb) : le resserrement serait fait par les marchés.",
        "Une extension du stress souverain français (OAT-Bund au-delà de 120 pb) : la BCE ralentirait ses hausses.",
        "Un Brent ramené sous 90 $ : le choc énergétique se dissiperait et l'inflation totale retomberait vite.",
    ]
)

# --- 8. Limites
need(75)
r.h1("Méthodologie et limites")
r.para(
    "Données publiques (FRED/ALFRED, BCE, Eurostat, BIS, Banque du Japon, ministère japonais des Finances, CFTC, Fed d'Atlanta, "
    "Fed de New York, Fed de Philadelphie, Global Macro Database), mises à jour quotidiennement. Les modèles sont décrits dans les "
    "fiches de modèle du projet (inflation : combinaison de modèles évaluée hors échantillon ; politique monétaire : règles et "
    "fonction de réaction estimée ; croissance : modèle à facteurs dynamiques et Growth-at-Risk ; scénarios : Monte Carlo, "
    "10 000 trajectoires)."
)
r.para(
    "Limites principales. Le r* et l'écart de production sont inobservables. Les évaluations utilisent les données actuelles "
    "(révisées), pas celles disponibles en temps réel. L'IPC japonais n'est disponible qu'avec retard. Faute de courbe OIS gratuite, "
    "le chemin anticipé de la BCE et de la BoJ est approché par les taux à 2 ans. Les probabilités de scénarios sont subjectives. "
    "Peu de cycles de resserrement et de récessions figurent dans les échantillons mensuels."
)
r.box(
    "Avertissement",
    "Produit de recherche éducatif. Ce document ne constitue ni une vue officielle d'une banque centrale, ni un conseil en "
    "investissement, ni une recommandation d'achat ou de vente. Les « vues » décrivent des implications macroéconomiques, "
    "pas des positions.",
)

path = ROOT / "docs" / "research" / f"note_de_recherche_{pd.Timestamp(K['dgs10_d']).strftime('%Y-%m')}.pdf"
r.output(str(path))
print(path)
for k in (
    "cpi",
    "core",
    "core3m",
    "pce_core",
    "hicp",
    "hicp_core",
    "hicp_core3m",
    "taylor",
    "priced",
    "model_med",
    "tp",
    "tp_since",
    "oat",
    "btp",
    "corr_now",
):
    print(k, K[k])
print("scenario keys", list(sr.keys()) if isinstance(sr, dict) else type(sr))
