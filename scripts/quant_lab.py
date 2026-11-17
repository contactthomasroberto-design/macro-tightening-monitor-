"""Weekly quant lab: the research team's pre-registered tests, run in GitHub Actions (no AI tokens).

MACRO_MODE=live python scripts/quant_lab.py          # write docs/research/quant/<date>.md and a JSON

1. Signal audit: information coefficient of every view family against the next 4 and 13 weeks'
   return, pooled across assets, on non-overlapping samples, with t-statistics.
2. H40: deflated Sharpe ratio over model variants only; probability of backtest overfitting (CSCV,
   16 blocks); minimum track-record length of the paper book.
3. H36: EWMA volatility (half-life 13 weeks) against the 156-week window.
4. H37: multi-horizon trend (4, 13, 52 weeks) against 12-1 month trend and against no trend.
5. H44: weeks run with a relaxed constraint and their share of the worst drawdown.
6. Stock-bond correlation when the 10-year yield is above 5% and core inflation above 3%.
7. Candidate signals H48-H51: country valuation, CFTC positioning, earnings momentum (each at
   confidence 0.10 in its own variant) and event de-risking before FOMC, US CPI and NVIDIA earnings.
Thresholds are those written in docs/research_log.md before the first run."""

from __future__ import annotations

import copy
import itertools
import json

import numpy as np
import pandas as pd
from scipy import stats

import _bootstrap  # noqa: F401
from macro import pipeline
from macro import portfolio as pf
from macro.config import ROOT
from macro.data import try_series

OUT = ROOT / "docs" / "research" / "quant"
JSON = ROOT / "archive" / "quant_lab"


def md(df: pd.DataFrame, index: bool = True) -> str:
    """Markdown table without extra dependencies."""
    d = df.reset_index() if index else df
    cells = [
        [f"{v:.3f}" if isinstance(v, float) else str(v) for v in row] for row in d.itertuples(index=False)
    ]
    head = "| " + " | ".join(map(str, d.columns)) + " |"
    sep = "|" + "---|" * len(d.columns)
    return "\n".join([head, sep] + ["| " + " | ".join(c) + " |" for c in cells])


