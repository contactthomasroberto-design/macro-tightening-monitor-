"""Evening report (in French): what the fund did today, why, and what the research found.

MACRO_MODE=live python scripts/evening_report.py           # write docs/reports/daily/<date>.md
MACRO_MODE=live python scripts/evening_report.py --issue   # also open a GitHub issue (e-mailed to the owner)

Run by the refresh workflow's evening run. Compares today's target with yesterday's (snapshots in
archive/portfolio_daily/), and summarises signals, risk, news pressure, new publications of banks and
asset managers, and the state of the pre-registered tests."""

from __future__ import annotations

import argparse
import json
import subprocess

import pandas as pd

import _bootstrap  # noqa: F401
from macro import news
from macro import news_scoring as ns
from macro import research_tracker as rt
from macro.config import ROOT
from macro.pipeline import portfolio_bundle

DAILY = ROOT / "archive" / "portfolio_daily"
OUT = ROOT / "docs" / "reports" / "daily"


def pct(x: float, d: int = 1) -> str:
    return f"{100 * x:+.{d}f} %".replace(".", ",")


def snapshot(b: dict, day: str) -> dict:
    views = pd.DataFrame(b["views"]).mean(axis=1).dropna()
    snap = {
        "date": day,
        "target": {k: round(float(v), 5) for k, v in b["target"].items() if abs(v) > 1e-5},
        "views": {k: round(float(v), 3) for k, v in views.items()},
    }
    DAILY.mkdir(parents=True, exist_ok=True)
    (DAILY / f"{day}.json").write_text(json.dumps(snap, indent=1))
    return snap


