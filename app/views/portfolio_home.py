"""Fund dashboard (executive summary), in French: the few numbers that matter, what the team thinks, what the
quants found, and what needs attention. Everything deep stays on the detailed pages."""

import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import footer, header, sidebar_controls, theme
from macro.config import ROOT
from portfolio_ui import SLEEVE_COLOR, SLEEVE_LABEL, bundle, by_sleeve

header(
    "Fund dashboard",
    "Synthèse de gestion : performance, risque, allocation, conclusions du comité d'investissement et de la recherche quantitative.",
)
ctl = sidebar_controls()
th = theme()
b = bundle()
cfg = b["config"]


def pct(x, d=1, sign=True):
    if x is None or pd.isna(x):
        return "—"
    return (f"{100 * x:+.{d}f} %" if sign else f"{100 * x:.{d}f} %").replace(".", ",")


def latest(folder: str) -> tuple[str, str] | None:
    files = sorted((ROOT / folder).glob("20*.md"))
    return (files[-1].stem, files[-1].read_text(encoding="utf-8")) if files else None


def section(md: str, title: str) -> str:
    """The markdown under the heading that starts with `title`, up to the next heading of the same level."""
    m = re.search(rf"^(#+) {re.escape(title)}.*?$(.*?)(?=^\1 |\Z)", md, flags=re.M | re.S)
    return m.group(2).strip() if m else ""


# ------------------------------------------------------------------ 1. the four numbers
perf = b.get("performance")
fs = b.get("forward_stress", pd.DataFrame())
breaches = int(fs["breach"].astype(bool).sum()) if not fs.empty else 0
pms = b.get("post_mortems") or []
m = b["metrics"]
c = st.columns(4)
if perf is not None and not perf.empty:
    ytd = perf.loc["year to date"]
    c[0].metric(
        "Performance YTD",
        pct(ytd.iloc[0]),
        f"{pct(ytd.iloc[0] - ytd.iloc[1])} vs 60/40",
        help="Modèle (backtest) tant que le carnet papier n'a pas démarré.",
    )
c[1].metric(
    "Drawdown maximal",
    pct(m["full model"]["max drawdown"], 0),
    f"60/40 : {pct(m['benchmark 60/40']['max drawdown'], 0)}",
    delta_color="off",
)
c[2].metric(
    "Volatilité ex ante",
    pct(b["risk"]["volatility"], 0, sign=False),
    f"60/40 : {pct(b['risk']['benchmark volatility'], 0, sign=False)}",
    delta_color="off",
)
c[3].metric(
    "Points de contrôle",
    str(breaches + len(pms) + len(b["stale"])),
    "aucun dépassement" if not (breaches + len(pms) + len(b["stale"])) else "voir ci-dessous",
    delta_color="off",
)
nav = b["paper_nav"]
st.caption(
    f"Carnet papier : {'démarré, valeur ' + format(nav.iloc[-1], '.4f') if not nav.empty else 'démarre le ' + cfg['live']['start']}. "
    "Performances issues du backtest walk-forward (2005-2026) jusqu'au démarrage : résultats hypothétiques."
)

# ------------------------------------------------------------------ 2. the book in one picture
left, right = st.columns([3, 2])
with left:
    st.subheader("Allocation par classe d'actifs")
    w = b["target"][b["target"].abs() > 1e-4]
    s = by_sleeve(b, w)
    bench = by_sleeve(b, b["w_eq"][b["w_eq"].abs() > 1e-6]).reindex(s.index).fillna(0)
    fig = go.Figure()
    fig.add_bar(
        y=[SLEEVE_LABEL.get(k, k) for k in s.index],
        x=s.values,
        orientation="h",
        name="Fonds",
        marker_color=[SLEEVE_COLOR.get(k, "#888") for k in s.index],
        text=[pct(v, 0, sign=False) for v in s.values],
        textposition="outside",
    )
    fig.add_scatter(
        y=[SLEEVE_LABEL.get(k, k) for k in s.index],
        x=bench.values,
        mode="markers",
        name="Benchmark 60/40",
        marker=dict(symbol="line-ns", size=18, line=dict(width=3, color="#333")),
    )
    fig.update_layout(
        height=60 + 34 * len(s),
        margin=dict(l=0, r=40, t=10, b=0),
        showlegend=True,
        legend=dict(orientation="h", y=-0.15),
        xaxis_tickformat=".0%",
    )
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
with right:
    st.subheader("Principales expositions")
    top = w.sort_values(ascending=False)
    rows = pd.concat([top.head(6), top[top < 0].sort_values().head(3)])
    for a, v in rows.items():
        st.markdown(
            f"{'Long' if v > 0 else 'Short'} · **{cfg['universe'].get(a, {}).get('name', a)}** — {pct(abs(v), 1, sign=False)}"
        )
    st.caption("Repère noir : pondération du benchmark 60/40 ACWI/AGG.")