def signal_audit(inp: pf.Inputs, cfg: dict, step: int = 4) -> pd.DataFrame:
    """IC per family and horizon, pooled across assets, sampled every `step` weeks."""
    r = inp.r
    assets = [a for a in cfg["universe"] if a in r]
    weeks = r.index[156::step]
    rows = []
    for t in weeks[:-13]:
        cov = pf.covariance(r.loc[:t, assets], 156, 52)
        v = pf.views_at(inp, t, list(cov.index), cfg)
        i = r.index.get_loc(t)
        for h in (4, 13):
            fwd = (1 + r.iloc[i + 1 : i + 1 + h]).prod() - 1
            for fam, sc in v.items():
                for a, s in sc.items():
                    if a in fwd and fwd[a] == fwd[a]:
                        rows.append({"family": fam, "h": h, "t": t, "asset": a, "s": s, "f": fwd[a]})
    df = pd.DataFrame(rows)
    out = []
    for (fam, h), g in df.groupby(["family", "h"]):
        g = g[g["t"].isin(weeks[:: max(1, h // step)])]  # non-overlapping in time
        if len(g) < 30:
            continue
        ic = stats.spearmanr(g["s"], g["f"])[0]
        n_t = g["t"].nunique()
        out.append(
            {"family": fam, "horizon (weeks)": h, "IC": ic, "t (dates)": ic * np.sqrt(n_t), "obs": len(g)}
        )
    return pd.DataFrame(out)


def pbo_cscv(returns: pd.DataFrame, blocks: int = 16) -> float:
    """Probability of backtest overfitting (Bailey et al., 2017): share of combinatorial splits where
    the in-sample best variant ranks below the median out of sample."""
    r = returns.dropna()
    parts = np.array_split(np.arange(len(r)), blocks)
    logits = []
    for ins in itertools.combinations(range(blocks), blocks // 2):
        i_idx = np.concatenate([parts[k] for k in ins])
        o_idx = np.concatenate([parts[k] for k in range(blocks) if k not in ins])
        sr_i = r.iloc[i_idx].mean() / r.iloc[i_idx].std()
        sr_o = r.iloc[o_idx].mean() / r.iloc[o_idx].std()
        best = sr_i.idxmax()
        rank = (sr_o < sr_o[best]).mean()
        logits.append(rank)
    return float(np.mean(np.array(logits) <= 0.5))


def min_track_record(ret: pd.Series, sr_target: float = 0.0, conf: float = 0.95) -> float:
    """Minimum track-record length in weeks to reject SR ≤ target at `conf` (Bailey and López de Prado)."""
    r = ret.dropna()
    sr = r.mean() / r.std()
    if sr <= sr_target:
        return float("inf")
    sk, ku = stats.skew(r), stats.kurtosis(r, fisher=False)
    z = stats.norm.ppf(conf)
    return float(1 + (1 - sk * sr + (ku - 1) / 4 * sr**2) * (z / (sr - sr_target)) ** 2)


def run_variant(inp: pf.Inputs, cfg: dict, **model) -> dict:
    c = copy.deepcopy(cfg)
    c["model"].update(model)
    return pf.backtest(inp, c)


def main() -> int:
    day = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    cfg, px, inp = pipeline.portfolio_inputs()
    r = inp.r
    bench = pf.benchmark_returns(r, cfg)
    cash = r["BIL"]
    res: dict = {"date": day}
    L = [
        f"# Laboratoire quant — {day}",
        "",
        "*Tests pré-enregistrés exécutés automatiquement (GitHub Actions).*",
        "",
    ]

    # 1. signal audit
    audit = signal_audit(inp, cfg)
    res["signal_audit"] = audit.round(4).to_dict("records")
    L += ["## 1. Audit des signaux (IC de Spearman, échantillons non chevauchants)", ""]
    L.append(md(audit, index=False) if not audit.empty else "Pas assez de données.")
    L += [
        "",
        "Un IC positif avec t > 2 indique un signal qui a prédit les rendements ; un IC proche de 0, aucun pouvoir.",
        "",
    ]

    # 2-4. variants
    base = pf.backtest(inp, cfg)
    ewma = run_variant(inp, cfg, cov_halflife_weeks=13)
    multi = run_variant(inp, cfg, trend_horizons=[4, 13, 52])
    fams = tuple(f for f in pf.FAMILIES if f != "trend")
    no_trend = pf.backtest(inp, cfg, families=fams)
    # step 3: correlated Ω; step 2: forced cash; step 4: semis floor and SOX hedge; step 1: survivorship
    omega = run_variant(inp, cfg, omega="correlated")
    cash_v = run_variant(inp, cfg, on_infeasible="cash")
    floor0 = copy.deepcopy(cfg)
    floor0["sleeves"]["semis"]["min"] = 0.0
    for a in ("HYNIX", "SAMSUNG"):
        floor0["universe"][a]["min"] = 0.0
    no_floor = pf.backtest(inp, floor0)
    soxh = copy.deepcopy(cfg)
    soxh["model"]["tail_hedge"]["underlying"] = "SOX"
    sox_hedge = pf.backtest(inp, soxh)
    clean = copy.deepcopy(cfg)  # survivorship-free: no hand-picked names, semiconductors via SOXX only
    for a in ("HYNIX", "SAMSUNG", "MU", "TSM", "NVDA", "ASML"):
        clean["universe"].pop(a, None)
    clean["sleeves"]["semis"]["min"] = 0.0
    clean["universe"]["SOXX"]["min"] = 0.0
    no_names = pf.backtest(inp, clean)
    # H47: Michaud resampling; 25 draws a week keeps the lab within its time budget
    resampled = run_variant(inp, cfg, resample={"draws": 25, "seed": 0})

    def with_conf(fam: str, c: float = 0.10) -> dict:
        x = copy.deepcopy(cfg)
        x["model"]["confidence"][fam] = c
        return pf.backtest(inp, x, families=(*pf.FAMILIES, fam))

    cand = {
        "valuation (H48)": with_conf("valuation"),
        "positioning (H49)": with_conf("positioning"),
        "earnings (H50)": with_conf("earnings"),
    }
    evc = copy.deepcopy(cfg)
    evc["model"]["event_derisk"]["enabled"] = True
    cand["event de-risk (H51)"] = pf.backtest(inp, evc)
    runs = {
        "v0.3": base,
        "EWMA vol (H36)": ewma,
        "multi-horizon trend (H37)": multi,
        "no trend": no_trend,
        "correlated omega (H38)": omega,
        "survivorship-free (H39)": no_names,
        "semis floor 0 (H41)": no_floor,
        "SOX put hedge (H42)": sox_hedge,
        "forced cash (H44)": cash_v,
        "resampled weights (H47)": resampled,
        **cand,
    }
    start = base["returns"].index[0]
    b = bench.loc[start:]
    met = pd.DataFrame({k: pf.metrics(v["returns"], cash, b) for k, v in runs.items()})
    met["benchmark 60/40"] = pd.Series(pf.metrics(b, cash))
    res["variants"] = met.round(4).to_dict()
    L += ["## 2. Variantes (walk-forward hebdomadaire, net de coûts)", "", md(met.T), ""]

    # H36
    relaxed = {k: float((v["log"]["status"] != "optimal").mean()) for k, v in runs.items()}
    dd0, dd1 = met.loc["max drawdown", "v0.3"], met.loc["max drawdown", "EWMA vol (H36)"]
    sh0, sh1 = met.loc["Sharpe", "v0.3"], met.loc["Sharpe", "EWMA vol (H36)"]
    h36 = (dd1 - dd0 >= 0.03) and (sh0 - sh1 <= 0.05) and relaxed["EWMA vol (H36)"] < 0.02
    L.append(
        f"- **H36 {'confirmée' if h36 else 'rejetée'}** : drawdown max {dd1:.1%} contre {dd0:.1%}, Sharpe {sh1:.2f} contre "
        f"{sh0:.2f}, semaines avec contrainte levée {relaxed['EWMA vol (H36)']:.1%}."
    )
    # H37
    dd_m, dd_n = met.loc["max drawdown", "multi-horizon trend (H37)"], met.loc["max drawdown", "no trend"]
    rm = multi["returns"]
    spx_w = r["SPY"].reindex(rm.index)
    worst = rm[spx_w <= spx_w.quantile(0.2)]
    boots = [worst.sample(len(worst), replace=True, random_state=k).mean() for k in range(500)]
    lo90 = float(np.quantile(boots, 0.05))
    h37 = (dd_m >= dd_n) and lo90 > 0
    L.append(
        f"- **H37 {'confirmée' if h37 else 'rejetée'}** : drawdown max {dd_m:.1%} avec tendance multi-horizon contre "
        f"{dd_n:.1%} sans tendance ; rendement moyen dans le pire quintile du S&P 500, borne basse à 90 % {lo90:.2%} par semaine."
    )
    # H40
    act = pd.DataFrame({k: (v["returns"] - b).dropna() for k, v in runs.items()}).dropna()
    trial_sr = [float(act[c].mean() / act[c].std()) for c in act]
    dsr = pf.deflated_sharpe(act["v0.3"], trial_sr)
    pbo = pbo_cscv(pd.DataFrame({k: v["returns"] for k, v in runs.items()}))
    beta = np.cov(base["returns"], b.reindex(base["returns"].index).fillna(0))[0, 1] / b.var()
    resid = (base["returns"] - beta * b.reindex(base["returns"].index)).dropna()
    mintrl = min_track_record(resid)

    # H38, H39, H41, H42, H44
    def mm(k, f):
        return met.loc[f, k]

    to = {k: float(v["log"]["turnover"].mean()) for k, v in runs.items()}
    h38 = (
        to["correlated omega (H38)"] <= 0.8 * to["v0.3"]
        and abs(mm("correlated omega (H38)", "Sharpe") - sh0) <= 0.05
    )
    L.append(
        f"- **H38 {'confirmée' if h38 else 'rejetée'}** : rotation moyenne {to['correlated omega (H38)']:.1%} contre "
        f"{to['v0.3']:.1%} par semaine, Sharpe {mm('correlated omega (H38)', 'Sharpe'):.2f} contre {sh0:.2f}."
    )
    bm = met["benchmark 60/40"]
    h39 = (
        mm("survivorship-free (H39)", "max drawdown") >= bm["max drawdown"]
        and mm("survivorship-free (H39)", "Sharpe") >= bm["Sharpe"]
    )
    L.append(
        f"- **H39 {'confirmée' if h39 else 'rejetée'}** (sans les 6 valeurs choisies en 2026, semis via SOXX seul) : drawdown "
        f"{mm('survivorship-free (H39)', 'max drawdown'):.1%} contre {bm['max drawdown']:.1%} pour le 60/40, Sharpe "
        f"{mm('survivorship-free (H39)', 'Sharpe'):.2f} contre {bm['Sharpe']:.2f}"
        + ("." if h39 else " : l'avance du modèle dépend de la sélection de 2026.")
    )

    def cvar(x):
        q = x.quantile(0.05)
        return float(-x[x <= q].mean())

    c0, c1 = cvar(base["returns"]), cvar(no_floor["returns"])
    h41 = mm("semis floor 0 (H41)", "Sharpe") >= sh0 and c1 < c0
    L.append(
        f"- **H41 {'confirmée' if h41 else 'rejetée'}** (plancher semis à 0) : Sharpe {mm('semis floor 0 (H41)', 'Sharpe'):.2f} "
        f"contre {sh0:.2f}, CVaR hebdo 5 % {c1:.2%} contre {c0:.2%}."
    )
    semis_ret = r[[a for a in ("HYNIX", "SAMSUNG", "MU", "TSM", "NVDA", "ASML") if a in r]].mean(axis=1)

    def sleeve_dd(res_):
        wts = res_["weights"].reindex(r.index, method="ffill").reindex(res_["returns"].index)
        names = [a for a in wts.columns if cfg["universe"].get(a, {}).get("sleeve") == "semis"]
        x = (wts[names].sum(axis=1) * semis_ret.reindex(wts.index)).fillna(0)
        return float(((1 + x).cumprod() / (1 + x).cumprod().cummax() - 1).min())

    cost = {
        k: float(v["hedges"]["premium (% of NAV)"].sum()) if not v["hedges"].empty else 0.0
        for k, v in (("SPX", base), ("SOX", sox_hedge))
    }
    L.append(
        f"- **H42 (diagnostic)** : put SOX contre put S&P 500 — drawdown max du fonds {mm('SOX put hedge (H42)', 'max drawdown'):.1%} "
        f"contre {dd0:.1%} ; primes cumulées {cost['SOX']:.1%} contre {cost['SPX']:.1%} de l'actif ; drawdown de la poche semis "
        f"{sleeve_dd(sox_hedge):.1%} contre {sleeve_dd(base):.1%}."
    )
    h44 = mm("forced cash (H44)", "max drawdown") > dd0
    L.append(
        f"- **H44 {'confirmée' if h44 else 'rejetée'}** (cash forcé au lieu de lever une contrainte) : drawdown max "
        f"{mm('forced cash (H44)', 'max drawdown'):.1%} contre {dd0:.1%}."
    )
    # H46: is the active return more than style exposure one could buy with ETFs?
    ad = pf.alpha_decomposition(base["returns"], r, b)
    h46 = bool(ad["alpha t"] >= 2)
    lo46 = ad["loadings"]
    top = (
        ", ".join(
            f"{k} {v:+.2f}" for k, v in lo46["loading"].abs().sort_values(ascending=False).head(3).items()
        )
        if not lo46.empty
        else "n/a"
    )
    L.append(
        f"- **H46 {'confirmée' if h46 else 'rejetée'}** (alpha après styles) : rendement actif net des facteurs "
        f"{ad['alpha (annual)']:+.2%} par an (t {ad['alpha t']:+.1f}, HAC), R² {ad['R²']:.0%} ; plus fortes "
        f"expositions (en valeur absolue) : {top}."
    )
    res["H46"] = {
        "alpha (annual)": ad["alpha (annual)"],
        "alpha t": ad["alpha t"],
        "R2": ad["R²"],
        "loadings": lo46["loading"].round(3).to_dict() if not lo46.empty else {},
    }
    # H47: resampled weights trade less without costing Sharpe
    k47 = "resampled weights (H47)"
    h47 = to[k47] <= 0.8 * to["v0.3"] and mm(k47, "Sharpe") >= sh0 - 0.05
    L.append(
        f"- **H47 {'confirmée' if h47 else 'rejetée'}** (rééchantillonnage de Michaud, 25 tirages) : rotation "
        f"{to[k47]:.1%} contre {to['v0.3']:.1%} par semaine, Sharpe {mm(k47, 'Sharpe'):.2f} contre {sh0:.2f}, "
        f"drawdown max {mm(k47, 'max drawdown'):.1%} contre {dd0:.1%}."
    )
    res["verdicts"] = {
        "H36": h36,
        "H37": h37,
        "H38": h38,
        "H39": h39,
        "H41": h41,
        "H44": h44,
        "H46": h46,
        "H47": bool(h47),
    }
    res["H40"] = {"DSR (model variants)": dsr, "PBO": pbo, "beta": float(beta), "MinTRL weeks": mintrl}
    L.append(
        f"- **H40** : deflated Sharpe sur les seules variantes du modèle {dsr:.2f} ; probabilité de surapprentissage "
        f"(PBO, CSCV 16 blocs) {pbo:.0%} {'(trop élevée : pas de succès revendiqué)' if pbo > 0.5 else ''}; "
        f"bêta au 60/40 {beta:.2f} ; historique minimal pour prouver un alpha ajusté du bêta : "
        f"{'jamais (Sharpe ≤ 0)' if mintrl == float('inf') else f'{mintrl / 52:.1f} ans'}."
    )
    # H44
    lg = base["log"]
    nav = (1 + base["returns"]).cumprod()
    trough = (nav / nav.cummax() - 1).idxmin()
    peak = nav.loc[:trough].idxmax()
    in_dd = lg.loc[peak:trough]
    share = float((in_dd["status"] != "optimal").mean()) if len(in_dd) else 0.0
    L.append(
        f"- **H44 (diagnostic)** : semaines avec contrainte levée {relaxed['v0.3']:.1%} sur tout l'historique, "
        f"{share:.0%} pendant le pire drawdown ({peak:%Y-%m} → {trough:%Y-%m})."
    )
    res["relaxed share"] = relaxed

    # H48-H51: candidate signals (thresholds pre-registered in docs/research_log.md)
    def ic_t(fam: str, h: int) -> tuple[float, float]:
        if audit.empty:
            return float("nan"), float("nan")
        row = audit[(audit["family"] == fam) & (audit["horizon (weeks)"] == h)]
        if row.empty:
            return float("nan"), float("nan")
        return float(row["IC"].iloc[0]), float(row["t (dates)"].iloc[0])

    L += ["", "### Signaux candidats (H48-H51)", ""]
    for hyp, fam, h in (("H48", "valuation", 13), ("H49", "positioning", 4), ("H50", "earnings", 13)):
        k = f"{fam} ({hyp})"
        ic, tt = ic_t(fam, h)
        ok = bool(
            tt > 2 and mm(k, "Sharpe") >= sh0 and mm(k, "max drawdown") >= dd0 - 0.01 and relaxed[k] < 0.02
        )
        res["verdicts"][hyp] = ok
        L.append(
            f"- **{hyp} {'confirmée' if ok else 'rejetée'}** ({fam}) : IC à {h} semaines {ic:+.3f} (t = {tt:.1f}) ; "
            f"Sharpe {mm(k, 'Sharpe'):.2f} contre {sh0:.2f} ; drawdown max {mm(k, 'max drawdown'):.1%} contre {dd0:.1%}."
        )
    k = "event de-risk (H51)"
    share_ev = float(
        np.mean(
            [
                bool(pf.events_ahead(inp.events, t, 7) & {"fomc", "cpi", "nvda_earnings"})
                for t in base["log"].index
            ]
        )
    )
    h51 = bool(mm(k, "max drawdown") - dd0 >= 0.01 and sh0 - mm(k, "Sharpe") <= 0.03)
    res["verdicts"]["H51"] = h51
    L.append(
        f"- **H51 {'confirmée' if h51 else 'rejetée'}** (réduction du risque la semaine avant FOMC, CPI US et résultats "
        f"NVIDIA) : drawdown max {mm(k, 'max drawdown'):.1%} contre {dd0:.1%}, Sharpe {mm(k, 'Sharpe'):.2f} contre "
        f"{sh0:.2f} ; part des semaines concernées {share_ev:.0%}."
    )

    # 6. stock-bond correlation by regime
    y10 = try_series("DGS10")
    core = try_series("CPILFESL")
    if y10 is not None and core is not None:
        w = pd.DataFrame({"eq": r["SPY"], "bd": r["IEF"]}).dropna()
        corr = w["eq"].rolling(26).corr(w["bd"])
        yy = y10.resample("W-FRI").last().reindex(corr.index, method="ffill")
        cm = core.dropna().resample("MS").last()
        cy = (
            (100 * (cm / cm.shift(12) - 1))
            .resample("W-FRI")
            .ffill()
            .shift(6)
            .reindex(corr.index, method="ffill")
        )
        hot = (yy > 5) & (cy > 3)
        calm = (yy < 4) & (cy < 2.5)
        L += [
            "",
            "## 3. Corrélation actions-obligations selon le régime (26 semaines, SPY contre IEF)",
            "",
            f"- 10 ans > 5 % et inflation sous-jacente > 3 % : corrélation moyenne {corr[hot].mean():+.2f} ({int(hot.sum())} semaines).",
            f"- 10 ans < 4 % et inflation sous-jacente < 2,5 % : {corr[calm].mean():+.2f} ({int(calm.sum())} semaines).",
            f"- Aujourd'hui : {corr.dropna().iloc[-1]:+.2f}.",
            "",
            "Une corrélation positive signifie que les obligations ne couvrent plus les baisses des actions.",
        ]
        res["stock_bond"] = {
            "hot": float(corr[hot].mean()),
            "calm": float(corr[calm].mean()),
            "now": float(corr.dropna().iloc[-1]),
        }
    L += [
        "",
        "---",
        "Règle : aucun paramètre n'est changé sur la foi d'un test ; une hypothèse confirmée devient une proposition de version datée.",
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    JSON.mkdir(parents=True, exist_ok=True)
    (OUT / f"{day}.md").write_text("\n".join(L), encoding="utf-8")
    (JSON / f"{day}.json").write_text(json.dumps(res, indent=1, default=str))
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
