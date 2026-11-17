"""The GitHub desk: computed analyst notes, written at every refresh without any AI tokens.

Each member of the team (config/team.yaml) whose work can be computed has a function here that
reads the data store and the portfolio bundle and returns a Note: findings with figures, a computed
stance on each instrument it covers (the sign agreement of the model's view families, never an
opinion), its confidence (the share of families that agree), and what would change it. The nightly
Claude committee reads these notes, debates them and adds what code cannot do (reading new
publications, judging events).

Coverage is the whole universe of config/portfolio.yaml, held or not, so each analyst covers their
whole market, not only the book."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

import numpy as np
import pandas as pd

COVERAGE = {
    "us-equity-analyst": ["SPY", "RSP", "QUAL", "USMV", "VLUE", "MTUM", "XLE", "XLU", "XLV", "XLF", "ITA"],
    "europe-analyst": ["VGK", "FXE", "FXF", "BWX"],
    "japan-asia-analyst": ["EWJ", "EWT", "EWY", "FXY"],
    "emerging-markets-analyst": ["EEM", "MCHI", "INDA", "EWZ", "EMB", "EMLC"],
    "semis-tech-analyst": ["SOXX", "HYNIX", "SAMSUNG", "MU", "TSM", "NVDA", "ASML"],
    "energy-commodities-analyst": ["BNO", "XLE", "DBC", "GLD", "CPER"],
    "oil-gas-analyst": ["BNO", "XLE"],
    "metals-analyst": ["GLD", "SLV", "CPER"],
    "financials-analyst": ["XLF", "VNQ", "LQD"],
    "defense-industrials-analyst": ["ITA", "IGF", "CPER"],
    "rates-credit-analyst": ["SHY", "IEF", "TLT", "TIP", "AGG", "BWX", "LQD", "HYG"],
    "high-yield-credit-analyst": ["HYG", "LQD"],
    "em-debt-analyst": ["EMB", "EMLC"],
    "fx-strategist": ["UUP", "FXY", "FXE", "FXF"],
}


@dataclass
class Note:
    agent: str
    task: str
    summary: str
    findings: list[str] = field(default_factory=list)
    table: pd.DataFrame | None = None
    watch: list[str] = field(default_factory=list)


@dataclass
class Context:
    b: dict  # portfolio bundle
    get: Callable[[str], pd.Series | None]  # data store
    px: pd.DataFrame  # daily USD prices of the universe

    @property
    def cfg(self) -> dict:
        return self.b["config"]

    def name(self, a: str) -> str:
        return self.cfg["universe"].get(a, {}).get("name", a)


def pct(x: float, d: int = 1) -> str:
    return "n.d." if x is None or not np.isfinite(x) else f"{100 * x:+.{d}f} %".replace(".", ",")


def _last(s: pd.Series | None) -> tuple[float, pd.Timestamp] | None:
    if s is None or s.dropna().empty:
        return None
    s = s.dropna()
    return float(s.iloc[-1]), s.index[-1]


def _chg(s: pd.Series | None, days: int) -> float:
    if s is None or len(s.dropna()) <= days:
        return np.nan
    s = s.dropna()
    return float(s.iloc[-1] - s.iloc[-1 - days])


def house_consensus(b: dict, asset: str, max_age_days: int = 180) -> tuple[float, int]:
    """Average stance of the dated house views still alive, and their number."""
    t = pd.Timestamp(b["as_of"])
    st = [
        float(v["stances"][asset])
        for v in b.get("house_views", [])
        if asset in v.get("stances", {}) and (t - pd.Timestamp(v["date"])).days <= max_age_days
    ]
    return (float(np.mean(st)) if st else np.nan), len(st)


def coverage_table(ctx: Context, assets: list[str]) -> pd.DataFrame:
    """Per instrument: returns, drawdown, volatility, family scores, the computed stance and the book."""
    b = ctx.b
    views = pd.DataFrame(b["views"])
    w, weq = b["target"], b["w_eq"]
    tilt = (b["mu"] - b["pi"]) if "mu" in b else pd.Series(dtype=float)
    rows = {}
    for a in assets:
        if a not in ctx.px:
            continue
        s = ctx.px[a].dropna()
        if len(s) < 30:
            continue
        r = s.pct_change().dropna()
        fam = views.loc[a].dropna() if a in views.index else pd.Series(dtype=float)
        fam = fam[fam.abs() > 1e-9]
        sign = np.sign(fam.mean()) if len(fam) else 0.0
        agree = float((np.sign(fam) == sign).mean()) if len(fam) and sign != 0 else 0.0
        hc, hn = house_consensus(b, a)
        rows[a] = {
            "name": ctx.name(a),
            "1 month": s.iloc[-1] / s.iloc[-min(22, len(s))] - 1,
            "3 months": s.iloc[-1] / s.iloc[-min(63, len(s))] - 1,
            "12 months": s.iloc[-1] / s.iloc[-min(252, len(s))] - 1,
            "from 1y high": s.iloc[-1] / s.iloc[-252:].max() - 1,
            "vol 3m": r.iloc[-63:].std() * np.sqrt(252),
            "families": ", ".join(f"{k} {v:+.1f}" for k, v in fam.round(2).items()),
            "model tilt (pp/yr)": 100 * float(tilt.get(a, np.nan)),
            "stance": {1.0: "positive", -1.0: "negative"}.get(float(sign), "neutral"),
            "agreement": agree,
            "house views": hc,
            "n views": hn,
            "weight": float(w.get(a, 0.0)),
            "vs benchmark": float(w.get(a, 0.0) - weq.get(a, 0.0)),
        }
    return pd.DataFrame(rows).T


def _coverage_note(ctx: Context, agent: str, title: str) -> Note:
    t = coverage_table(ctx, COVERAGE[agent])
    if t.empty:
        return Note(agent, title, "Pas de données pour la couverture.")
    t = t.sort_values("model tilt (pp/yr)", ascending=False)
    best, worst = t.index[0], t.index[-1]
    f = []
    for _, r in t.iterrows():
        hv = (
            ""
            if not np.isfinite(r["house views"])
            else f" ; vues publiées {r['house views']:+.1f} ({r['n views']})"
        )
        f.append(
            f"{r['name']} : 1 mois {pct(r['1 month'])}, 12 mois {pct(r['12 months'])}, {pct(r['from 1y high'], 0)} "
            f"du plus haut, vol {100 * r['vol 3m']:.0f} % ; familles {r['families'] or 'aucune'} → **{r['stance']}** "
            f"(accord {100 * r['agreement']:.0f} %){hv} ; poids {pct(r['weight'])} ({pct(r['vs benchmark'])} vs 60/40)."
        )
    conflict = t[
        np.isfinite(t["house views"].astype(float))
        & (np.sign(t["house views"].astype(float)) * np.sign(t["model tilt (pp/yr)"].astype(float)) < 0)
    ]
    watch = [
        f"{r['name']} : nos signaux ({r['stance']}) contredisent les vues publiées ({r['house views']:+.1f}) — à débattre."
        for _, r in conflict.iterrows()
    ]
    summary = (
        f"Préféré : {t.loc[best, 'name']} ({t.loc[best, 'model tilt (pp/yr)']:+.1f} pt/an) ; "
        f"le moins attractif : {t.loc[worst, 'name']} ({t.loc[worst, 'model tilt (pp/yr)']:+.1f} pt/an)."
        + (f" {len(conflict)} désaccord(s) avec les vues publiées." if len(conflict) else "")
    )
    return Note(agent, title, summary, f, t, watch)


# ---------------------------------------------------------------------------- macro desk
def macro_strategist(ctx: Context) -> Note:
    from macro import portfolio as pf

    f, watch = [], []
    reg = pf.regime_series(ctx.get("INDPRO"), ctx.get("CPIAUCSL")).dropna()
    if not reg.empty:
        since = reg[reg != reg.iloc[-1]].index[-1] if (reg != reg.iloc[-1]).any() else reg.index[0]
        f.append(f"Régime croissance/inflation : **{reg.iloc[-1]}** depuis {since:%m/%Y}.")
    mf = ctx.b.get("macro_now")
    if mf is not None and len(mf):
        f.append(
            "Facteurs macro du modèle (−1 à +1) : " + ", ".join(f"{k} {v:+.2f}" for k, v in mf.items()) + "."
        )
        hist = ctx.b.get("macro_history")
        if hist is not None and len(hist) > 13:
            d = hist.iloc[-1] - hist.iloc[-14]
            f.append("Variation sur 3 mois : " + ", ".join(f"{k} {v:+.2f}" for k, v in d.items()) + ".")
    for sid, lab, unit in (
        ("DGS10", "10 ans US", "%"),
        ("DFII10", "10 ans réel", "%"),
        ("T10Y2Y", "pente 10-2 ans", "pt"),
        ("BAMLH0A0HYM2", "spread HY", "pt"),
        ("VIXCLS", "VIX", ""),
        ("DTWEXBGS", "dollar large", ""),
    ):
        x = _last(ctx.get(sid))
        if x:
            f.append(
                f"{lab} : {x[0]:.2f}{unit} ({_chg(ctx.get(sid), 22):+.2f} sur un mois, au {x[1]:%d/%m})."
            )
    stress = ctx.b.get("hedge_now", {}).get("VIX")
    if stress and stress > 25:
        watch.append(
            f"VIX à {stress:.0f} : régime de stress, surveiller les corrélations actions-obligations."
        )
    summary = f"Régime {reg.iloc[-1] if not reg.empty else 'n.d.'} ; " + (
        ", ".join(f"{k} {v:+.2f}" for k, v in mf.items()) if mf is not None and len(mf) else "facteurs n.d."
    )
    return Note(
        "macro-strategist", "Régime macro mondial et facteurs (calcul GitHub)", summary, f, None, watch
    )


def us_economist(ctx: Context) -> Note:
    from macro import pipeline as pipe

    f, watch = [], []
    try:
        g = pipe.growth_bundle()
        nc = g["nowcast"]
        f.append(
            f"Nowcast du PIB ({nc['target']}) : {nc['point']:.1f} % annualisé (68 % : {nc['lo68']:.1f} à {nc['hi68']:.1f})."
        )
        f.append(f"Probabilité de récession à 12 mois (probit) : {100 * float(g['recession'].value):.0f} %.")
    except Exception as exc:  # noqa: BLE001
        f.append(f"Nowcast indisponible ({type(exc).__name__}).")
    for sid, lab, yoy in (
        ("CPIAUCSL", "CPI", True),
        ("CPILFESL", "CPI core", True),
        ("PCEPILFE", "PCE core", True),
        ("UNRATE", "chômage", False),
        ("PAYEMS", "emplois non agricoles (k)", False),
        ("ICSA", "inscriptions hebdo au chômage", False),
    ):
        s = ctx.get(sid)
        if s is None or len(s.dropna()) < 14:
            continue
        s = s.dropna()
        if yoy:
            y = s.iloc[-1] / s.iloc[-13] - 1
            m3 = (s.iloc[-1] / s.iloc[-4]) ** 4 - 1
            f.append(f"{lab} : {pct(y)} sur un an, {pct(m3)} annualisé sur 3 mois ({s.index[-1]:%m/%Y}).")
            if m3 > y + 0.005:
                watch.append(f"{lab} réaccélère (3 mois {pct(m3)} > 12 mois {pct(y)}).")
        elif sid == "PAYEMS":
            f.append(
                f"{lab} : {s.iloc[-1] - s.iloc[-2]:+.0f} le dernier mois, {(s.iloc[-1] - s.iloc[-4]) / 3:+.0f} en moyenne sur 3 mois."
            )
        elif sid == "UNRATE":
            sahm = s.rolling(3).mean().iloc[-1] - s.rolling(3).mean().iloc[-13:].min()
            f.append(f"{lab} : {s.iloc[-1]:.1f} % ; indicateur de Sahm {sahm:+.2f} pt (signal à 0,50).")
            if sahm >= 0.5:
                watch.append("Règle de Sahm déclenchée.")
        else:
            f.append(f"{lab} : {s.iloc[-1]:,.0f} (moyenne 4 semaines {s.iloc[-4:].mean():,.0f}).")
    return Note(
        "us-economist",
        "Activité, emploi et inflation US (calcul GitHub)",
        f[0] if f else "n.d.",
        f,
        None,
        watch,
    )


def central_bank_watcher(ctx: Context) -> Note:
    f, watch = [], []
    dff, fp12 = _last(ctx.get("DFF")), _last(ctx.get("FED_PRICED_12M"))
    if dff:
        f.append(f"Fed funds effectif : {dff[0]:.2f} %.")
    if dff and fp12:
        d = fp12[0] - dff[0]
        f.append(
            f"Taux attendu par le marché à 12 mois : {fp12[0]:.2f} % ({100 * d:+.0f} pb vs aujourd'hui)."
        )
        ch = _chg(ctx.get("FED_PRICED_12M"), 22)
        if np.isfinite(ch):
            f.append(f"Repricing sur un mois : {100 * ch:+.0f} pb.")
            if abs(ch) > 0.25:
                watch.append(f"Repricing Fed de {100 * ch:+.0f} pb en un mois.")
    for sid, lab in (
        ("EA_DFR", "BCE dépôt"),
        ("JP_POLICY", "BoJ (taux directeur)"),
        ("SOFR", "SOFR"),
        ("EA_ESTR", "€STR"),
    ):
        x = _last(ctx.get(sid))
        if x:
            f.append(f"{lab} : {x[0]:.2f} % au {x[1]:%d/%m}.")
    return Note(
        "central-bank-watcher",
        "Banques centrales : prix de marché vs taux (calcul GitHub)",
        f[0] if f else "n.d.",
        f,
        None,
        watch,
    )


# ---------------------------------------------------------------------------- quant desk
def quant_researcher(ctx: Context) -> Note:
    b = ctx.b
    m = b["metrics"]
    full, bench = m["full model"], m["benchmark 60/40"]
    f = [
        f"Backtest : {pct(full['annual return'])}/an, drawdown max {pct(full['max drawdown'])} (60/40 {pct(bench['max drawdown'])}), "
        f"Sharpe {full['Sharpe']:.2f} vs {bench['Sharpe']:.2f}.",
        f"Deflated Sharpe {b['deflated_sharpe']:.2f} sur {b['trials']} configurations (< 0,95 : pas de preuve d'alpha au-delà de la chance).",
    ]
    for k, v in b["tests"].items():
        if v.get("n", 0) >= 8:
            f.append(f"{k} : IC {v['IC']:+.2f}, t = {v['t']:+.1f}, n = {v['n']}.")
    for k in m.columns:
        if k in ("full model", "benchmark 60/40"):
            continue
        f.append(f"Variante {k} : Sharpe {m[k]['Sharpe']:.2f}, drawdown {pct(m[k]['max drawdown'])}.")
    watch = (
        ["Deflated Sharpe sous 0,5 : rester prudent sur les tailles."] if b["deflated_sharpe"] < 0.5 else []
    )
    return Note(
        "quant-researcher",
        "Robustesse du modèle et tests pré-enregistrés (calcul GitHub)",
        f[1],
        f,
        None,
        watch,
    )


def signals_researcher(ctx: Context) -> Note:
    vc = ctx.b["view_contribution"]
    views = pd.DataFrame(ctx.b["views"])
    f = []
    mag = (100 * vc.abs().sum()).sort_values(ascending=False)
    f.append(
        "Poids de chaque famille dans les rendements attendus (somme des |contributions|, pt/an) : "
        + ", ".join(f"{k} {v:.1f}" for k, v in mag.items())
        + "."
    )
    for fam in views.columns:
        s = views[fam].dropna()
        if len(s):
            f.append(
                f"{fam} : {len(s)} instruments notés, moyenne {s.mean():+.2f}, top {s.idxmax()} {s.max():+.2f}, bas {s.idxmin()} {s.min():+.2f}."
            )
    c = views.corr(min_periods=5)
    pairs = [
        (a, b_, c.loc[a, b_])
        for i, a in enumerate(c.columns)
        for b_ in c.columns[i + 1 :]
        if np.isfinite(c.loc[a, b_])
    ]
    pairs.sort(key=lambda x: x[2])
    if pairs:
        f.append(
            f"Familles les plus opposées aujourd'hui : {pairs[0][0]} et {pairs[0][1]} (corrélation {pairs[0][2]:+.2f})."
        )
    return Note(
        "signals-researcher", "Contribution et cohérence des familles de signaux (calcul GitHub)", f[0], f
    )


def portfolio_construction_quant(ctx: Context) -> Note:
    b, cfg = ctx.b, ctx.cfg
    w = b["target"]
    at_bound = [
        a
        for a in w.index
        if a in cfg["universe"]
        and (
            np.isclose(w[a], cfg["universe"][a].get("max", 9))
            or (abs(w[a]) > 1e-6 and np.isclose(w[a], cfg["universe"][a].get("min", -9)))
        )
    ]
    tr = b["trades"]
    f = [
        f"Statut de l'optimiseur : {b['target_status']}.",
        f"Brut {pct(b['gross'], 0)} (plafond {pct(cfg['sleeves']['gross_max'], 0)}), actions nettes {pct(b['net_equity'], 0)}, {int((w.abs() > 1e-4).sum())} lignes, {int((w < -1e-4).sum())} shorts.",
        f"Positions à leur borne : {', '.join(at_bound) or 'aucune'}.",
        f"Rotation au prochain rééquilibrage : {pct(float(tr['trade'].abs().sum()) / 2 if not tr.empty else 0)} de la VL.",
    ]
    watch = [f"Contrainte relâchée : {b['target_status']}."] if b["target_status"] not in ("optimal",) else []
    return Note(
        "portfolio-construction-quant",
        "Construction : contraintes, brut, rotation (calcul GitHub)",
        f[0] + " " + f[1],
        f,
        None,
        watch,
    )


def risk_manager(ctx: Context) -> Note:
    b = ctx.b
    r = b["risk"]
    rc = (
        r["risk contribution"].sort_values(ascending=False)
        if isinstance(r["risk contribution"], pd.Series)
        else pd.Series(dtype=float)
    )
    f = [
        f"Volatilité ex ante {pct(r['volatility'])} (60/40 {pct(r['benchmark volatility'])}), tracking error {pct(r['tracking error'])}.",
        f"VaR 95 % à 1 semaine {pct(r['VaR 95% (1 week)'])}, expected shortfall {pct(r['expected shortfall 95% (1 week)'])}.",
        "Plus grosses contributions au risque : "
        + ", ".join(f"{ctx.name(a)} {pct(v, 0)}" for a, v in rc.head(5).items())
        + ".",
        f"Drawdown du carnet papier {pct(b['paper_drawdown'])} ; overlay niveau {b['overlay_state']}.",
    ]
    fs = b.get("forward_stress", pd.DataFrame())
    watch = (
        [
            f"Stress « {k} » hors limite : {pct(v['book'])} ({v['breach']})."
            for k, v in fs[fs["breach"].astype(bool)].iterrows()
        ]
        if not fs.empty
        else []
    )
    if b["stale"]:
        watch.append(f"Prix périmés : {', '.join(b['stale'])}.")
    return Note("risk-manager", "Risque du livre (calcul GitHub)", f[0], f, None, watch)


def stress_testing_analyst(ctx: Context) -> Note:
    fs = ctx.b.get("forward_stress", pd.DataFrame())
    if fs.empty:
        return Note("stress-testing-analyst", "Stress tests prospectifs", "n.d.")
    fs = fs.sort_values("book")
    f = [
        f"{k} : livre {pct(v['book'])} (dont couverture {pct(v['of which tail hedge'])}), 60/40 {pct(v['benchmark'])}"
        + (f" — **{v['breach']}**" if v["breach"] else "")
        + f" ; pertes : {v['largest losses']}."
        for k, v in fs.iterrows()
    ]
    ep = ctx.b.get("episodes")
    if ep is not None and not ep.empty:
        worse = ep[ep["portfolio (current weights)"] < ep["benchmark"]]
        f.append(
            f"Crises passées rejouées : le livre actuel fait pire que le 60/40 dans {len(worse)} sur {len(ep)} ({', '.join(worse.index) or 'aucune'})."
        )
    nb = int(fs["breach"].astype(bool).sum())
    return Note(
        "stress-testing-analyst",
        "Stress tests prospectifs et crises rejouées (calcul GitHub)",
        f"Pire scénario : {fs.index[0]} ({pct(fs['book'].iloc[0])}) ; {nb} hors limite.",
        f,
    )


def execution_trading_analyst(ctx: Context) -> Note:
    tr, cfg = ctx.b["trades"], ctx.cfg
    if tr.empty:
        return Note("execution-trading-analyst", "Coûts du prochain rééquilibrage", "Aucun ordre prévu.")
    cost = sum(abs(v) * cfg["universe"].get(a, {}).get("cost_bp", 5) / 1e4 for a, v in tr["trade"].items())
    big = tr.reindex(tr["trade"].abs().sort_values(ascending=False).index).head(6)
    f = [
        f"{len(tr)} ordres papier, rotation {pct(float(tr['trade'].abs().sum()) / 2)} ; coût estimé {100 * cost:.2f} % de la VL ({1e4 * cost:.0f} pb)."
    ]
    f += [
        f"{ctx.name(a)} : {pct(r['trade'])} ({r['action']}, {cfg['universe'].get(a, {}).get('cost_bp', 5)} pb)."
        for a, r in big.iterrows()
    ]
    shorts = ctx.b["target"][ctx.b["target"] < -1e-4]
    if len(shorts):
        borrow = sum(
            abs(v) * cfg["universe"].get(a, {}).get("borrow_bp", 30) / 1e4 for a, v in shorts.items()
        )
        f.append(f"Coût d'emprunt annuel des shorts : {1e4 * borrow:.0f} pb de la VL.")
    return Note("execution-trading-analyst", "Ordres et coûts (calcul GitHub)", f[0], f)


def data_quality_engineer(ctx: Context) -> Note:
    px, f, watch = ctx.px, [], []
    last = px.apply(lambda s: s.dropna().index[-1] if s.notna().any() else pd.NaT)
    ref = last.max()
    lag = (ref - last).dt.days.sort_values(ascending=False)
    f.append(
        f"Dernière date de prix : {ref:%d/%m/%Y} ; instruments en retard de plus de 3 jours : "
        + (", ".join(f"{a} ({d} j)" for a, d in lag[lag > 3].items()) or "aucun")
        + "."
    )
    r = px.pct_change(fill_method=None).iloc[-260:]
    z = (r.iloc[-1] / r.iloc[:-1].std()).abs().sort_values(ascending=False)
    jumps = z[z > 6]
    f.append(
        "Sauts de plus de 6 écarts-types au dernier jour : "
        + (", ".join(f"{a} ({r[a].iloc[-1]:+.1%})" for a in jumps.index) or "aucun")
        + "."
    )
    if len(jumps):
        watch.append(f"Vérifier les prix : {', '.join(jumps.index)}.")
    if ctx.b["stale"]:
        watch.append(f"Rééquilibrage gelé pour prix périmés : {', '.join(ctx.b['stale'])}.")
    return Note(
        "data-quality-engineer", "Fraîcheur et anomalies des données (calcul GitHub)", f[0], f, None, watch
    )


def news_desk_analyst(ctx: Context) -> Note:
    from macro import news
    from macro import news_scoring as ns

    arch = ns.read_archive()
    if arch.empty:
        return Note("news-desk-analyst", "Pression des news", "Archive vide.")
    recent = arch[arch["first_seen"] >= arch["first_seen"].max() - pd.Timedelta(days=3)]
    a = ns.asset_scores(recent, news.load())
    a = a[a["headlines"] >= 3].sort_values("news score")
    f = [f"{len(recent)} titres notés (FinBERT) sur 3 jours."]
    f += [
        f"{ctx.name(k)} : score {r['news score']:+.2f} sur {int(r['headlines'])} titres."
        for k, r in pd.concat([a.head(3), a.tail(3)]).iterrows()
    ]
    watch = [
        f"{ctx.name(k)} : news extrêmes ({r['news score']:+.2f})."
        for k, r in a[a["news score"].abs() >= 0.6].iterrows()
    ]
    return Note("news-desk-analyst", "News notées : pression par actif (calcul GitHub)", f[0], f, None, watch)


def research_librarian(ctx: Context) -> Note:
    from macro import research_tracker as rt

    arch = rt.read_archive()
    if arch.empty:
        return Note("research-librarian", "Suivi des publications", "Archive vide.")
    col = "first_seen" if "first_seen" in arch else arch.columns[0]
    t = pd.to_datetime(arch[col], utc=True, errors="coerce")
    recent = arch[t >= t.max() - pd.Timedelta(days=3)]
    top = recent["institution"].value_counts().head(8)
    f = [
        f"{len(recent)} publications relevées sur 3 jours, {recent['institution'].nunique()} institutions.",
        "Les plus actives : " + ", ".join(f"{k} ({v})" for k, v in top.items()) + ".",
    ]
    try:
        cons = rt.consensus(arch)
        if not cons.empty:
            f.append(
                "Consensus des recommandations explicites (30 jours) : "
                + ", ".join(f"{i} {r.iloc[0]:+.2f}" for i, r in cons.head(8).iterrows())
                + "."
            )
    except Exception:  # noqa: BLE001
        pass
    alive = [
        v
        for v in ctx.b.get("house_views", [])
        if (pd.Timestamp(ctx.b["as_of"]) - pd.Timestamp(v["date"])).days <= 180
    ]
    f.append(f"Vues de maison actives dans le modèle : {len(alive)}.")
    return Note("research-librarian", "Veille des publications (calcul GitHub)", f[0], f)


def chief_investment_officer(ctx: Context, notes: list[Note]) -> Note:
    b = ctx.b
    w = b["target"][b["target"].abs() > 1e-3].sort_values(ascending=False)
    f = ["Livre : " + ", ".join(f"{ctx.name(a)} {pct(v)}" for a, v in w.head(8).items()) + "."]
    watch = [f"{n.agent} : {x}" for n in notes for x in n.watch]
    f.append(f"{len(watch)} point(s) à arbitrer au comité de ce soir.")
    return Note("chief-investment-officer", "Synthèse du desk GitHub (calcul GitHub)", f[1], f, None, watch)


ANALYSTS: dict[str, Callable[[Context], Note]] = {
    "macro-strategist": macro_strategist,
    "us-economist": us_economist,
    "central-bank-watcher": central_bank_watcher,
    "quant-researcher": quant_researcher,
    "signals-researcher": signals_researcher,
    "portfolio-construction-quant": portfolio_construction_quant,
    "risk-manager": risk_manager,
    "stress-testing-analyst": stress_testing_analyst,
    "execution-trading-analyst": execution_trading_analyst,
    "data-quality-engineer": data_quality_engineer,
    "news-desk-analyst": news_desk_analyst,
    "research-librarian": research_librarian,
}
TITLES = {
    "us-equity-analyst": "Actions US : indices, styles, secteurs",
    "europe-analyst": "Europe : actions, euro, franc, obligations",
    "japan-asia-analyst": "Japon et Asie développée",
    "emerging-markets-analyst": "Émergents : actions et dette",
    "semis-tech-analyst": "Semi-conducteurs : noms et cycle",
    "energy-commodities-analyst": "Énergie et matières premières",
    "oil-gas-analyst": "Pétrole et gaz",
    "metals-analyst": "Métaux précieux et industriels",
    "financials-analyst": "Financières et immobilier",
    "defense-industrials-analyst": "Défense et infrastructures",
    "rates-credit-analyst": "Taux et crédit",
    "high-yield-credit-analyst": "Haut rendement",
    "em-debt-analyst": "Dette émergente",
    "fx-strategist": "Changes",
}


def run(ctx: Context) -> list[Note]:
    """All computable notes; a failing analyst yields a note saying so rather than stopping the desk."""
    notes = []
    jobs: list[tuple[str, Callable[[], Note]]] = [(k, partial(fn, ctx)) for k, fn in ANALYSTS.items()]
    jobs += [(k, partial(_coverage_note, ctx, k, TITLES[k] + " (calcul GitHub)")) for k in COVERAGE]
    for agent, job in jobs:
        try:
            notes.append(job())
        except Exception as exc:  # noqa: BLE001
            notes.append(Note(agent, "Note du desk", f"Indisponible ({type(exc).__name__}: {exc})"))
    for n in notes:
        try:
            enrich(ctx, n)
        except Exception as exc:  # noqa: BLE001
            n.findings.append(f"(scan de marché indisponible : {type(exc).__name__})")
    try:
        _semis_extra(ctx, next(n for n in notes if n.agent == "semis-tech-analyst"))
        notes.append(cross_asset_scan(ctx))
    except Exception as exc:  # noqa: BLE001
        notes.append(
            Note("macro-strategist", "Tour d'horizon cross-asset", f"Indisponible ({type(exc).__name__})")
        )
    notes.append(chief_investment_officer(ctx, notes))
    return notes


def _semis_extra(ctx: Context, note: Note) -> None:
    from macro import portfolio as pf

    for co in ("MU", "NVDA"):
        rv, gp = ctx.get(f"{co}_REV"), ctx.get(f"{co}_GP")
        if rv is not None and len(rv.dropna()) >= 5:
            q = rv.dropna()
            line = f"{ctx.name(co)} (SEC) : CA {q.iloc[-1] / 1e9:.1f} Md$ au {q.index[-1]:%m/%Y}, {pct(q.iloc[-1] / q.iloc[-5] - 1, 0)} sur un an"
            if gp is not None and len(gp.dropna()) >= 2:
                m = (gp.dropna() / q).dropna()
                if len(m) >= 2:
                    line += f", marge brute {100 * m.iloc[-1]:.0f} % ({100 * m.iloc[-2]:.0f} % le trimestre précédent)"
            note.findings.append(line + ".")
    mc = pf.memory_cycle(ctx.get("MU_REV"))
    if not mc.empty:
        note.findings.append(
            f"Cycle mémoire (accélération du CA de Micron) : {100 * mc.iloc[-1]:+.1f} pt au {mc.index[-1]:%m/%Y}."
        )


def markdown(n: Note, stamp: str) -> str:
    out = [
        f"# {n.task}",
        "",
        f"*`{n.agent}` — {stamp}. Note calculée par GitHub Actions à partir des données et des modèles du dépôt : "
        "aucune opinion, les positions viennent des règles. Le comité du soir la discute.*",
        "",
        f"**En bref** : {n.summary}",
        "",
    ]
    out += [f"- {x}" for x in n.findings]
    if n.watch:
        out += ["", "**À surveiller / à débattre**", ""] + [f"- {x}" for x in n.watch]
    if n.table is not None and not n.table.empty:
        t = n.table.copy()
        for c in (
            "1 month",
            "3 months",
            "12 months",
            "from 1y high",
            "vol 3m",
            "weight",
            "vs benchmark",
            "agreement",
        ):
            if c in t:
                t[c] = t[c].map(lambda v: f"{100 * float(v):+.1f}%")
        for c in ("12-1 momentum", "5y percentile"):
            if c in t:
                t[c] = t[c].map(lambda v: "" if not np.isfinite(float(v)) else f"{100 * float(v):+.0f}%")
        for c in ("1m z", "beta SPY", "corr SPY", "corr change 3m"):
            if c in t:
                t[c] = t[c].map(lambda v: "" if not np.isfinite(float(v)) else f"{float(v):+.2f}")
        for c in ("model tilt (pp/yr)", "house views"):
            if c in t:
                t[c] = t[c].map(lambda v: "" if not np.isfinite(float(v)) else f"{float(v):+.1f}")
        cols = [c for c in t.columns if c != "families"]
        out += ["", "| " + " | ".join(["", *cols]) + " |", "|" + "---|" * (len(cols) + 1)]
        out += ["| " + " | ".join([str(a), *[str(r[c]) for c in cols]]) + " |" for a, r in t.iterrows()]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------- market-wide scans
# Series of the data store each desk reads beyond its instruments: (id or "A-B" spread, label, how).
# how: "level" (level, 1-month change, z of that change, 5-year percentile) or "yoy" (12-month % change).
EXTRAS: dict[str, list[tuple[str, str, str]]] = {
    "us-equity-analyst": [
        ("SPX", "S&P 500", "level"),
        ("SOX", "Philadelphia semis", "level"),
        ("NVDA", "Nvidia", "level"),
        ("MSFT", "Microsoft", "level"),
        ("GOOGL", "Alphabet", "level"),
        ("AMZN", "Amazon", "level"),
        ("META", "Meta", "level"),
        ("VIX", "VIX", "level"),
        ("TFF_ES_LEV", "S&P futures: leveraged funds net", "level"),
        ("TFF_ES_AM", "S&P futures: asset managers net", "level"),
    ],
    "europe-analyst": [
        ("SX5E", "Euro Stoxx 50", "level"),
        ("EURUSD", "EUR/USD", "level"),
        ("EA_HICP", "HICP", "yoy"),
        ("EA_HICP_CORE", "HICP core", "yoy"),
        ("EA_HICP_SERV", "HICP services", "yoy"),
        ("EA_UNRATE", "unemployment", "level"),
        ("EA_DFR", "ECB deposit rate", "level"),
        ("EA_YC_2Y", "euro 2Y AAA", "level"),
        ("DE_10Y", "Bund 10Y", "level"),
        ("IT_10Y-DE_10Y", "BTP-Bund spread", "level"),
        ("FR_10Y-DE_10Y", "OAT-Bund spread", "level"),
        ("ES_10Y-DE_10Y", "Bono-Bund spread", "level"),
        ("TFF_EUR_LEV", "EUR futures: leveraged funds net", "level"),
    ],
    "japan-asia-analyst": [
        ("N225", "Nikkei 225", "level"),
        ("USDJPY", "USD/JPY", "level"),
        ("USDKRW", "USD/KRW", "level"),
        ("JP_CPI", "Japan CPI", "yoy"),
        ("JP_POLICY", "BoJ policy rate", "level"),
        ("JP_2Y", "JGB 2Y", "level"),
        ("JP_10Y", "JGB 10Y", "level"),
        ("DGS10-JP_10Y", "US-Japan 10Y differential", "level"),
        ("TFF_JPY_LEV", "JPY futures: leveraged funds net", "level"),
    ],
    "emerging-markets-analyst": [
        ("USDKRW", "USD/KRW", "level"),
        ("DTWEXBGS", "broad dollar", "level"),
        ("GSCPI", "supply-chain pressure", "level"),
    ],
    "semis-tech-analyst": [
        ("SOX", "Philadelphia semis", "level"),
        ("NVDA", "Nvidia (USD)", "level"),
        ("USDKRW", "USD/KRW", "level"),
        ("NEWS_TONE_MEMORY", "memory news tone", "level"),
    ],
    "energy-commodities-analyst": [
        ("BRENT_FUT", "Brent future", "level"),
        ("DCOILBRENTEU", "Brent spot", "level"),
        ("GOLD_FUT", "gold future", "level"),
        ("CPIENGSL", "US CPI energy", "yoy"),
        ("GSCPI", "supply-chain pressure", "level"),
    ],
    "oil-gas-analyst": [
        ("BRENT_FUT", "Brent future", "level"),
        ("DCOILBRENTEU", "Brent spot", "level"),
        ("CPIENGSL", "US CPI energy", "yoy"),
    ],
    "metals-analyst": [
        ("GOLD_FUT", "gold future", "level"),
        ("DFII10", "US 10Y real yield", "level"),
        ("DTWEXBGS", "broad dollar", "level"),
    ],
    "financials-analyst": [
        ("NFCI", "Chicago Fed NFCI", "level"),
        ("STLFSI4", "St Louis financial stress", "level"),
        ("MORTGAGE30US", "30Y mortgage rate", "level"),
        ("CSUSHPISA", "Case-Shiller house prices", "yoy"),
        ("T10Y3M", "3m-10Y slope (bank margins)", "level"),
        ("EBP", "excess bond premium", "level"),
    ],
    "defense-industrials-analyst": [
        ("INDPRO", "US industrial production", "yoy"),
        ("GACDFSA066MSFRBPHI", "Philly Fed activity", "level"),
    ],
    "rates-credit-analyst": [
        ("DGS2", "UST 2Y", "level"),
        ("DGS10", "UST 10Y", "level"),
        ("DGS30", "UST 30Y", "level"),
        ("T10Y2Y", "2s10s", "level"),
        ("T10Y3M", "3m10Y", "level"),
        ("DFII10", "10Y real", "level"),
        ("T10YIE", "10Y breakeven", "level"),
        ("T5YIFR", "5y5y inflation", "level"),
        ("ACMTP10", "ACM term premium 10Y", "level"),
        ("THREEFYTP10", "Kim-Wright term premium 10Y", "level"),
        ("MOVE", "MOVE", "level"),
        ("BAMLC0A0CM", "IG OAS", "level"),
        ("BAMLH0A0HYM2", "HY OAS", "level"),
        ("EBP", "excess bond premium", "level"),
        ("TFF_UST10_LEV", "10Y futures: leveraged funds net", "level"),
        ("TFF_UST10_AM", "10Y futures: asset managers net", "level"),
    ],
    "high-yield-credit-analyst": [
        ("BAMLH0A0HYM2", "HY OAS", "level"),
        ("BAMLC0A0CM", "IG OAS", "level"),
        ("BAMLH0A0HYM2-BAMLC0A0CM", "HY-IG", "level"),
        ("GZ_SPREAD", "Gilchrist-Zakrajsek spread", "level"),
        ("EBP", "excess bond premium", "level"),
        ("EBP_PROB", "EBP recession probability", "level"),
    ],
    "em-debt-analyst": [
        ("DTWEXBGS", "broad dollar", "level"),
        ("DGS10", "UST 10Y", "level"),
        ("BAMLH0A0HYM2", "US HY OAS (risk appetite)", "level"),
    ],
    "fx-strategist": [
        ("DXY", "DXY", "level"),
        ("DTWEXBGS", "broad dollar", "level"),
        ("EURUSD", "EUR/USD", "level"),
        ("USDJPY", "USD/JPY", "level"),
        ("USDKRW", "USD/KRW", "level"),
        ("DGS2-EA_YC_2Y", "US-euro 2Y differential", "level"),
        ("DGS2-JP_2Y", "US-Japan 2Y differential", "level"),
        ("TFF_EUR_LEV", "EUR futures: leveraged net", "level"),
        ("TFF_JPY_LEV", "JPY futures: leveraged net", "level"),
    ],
}


def series_of(get: Callable[[str], pd.Series | None], sid: str) -> pd.Series | None:
    if "-" in sid and not sid.startswith("-"):
        a, b = sid.split("-", 1)
        sa, sb = get(a), get(b)
        if sa is None or sb is None:
            return None
        return (sa.dropna() - sb.dropna().reindex(sa.dropna().index, method="ffill")).dropna()
    return get(sid)


def scan_line(s: pd.Series | None, label: str, how: str) -> tuple[str, float] | None:
    """One line per series: level, 1-month change, z-score of that change against three years of
    1-month changes, and percentile of the level over five years. Returns the line and |z|."""
    if s is None or len(s.dropna()) < 30:
        return None
    s = s.dropna()
    span = (s.index[-1] - s.index[0]).days / max(len(s) - 1, 1)
    step = max(int(round(30 / max(span, 1e-9))), 1)  # observations in a month
    if how == "yoy":
        yr = max(int(round(365 / max(span, 1e-9))), 1)
        if len(s) <= yr + 3:
            return None
        y = s / s.shift(yr) - 1
        return (
            f"{label} : {pct(y.iloc[-1])} sur un an (précédent {pct(y.iloc[-1 - step] if len(y) > step else np.nan)}, au {s.index[-1]:%m/%Y}).",
            0.0,
        )
    d = s.diff(step)
    hist = d.loc[s.index[-1] - pd.Timedelta(days=3 * 365) :].dropna()
    z = (d.iloc[-1] - hist.mean()) / hist.std() if len(hist) > 10 and hist.std() > 0 else np.nan
    w5 = s.loc[s.index[-1] - pd.Timedelta(days=5 * 365) :]
    pc = float((w5 <= s.iloc[-1]).mean())
    big = abs(s.iloc[-1]) >= 50
    lvl = f"{s.iloc[-1]:,.0f}" if big else f"{s.iloc[-1]:.2f}"
    ch = f"{d.iloc[-1]:+,.0f}" if big else f"{d.iloc[-1]:+.2f}"
    flag = " ⚠" if np.isfinite(z) and abs(z) >= 2 else ""
    return (
        f"{label} : {lvl} ({ch} sur un mois, z {z:+.1f} ; percentile 5 ans {100 * pc:.0f} %){flag}.",
        abs(z) if np.isfinite(z) else 0.0,
    )


def senior_metrics(ctx: Context, assets: list[str]) -> pd.DataFrame:
    """12-1 momentum, z-score of the 1-month return, 5-year price percentile, beta and correlation to
    the S&P 500 (3 years) and the change of that correlation over the last 3 months."""
    px = ctx.px
    out = {}
    spy = px["SPY"].dropna().pct_change() if "SPY" in px else None
    for a in assets:
        if a not in px or len(px[a].dropna()) < 300:
            continue
        s = px[a].dropna()
        r = s.pct_change().dropna()
        m21 = s.pct_change(21)
        hist = m21.iloc[-756:].dropna()
        z = (m21.iloc[-1] - hist.mean()) / hist.std() if hist.std() > 0 else np.nan
        mom = s.iloc[-22] / s.iloc[-min(253, len(s))] - 1
        p5 = float((s.iloc[-1260:] <= s.iloc[-1]).mean())
        beta = corr = dcorr = np.nan
        if spy is not None and a != "SPY":
            j = pd.concat([r, spy], axis=1).dropna().iloc[-756:]
            if len(j) > 120:
                beta = float(j.cov().iloc[0, 1] / j.iloc[:, 1].var())
                corr = float(j.corr().iloc[0, 1])
                dcorr = float(j.iloc[-63:].corr().iloc[0, 1] - corr)
        out[a] = {
            "12-1 momentum": mom,
            "1m z": z,
            "5y percentile": p5,
            "beta SPY": beta,
            "corr SPY": corr,
            "corr change 3m": dcorr,
        }
    return pd.DataFrame(out).T


def relative_value(ctx: Context, assets: list[str]) -> str | None:
    """The pair inside a coverage with the widest gap of computed stances, with its correlation and
    the z-score of the price ratio against one year: a candidate for the committee, not a trade."""
    t = coverage_table(ctx, assets)
    t = t[np.isfinite(t["model tilt (pp/yr)"].astype(float))]
    if len(t) < 2:
        return None
    hi, lo = t["model tilt (pp/yr)"].astype(float).idxmax(), t["model tilt (pp/yr)"].astype(float).idxmin()
    px = ctx.px[[hi, lo]].dropna().iloc[-252:]
    if len(px) < 120:
        return None
    ratio = np.log(px[hi] / px[lo])
    z = (ratio.iloc[-1] - ratio.mean()) / ratio.std() if ratio.std() > 0 else np.nan
    c = float(px.pct_change().corr().iloc[0, 1])
    gap = float(t.loc[hi, "model tilt (pp/yr)"] - t.loc[lo, "model tilt (pp/yr)"])
    return (
        f"Valeur relative candidate : long {ctx.name(hi)} / short {ctx.name(lo)} — écart de vues {gap:+.1f} pt/an, "
        f"corrélation 1 an {c:+.2f}, ratio à z {z:+.1f} sur un an "
        + (
            "(le marché a déjà joué l'écart)."
            if np.isfinite(z) and z > 1.5
            else "(pas encore dans les prix)."
            if np.isfinite(z) and z < 0
            else "."
        )
    )


def enrich(ctx: Context, note: Note) -> None:
    """Add the market-wide scan, the senior metrics and a relative-value candidate to a desk note."""
    lines = []
    for sid, label, how in EXTRAS.get(note.agent, []):
        x = scan_line(series_of(ctx.get, sid), label, how)
        if x:
            lines.append(x)
            if x[1] >= 2:
                note.watch.append(f"Mouvement anormal : {x[0]}")
    if lines:
        note.findings += ["**Marché au sens large**"] + [x[0] for x in lines]
    if note.agent in COVERAGE:
        sm = senior_metrics(ctx, COVERAGE[note.agent])
        if not sm.empty and note.table is not None:
            note.table = note.table.join(sm, how="left")
            for a, r in sm.iterrows():
                if np.isfinite(r["corr change 3m"]) and abs(r["corr change 3m"]) > 0.3:
                    note.watch.append(
                        f"{ctx.name(a)} : corrélation au S&P 500 en rupture ({r['corr change 3m']:+.2f} sur 3 mois)."
                    )
                if np.isfinite(r["1m z"]) and abs(r["1m z"]) >= 2:
                    note.watch.append(f"{ctx.name(a)} : mouvement d'un mois à z {r['1m z']:+.1f}.")
        rv = relative_value(ctx, COVERAGE[note.agent])
        if rv:
            note.findings.append(rv)


def cross_asset_scan(ctx: Context) -> Note:
    """Every series of config/markets.yaml: the market-wide dashboard a senior PM reads first."""
    import yaml

    from macro.config import ROOT

    with open(ROOT / "config" / "markets.yaml", encoding="utf-8") as fh:
        assets = yaml.safe_load(fh)["assets"]
    lines = []
    for a in assets:
        x = scan_line(ctx.get(a["id"]), f"[{a['cls']}] {a['name']}", "level")
        if x:
            lines.append(x)
    lines.sort(key=lambda x: -x[1])
    f = [x[0] for x in lines]
    watch = [x[0] for x in lines if x[1] >= 2]
    return Note(
        "macro-strategist",
        "Tour d'horizon cross-asset : tous les marchés suivis (calcul GitHub)",
        f"{len(lines)} marchés ; {len(watch)} mouvement(s) d'un mois au-delà de 2 écarts-types.",
        f,
        None,
        watch,
    )