def previous(day: str) -> dict | None:
    files = sorted(p for p in DAILY.glob("*.json") if p.stem < day) if DAILY.exists() else []
    return json.loads(files[-1].read_text()) if files else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", action="store_true")
    args = ap.parse_args()
    day = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    b = portfolio_bundle()
    cfg = b["config"]
    name = lambda a: cfg["universe"].get(a, {}).get("name", a)  # noqa: E731
    snap = snapshot(b, day)
    prev = previous(day)
    m, r = b["metrics"], b["risk"]
    now_utc = pd.Timestamp.now(tz="UTC")
    L: list[str] = [
        f"# Rapport du jour — {day}",
        f"*Mis à jour à {now_utc:%H:%M} UTC ; régénéré à chaque rafraîchissement, envoyé par e-mail le soir.*",
        "",
    ]

    # ---------------------------------------------------------------- the book
    L += ["## 1. Le portefeuille", ""]
    L.append(
        f"Exposition brute {100 * b['gross']:.0f} %, nette actions {100 * b['net_equity']:.0f} %, volatilité ex ante "
        f"{100 * r['volatility']:.1f} % (benchmark {100 * r['benchmark volatility']:.1f} %), tracking error "
        f"{100 * r['tracking error']:.1f} %, VaR 95 % à une semaine {100 * r['VaR 95% (1 week)']:.1f} %."
    )
    if b["overlay_state"]:
        L.append(f"**Frein de drawdown actif (niveau {b['overlay_state']})**.")
    h = b.get("hedge_now") or {}
    if h:
        L.append(
            f"Couverture optionnelle : {100 * h['hedge ratio']:.0f} % de l'exposition actions en puts S&P 500 à 5 % "
            f"hors de la monnaie (VIX {h['VIX']:.1f}, coût {100 * h['premium (% of NAV)']:.2f} % de l'actif par mois)."
        )
    t = pd.Series(snap["target"])
    longs = t[t > 0].sort_values(ascending=False).head(8)
    shorts = t[t < 0].sort_values().head(6)
    L += [
        "",
        "**Principales positions longues** : "
        + ", ".join(f"{name(a)} {100 * v:.1f} %" for a, v in longs.items()),
    ]
    if not shorts.empty:
        L.append(
            "**Positions courtes** : " + ", ".join(f"{name(a)} {100 * v:.1f} %" for a, v in shorts.items())
        )
    if prev:
        p = pd.Series(prev["target"])
        d = t.sub(p, fill_value=0)
        d = d[d.abs() >= 0.0025].sort_values(key=abs, ascending=False)
        L += ["", f"### Changements depuis le {prev['date']}"]
        if d.empty:
            L.append("Aucun changement au-delà de 0,25 point.")
        for a, v in d.head(12).items():
            L.append(f"- {name(a)} : {100 * p.get(a, 0):.1f} % → {100 * t.get(a, 0):.1f} % ({pct(v)})")
        vp, vn = pd.Series(prev.get("views", {})), pd.Series(snap["views"])
        dv = vn.sub(vp, fill_value=0)
        dv = dv[dv.abs() >= 0.15].sort_values(key=abs, ascending=False)
        if not dv.empty:
            L.append("")
            L.append(
                "Signaux qui ont le plus bougé (moyenne des familles, −1 à +1) : "
                + ", ".join(f"{name(a)} {vp.get(a, 0):+.2f} → {vn.get(a, 0):+.2f}" for a in dv.head(8).index)
            )
    else:
        L.append("Premier rapport : pas de comparaison avec la veille.")
    if b["rebalance_due"]:
        L.append(f"\nRééquilibrage papier ce soir : {b['rebalance_due']}.")

    # ---------------------------------------------------------------- models
    L += ["", "## 2. Modèles et tests", ""]
    full, bench = m["full model"], m["benchmark 60/40"]
    L.append(
        f"Backtest walk-forward depuis {b['benchmark'].index[0]:%Y} : {100 * full['annual return']:.1f} % par an, "
        f"drawdown max {100 * full['max drawdown']:.1f} % contre {100 * bench['max drawdown']:.1f} % pour le 60/40, "
        f"Sharpe {full['Sharpe']:.2f} contre {bench['Sharpe']:.2f} ; deflated Sharpe {b['deflated_sharpe']:.2f} "
        f"sur {b['trials']} configurations."
    )
    for k, v in b["tests"].items():
        if v.get("n", 0) >= 8:
            L.append(f"- {k} : IC {v['IC']:+.2f}, t = {v['t']:+.1f}, n = {v['n']}")
    L.append(f"- Poids des news dans l'allocation : {100 * b.get('news_confidence', 0):.0f} % (verrou H32).")

    # ---------------------------------------------------------------- news
    # ---------------------------------------------------------------- markets, macro, companies
    L += ["", "## 2 bis. Marchés, macro et entreprises du jour", ""]
    import datetime as dt

    from macro.data import store, try_series
    from macro.signposts import evaluate

    px = pd.DataFrame(
        {a: s.dropna() for a in cfg["universe"] if (s := try_series(a)) is not None and not s.dropna().empty}
    ).ffill()
    if len(px) > 6:
        d1 = (px.iloc[-1] / px.iloc[-2] - 1).dropna()
        d5 = (px.iloc[-1] / px.iloc[-6] - 1).dropna()
        mv = d5.reindex(d5.abs().sort_values(ascending=False).index).head(8)
        L.append(
            "Plus forts mouvements sur 5 séances (tout l'univers, détenu ou non) : "
            + ", ".join(
                f"{name(a)} {100 * v:+.1f} % (jour {100 * d1.get(a, 0):+.1f} %)" for a, v in mv.items()
            )
        )
    rel = store().recent_releases(dt.datetime.now(dt.UTC) - dt.timedelta(days=1))
    if not rel.empty:
        L.append(
            "Publications de données des dernières 24 h : "
            + ", ".join(
                f"{r_['series_id']} {r_['value']:.2f} ({r_['obs_date']})" for _, r_ in rel.head(15).iterrows()
            )
        )
    sp_ = evaluate(try_series)
    crossed = sp_[sp_["crossed"] == True]  # noqa: E712
    if not crossed.empty:
        L.append(
            "Seuils d'alerte franchis : "
            + ", ".join(f"{r_['label']} ({r_['latest']:.2f})" for _, r_ in crossed.iterrows())
        )
    for co in ("MU", "NVDA"):
        rv = try_series(f"{co}_REV")
        if rv is not None and len(rv.dropna()) >= 5:
            q = rv.dropna()
            L.append(
                f"{name(co)} : dernier chiffre d'affaires trimestriel publié le {q.index[-1]:%d/%m/%Y}, "
                f"{q.iloc[-1] / 1e9:.1f} Md$ ({100 * (q.iloc[-1] / q.iloc[-5] - 1):+.0f} % sur un an, SEC)."
            )

    # ---------------------------------------------------------------- macro analysis (computed)
    L += ["", "## 2 ter. Analyse macro (modèles du monitor, calculée dans GitHub)", ""]
    from macro import pipeline as pipe
    from macro import portfolio as pf

    def safe(fn):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - one missing model must not stop the report
            L.append(f"- (indisponible : {type(exc).__name__})")
            return None

    reg = pf.regime_series(try_series("INDPRO"), try_series("CPIAUCSL")).dropna()
    if not reg.empty:
        L.append(
            f"- Régime (production industrielle et CPI, en tendance) : **{reg.iloc[-1]}**, depuis {reg[reg != reg.iloc[-1]].index[-1]:%d/%m/%Y}."
            if (reg != reg.iloc[-1]).any()
            else f"- Régime : **{reg.iloc[-1]}**."
        )
    mf = b.get("macro_now")
    if mf is not None and len(mf):
        L.append(
            "- Facteurs macro du modèle (−1 à +1) : " + ", ".join(f"{k} {v:+.2f}" for k, v in mf.items())
        )
    g = safe(lambda: pipe.growth_bundle())
    if g:
        nc = g["nowcast"]
        L.append(
            f"- Nowcast du PIB US ({nc['target']}) : {nc['point']:.1f} % annualisé (68 % : {nc['lo68']:.1f} à {nc['hi68']:.1f}) ; probabilité de récession à 12 mois {100 * float(g['recession'].value):.0f} %."
        )
    inf = safe(lambda: pipe.inflation_bundle("US"))
    if inf and inf.get("prob_exceed"):
        pe_ = inf["prob_exceed"]
        L.append(
            f"- Inflation US prévue à 12 mois : {pe_['point']:.1f} % ; probabilité de dépasser {pe_['threshold'] + pe_['margin']:.1f} % : {100 * pe_['p']:.0f} %."
        )
    ld = safe(lambda: pipe.leading_bundle())
    if ld is not None and not ld["table"].empty:
        best = ld["table"]["AUC"].idxmax()
        L.append(
            f"- Meilleur modèle de récession hors échantillon ({best}) : {100 * ld['table'].loc[best, 'probability now']:.0f} %."
        )
    fp, dff = try_series("FED_PRICED_12M"), try_series("DFF")
    if fp is not None and dff is not None:
        L.append(
            f"- Fed : taux effectif {dff.dropna().iloc[-1]:.2f} %, taux attendu par le marché à 12 mois {fp.dropna().iloc[-1]:.2f} %."
        )
    for sid, lab in (
        ("DGS10", "10 ans US"),
        ("DFII10", "10 ans réel"),
        ("BAMLH0A0HYM2", "spread haut rendement"),
        ("VIXCLS", "VIX"),
    ):
        x = try_series(sid)
        if x is not None and len(x.dropna()) > 22:
            x = x.dropna()
            L.append(f"- {lab} : {x.iloc[-1]:.2f} ({x.iloc[-1] - x.iloc[-22]:+.2f} sur un mois).")

    # ---------------------------------------------------------------- micro analysis (computed)
    L += ["", "## 2 quater. Analyse micro : poche semi-conducteurs (calculée dans GitHub)", ""]
    mt = b.get("micro_table")
    if mt is not None and not mt.empty:
        L.append("| Titre | " + " | ".join(mt.columns) + " | poids |")
        L.append("|---|" + "---|" * (len(mt.columns) + 1))
        for a, row in mt.iterrows():
            L.append(
                f"| {name(a)} | "
                + " | ".join("" if v != v else f"{v:+.2f}" for v in row)
                + f" | {100 * b['target'].get(a, 0):.1f} % |"
            )
    for a in [x for x in cfg["universe"] if cfg["universe"][x]["sleeve"] == "semis"]:
        s_ = try_series(a)
        if s_ is None or len(s_.dropna()) < 260:
            continue
        s_ = s_.dropna()
        r_ = s_.pct_change().dropna()
        L.append(
            f"- {name(a)} : {100 * (s_.iloc[-1] / s_.iloc[-252:].max() - 1):+.0f} % depuis son plus haut sur un an, "
            f"{100 * (s_.iloc[-1] / s_.iloc[-22] - 1):+.0f} % sur un mois, volatilité 3 mois {100 * r_.iloc[-63:].std() * 252**0.5:.0f} %."
        )
    for co in ("MU", "NVDA"):
        rv, gp = try_series(f"{co}_REV"), try_series(f"{co}_GP")
        if rv is not None and gp is not None and len(rv.dropna()) >= 5 and len(gp.dropna()) >= 2:
            m_ = (gp.dropna() / rv.dropna()).dropna()
            if len(m_) >= 2:
                L.append(
                    f"- {name(co)} : marge brute {100 * m_.iloc[-1]:.0f} % (trimestre précédent {100 * m_.iloc[-2]:.0f} %), données SEC."
                )
    mc = pf.memory_cycle(try_series("MU_REV"))
    if not mc.empty:
        L.append(
            f"- Cycle mémoire (accélération de la croissance du CA de Micron) : {100 * mc.iloc[-1]:+.1f} points au {mc.index[-1]:%d/%m/%Y}."
        )

    perf = b.get("performance")
    if perf is not None and not perf.empty:
        L += ["", "### Performance par période (USD, après coûts)", ""]
        cols = list(perf.columns)
        L.append("| Période | " + " | ".join(cols) + " |")
        L.append("|---|" + "---|" * len(cols))
        for k, row in perf.iterrows():
            L.append(f"| {k} | " + " | ".join("—" if pd.isna(v) else pct(v) for v in row) + " |")
        cal = b.get("calendar_returns")
        if cal is not None and not cal.empty:
            L += ["", "Par année (modèle ; année en cours à date) :", ""]
            L.append("| Année | Modèle | 60/40 | Écart |")
            L.append("|---|---|---|---|")
            for y, row in cal.head(10).iterrows():
                L.append(f"| {y} | {pct(row['year'])} | {pct(row['benchmark'])} | {pct(row['excess'])} |")

    L += ["", "## 2 quinquies. Contrôles du process : stress tests, revues de pertes, paris notés", ""]
    from macro import fund_process as fp

    fs = b.get("forward_stress", pd.DataFrame())
    if not fs.empty:
        worst = fs.sort_values("book").iloc[0]
        nb = int(fs["breach"].astype(bool).sum())
        L.append(
            f"- Stress tests prospectifs : {len(fs)} scénarios, {nb} au-delà des limites (15 % de la VL, ou la perte du "
            f"benchmark + 2 points). Pire cas : {fs.sort_values('book').index[0]} à {pct(worst['book'])} contre "
            f"{pct(worst['benchmark'])} pour le 60/40."
        )
        for k, row in fs[fs["breach"].astype(bool)].iterrows():
            L.append(
                f"  - ⚠ {k} : {pct(row['book'])} ({row['breach']}) ; principales pertes : {row['largest losses']}."
            )
    pms = b.get("post_mortems") or []
    if pms:
        L.append(f"- Revues de pertes ({b.get('post_mortem_source')}, 4 semaines, seuil 1 % de la VL) :")
        for pm in pms:
            L.append(
                f"  - {name(pm['asset'])} : {pct(pm['loss'], 2)} de la VL. {pm['verdict'].capitalize()}."
            )
    else:
        L.append("- Revues de pertes : aucune position n'a coûté plus de 1 % de la VL sur 4 semaines.")
    dec = fp.read_decisions()
    if dec.empty:
        L.append("- Registre des paris : vide pour l'instant (premières entrées au comité du soir).")
    else:
        bt = fp.brier_table(dec)
        team_row = bt.loc["team"] if "team" in bt.index else None
        L.append(
            f"- Registre des paris : {len(dec)} enregistrés, {int((dec['status'] == 'open').sum())} ouverts, "
            f"{int((dec['status'] == 'resolved').sum())} notés"
            + (
                f" ; score de Brier de l'équipe {team_row['Brier']:.3f} (0,25 = toujours 50 %)."
                if team_row is not None and pd.notna(team_row["Brier"])
                else "."
            )
        )

    L += ["", "## 3. Ce que disent les news (24 dernières heures)", ""]
    arch = ns.read_archive()
    now = pd.Timestamp.now(tz="UTC")
    if not arch.empty:
        recent = arch[arch["first_seen"] >= now - pd.Timedelta(days=1)]
        ncfg = news.load()
        if not recent.empty:
            a = ns.asset_scores(recent, ncfg, now=now)
            L.append(
                "Pression par position : "
                + ", ".join(
                    f"{i} {r_['news score']:+.2f} ({int(r_['headlines'])} titres)"
                    for i, r_ in a.head(7).iterrows()
                )
            )
            top = recent.assign(impact=ns.impact(recent, ncfg, now=now)).sort_values(
                "impact", ascending=False
            )
            for _, r_ in top.head(6).iterrows():
                L.append(
                    f"- [{r_['title']}]({r_['link']}) — {r_['source']}, sentiment {r_['sentiment']:+.2f}"
                )
    else:
        L.append("Pas encore d'archive de news notées.")

    # ---------------------------------------------------------------- research
    L += ["", "## 4. Publications des banques, gérants et hedge funds", ""]
    ra = rt.read_archive()
    if not ra.empty:
        new = ra[ra["first_seen"] >= now - pd.Timedelta(days=1)]
        with_st = new[new["stances"].map(bool)]
        L.append(
            f"{len(new)} nouvelles publications relevées, {len(with_st)} avec une recommandation explicite."
        )
        for _, r_ in with_st.head(10).iterrows():
            st = ", ".join(f"{name(k)} {'+' if v > 0 else '−'}" for k, v in r_["stances"].items())
            L.append(f"- {r_['institution']} : [{r_['title']}]({r_['link']}) → {st}")
        cons = rt.consensus(ra)
        views = pd.Series(snap["views"])
        div = [
            (a, row["net stance"], views.get(a, 0.0))
            for a, row in cons.iterrows()
            if row["mentions"] >= 2 and abs(row["net stance"] - views.get(a, 0.0)) > 0.8
        ]
        if div:
            L.append("")
            L.append(
                "Désaccords marqués entre le consensus publié (30 jours) et nos signaux : "
                + "; ".join(f"{name(a)} (consensus {c:+.1f}, nous {v:+.2f})" for a, c, v in div)
            )
    else:
        L.append("Pas encore d'archive de publications.")
    L += [
        "",
        "---",
        "Portefeuille modèle suivi sur papier : aucun ordre n'est passé. Détails : menu Portfolio du monitor.",
    ]
    text = "\n".join(L)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{day}.md").write_text(text, encoding="utf-8")
    print(text)
    if args.issue:
        subprocess.run(
            ["gh", "issue", "create", "--title", f"Rapport du soir — {day}", "--body", text[:60000]],
            check=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