# ------------------------------------------------------------------ 3. attention
if breaches or pms or b["stale"]:
    st.subheader("Points de contrôle du risque")
    for k, r in fs[fs["breach"].astype(bool)].iterrows():
        st.warning(
            f"**Scénario « {k} »** : perte estimée {pct(r['book'], 1)} de la VL, limite dépassée ({r['breach']})."
        )
    for pm in pms:
        st.warning(
            f"**{cfg['universe'].get(pm['asset'], {}).get('name', pm['asset'])}** contribution de {pct(pm['loss'], 1)} de la VL sur 4 semaines (revue de perte ouverte) — {pm['verdict']}."
        )
    if b["stale"]:
        st.error(f"Prix non mis à jour : {', '.join(b['stale'])} (rééquilibrage gelé).")

# ------------------------------------------------------------------ 4. the team
st.subheader("Comité d'investissement")
acts = b.get("committee_actions") or {}
cv = b.get("committee_views")
imp = b.get("committee_impact")
conf = b.get("committee_confidence")
cc = st.columns(3)
cc[0].metric(
    "Poids du comité dans le modèle",
    pct(conf, 0, sign=False) if conf is not None else "—",
    help="5 % au départ ; jusqu'à 15 % si ses décisions notées battent le hasard, 0 % sinon (H52).",
)
cc[1].metric("Vues du comité en vigueur", str(len(cv)) if cv is not None else "0")
cc[2].metric(
    "Budget de risque",
    pct(acts.get("derisk", 1.0), 0, sign=False),
    "réduit par le comité" if acts.get("derisk", 1.0) < 1 else "normal",
    delta_color="off",
)
for r in acts.get("rows", []):
    what = (
        f"réduction du risque à {100 * float(r['scale']):.0f} %"
        if r["action"] == "derisk"
        else f"gel de {cfg['universe'].get(r['target'], {}).get('name', r['target'])}"
    )
    st.warning(
        f"**Action du comité** ({r['date']:%d/%m} → {r['expires']:%d/%m}) : {what}. Motif : {r['reason']}"
    )
if imp is not None and not imp.empty:
    with st.expander("Ce que les décisions du comité changent dans le portefeuille"):
        view = imp.copy()
        view.index = [cfg["universe"].get(a, {}).get("name", a) for a in view.index]
        st.dataframe(view.style.format("{:+.2%}"), use_container_width=True)
        st.caption("Poids avec les vues du comité, comparés aux poids que le modèle choisirait sans elles.")
note = latest("docs/research/daily")
if note:
    day, md = note
    essentials = section(md, "L'essentiel")
    st.markdown(f"**Synthèse du CIO — comité du {pd.Timestamp(day):%d/%m/%Y}**")
    st.markdown(essentials or md[:2500])
    with st.expander("Procès-verbal et notes complètes"):
        st.markdown(md)
else:
    st.info("Aucune note de comité publiée.")
desk_readme = ROOT / "docs" / "research" / "desk" / "README.md"
if desk_readme.exists():
    debate = desk_readme.read_text(encoding="utf-8").partition("## Points à débattre")[2]
    pts = [x[2:] for x in debate.splitlines() if x.startswith("- ")]
    if pts:
        with st.expander(f"Ordre du jour du prochain comité ({len(pts)} points remontés par le desk)"):
            st.markdown("\n".join(f"- {p}" for p in pts[:15]))
st.caption(
    "Comité des analystes chaque nuit à 23 h 41 (Zurich) ; le desk GitHub met ses notes à jour trois fois par jour."
)

# ------------------------------------------------------------------ 5. the quants
st.subheader("Recherche quantitative")
lab = latest("docs/research/quant")
if lab:
    day, md = lab
    verdicts = [x[2:] for x in md.splitlines() if x.startswith("- **H")]
    st.markdown(
        f"**Laboratoire du {pd.Timestamp(day):%d/%m/%Y}** — {len(verdicts)} hypothèses pré-enregistrées, walk-forward 2005-2026, net de coûts."
    )
    ok = [v for v in verdicts if "confirmée" in v or "supported" in v]
    ko = [v for v in verdicts if "rejetée" in v]
    c = st.columns(2)
    c[0].markdown(
        "**Hypothèses validées**\n\n" + ("\n".join(f"- {v.split(':')[0]}" for v in ok) or "- aucune")
    )
    c[1].markdown(
        "**Hypothèses rejetées**\n\n" + ("\n".join(f"- {v.split(':')[0]}" for v in ko) or "- aucune")
    )
    with st.expander("Résultats détaillés"):
        st.markdown("\n".join(f"- {v}" for v in verdicts))
else:
    st.info("Laboratoire hebdomadaire (samedi) ; aucun résultat publié.")
dsr = b["deflated_sharpe"]
st.markdown(
    f"**Lecture** : drawdown historique environ deux fois inférieur au benchmark ; le deflated Sharpe ({dsr:.2f}, seuil 0,95) "
    "ne permet pas de conclure à un alpha statistiquement significatif. Le track record papier, sur plusieurs années, est le juge."
)
footer()
