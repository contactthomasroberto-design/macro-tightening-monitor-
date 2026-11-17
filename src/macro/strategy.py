"""How the strategy evolves and whether it stays relevant: the history an allocator reads first.

- `record_metrics` appends one dated row per refresh to archive/strategy_metrics.csv (model version, backtest
  and benchmark figures, deflated Sharpe, overfitting probability, paper book), so the evolution of the
  strategy is measured on the record, not remembered.
- `hypotheses` collects the pre-registered verdicts of every quant-lab run (archive/quant_lab/*.json).
- `reviews` lists the committee's nightly strategy reviews (docs/research/strategy/*.md) with their verdict.
- `versions` reads the portfolio and backtest rows of docs/MODEL_CHANGELOG.md.
- `factsheet` writes the monthly factsheet in French (docs/factsheets/<YYYY-MM>.md).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from macro.config import ROOT

METRICS = ROOT / "archive" / "strategy_metrics.csv"
LAB = ROOT / "archive" / "quant_lab"
REVIEWS = ROOT / "docs" / "research" / "strategy"
CHANGELOG = ROOT / "docs" / "MODEL_CHANGELOG.md"
FACTSHEETS = ROOT / "docs" / "factsheets"
METRIC_COLUMNS = [
    "date",
    "version",
    "annual return",
    "volatility",
    "Sharpe",
    "max drawdown",
    "benchmark annual return",
    "benchmark Sharpe",
    "benchmark max drawdown",
    "deflated Sharpe",
    "PBO",
    "DSR model variants",
    "survivorship-free Sharpe",
    "paper return",
    "paper drawdown",
]
VERDICTS = {True: "validée", False: "rejetée"}


def _lab_runs(path: Path = LAB) -> list[dict]:
    out = []
    for f in sorted(Path(path).glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def _latest_lab(path: Path = LAB) -> dict:
    runs = _lab_runs(path)
    return runs[-1] if runs else {}


def metrics_row(b: dict, day: str) -> dict:
    """Today's figures of the strategy from the portfolio bundle and the latest quant lab."""
    m = b["metrics"]
    full, bench = m["full model"], m["benchmark 60/40"]
    lab = _latest_lab()
    h40 = lab.get("H40", {}) if isinstance(lab.get("H40"), dict) else {}
    variants = lab.get("variants", {}) if isinstance(lab.get("variants"), dict) else {}
    sf = variants.get("survivorship-free (H39)", {})
    nav = b.get("paper_nav", pd.Series(dtype=float))
    return {
        "date": day,
        "version": b.get("version", ""),
        "annual return": float(full["annual return"]),
        "volatility": float(full["volatility"]),
        "Sharpe": float(full["Sharpe"]),
        "max drawdown": float(full["max drawdown"]),
        "benchmark annual return": float(bench["annual return"]),
        "benchmark Sharpe": float(bench["Sharpe"]),
        "benchmark max drawdown": float(bench["max drawdown"]),
        "deflated Sharpe": float(b.get("deflated_sharpe", np.nan)),
        "PBO": float(h40.get("PBO", np.nan)) if h40 else np.nan,
        "DSR model variants": float(h40.get("DSR (model variants)", np.nan)) if h40 else np.nan,
        "survivorship-free Sharpe": float(sf.get("Sharpe", np.nan)) if sf else np.nan,
        "paper return": float(nav.iloc[-1] - 1) if len(nav) else np.nan,
        "paper drawdown": float(b.get("paper_drawdown", np.nan)) if len(nav) else np.nan,
    }


def record_metrics(row: dict, path: Path = METRICS) -> pd.DataFrame:
    """Append today's row, replacing an earlier row of the same day (one row per day)."""
    old = read_metrics(path)
    old = old[old["date"].astype(str) != str(row["date"])] if not old.empty else old
    df = pd.concat([old, pd.DataFrame([row], columns=METRIC_COLUMNS)], ignore_index=True)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df


def read_metrics(path: Path = METRICS) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=METRIC_COLUMNS)
    return pd.read_csv(path)


def hypotheses(path: Path = LAB) -> pd.DataFrame:
    """Every pre-registered verdict of the quant lab, latest first per hypothesis, with its history."""
    rows = []
    for run in _lab_runs(path):
        for h, v in (run.get("verdicts") or {}).items():
            val = v if isinstance(v, bool) else str(v).strip().lower() == "true"
            rows.append({"hypothesis": h, "date": run.get("date"), "verdict": VERDICTS[val]})
    df = pd.DataFrame(rows, columns=["hypothesis", "date", "verdict"])
    if df.empty:
        return df
    hist = df.groupby("hypothesis")["verdict"].apply(lambda s: " → ".join(s)).rename("history")
    last = df.sort_values("date").groupby("hypothesis").last().join(hist)
    order = sorted(last.index, key=lambda h: int(re.sub(r"\D", "", h) or 0))
    return last.loc[order].reset_index()


def reviews(path: Path = REVIEWS) -> pd.DataFrame:
    """The committee's strategy reviews: date, verdict line (the first non-title line) and file."""
    rows = []
    for f in sorted(Path(path).glob("20*.md")):
        lines = [x.strip() for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
        body = [x for x in lines if not x.startswith("#")]
        verdict = body[0].lstrip("*> ").strip() if body else ""
        try:
            rel = str(f.relative_to(ROOT))
        except ValueError:
            rel = str(f)
        rows.append({"date": f.stem, "verdict": verdict, "file": rel})
    return pd.DataFrame(rows, columns=["date", "verdict", "file"])


def versions(path: Path = CHANGELOG) -> pd.DataFrame:
    rows = []
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 5 and cells[1] in ("portfolio", "backtest"):
                rows.append(
                    {
                        "window": cells[0],
                        "model": cells[1],
                        "version": cells[2],
                        "change": cells[3],
                        "reason": cells[4],
                    }
                )
    return pd.DataFrame(rows, columns=["window", "model", "version", "change", "reason"])


# ---------------------------------------------------------------------------- factsheet
def _p(x, d: int = 1, sign: bool = True) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return (f"{100 * x:+.{d}f} %" if sign else f"{100 * x:.{d}f} %").replace(".", ",")


def factsheet(b: dict, month: str, verdict: str | None = None) -> str:
    """Monthly factsheet in French, in the layout allocators expect: objective, key figures against the
    benchmark and funds one can buy, monthly returns, allocation, main exposures, risk, committee view."""
    cfg = b["config"]
    m = b["metrics"]
    full, bench = m["full model"], m["benchmark 60/40"]
    perf = b.get("performance", pd.DataFrame())
    name = lambda a: cfg["universe"].get(a, {}).get("name", a)  # noqa: E731
    L = [
        f"# Fonds modèle macro global — factsheet {month}",
        "",
        "*Portefeuille modèle sur papier, à but de recherche : aucune offre ni recommandation d'investissement. "
        "Jusqu'au démarrage du carnet papier, les performances sont celles d'un backtest walk-forward (hypothétiques).*",
        "",
        "## Objectif et stratégie",
        "Fonds multi-actifs global, systématique, long/short (brut ≤ 160 %), rééquilibré chaque semaine. Objectif : "
        "un rendement supérieur au 60/40 mondial (ACWI/AGG) avec un drawdown au plus égal. Allocation par "
        "Black-Litterman à partir de vues de tendance, macro, régime, valeur, carry, micro (semi-conducteurs) et "
        "de vues publiées des grandes maisons ; couverture de queue et réduction du risque en drawdown.",
        f"Version du modèle : {b.get('version', 'n.d.')}.",
        "",
        "## Chiffres clés",
        "",
        "| | Fonds | 60/40 |",
        "|---|---|---|",
        f"| Rendement annualisé (depuis 2005) | {_p(full['annual return'])} | {_p(bench['annual return'])} |",
        f"| Volatilité | {_p(full['volatility'], sign=False)} | {_p(bench['volatility'], sign=False)} |",
        f"| Sharpe | {full['Sharpe']:.2f} | {bench['Sharpe']:.2f} |".replace(".", ","),
        f"| Drawdown maximal | {_p(full['max drawdown'])} | {_p(bench['max drawdown'])} |",
        f"| Pire année glissante | {_p(full.get('worst 52 weeks', np.nan))} | {_p(bench.get('worst 52 weeks', np.nan))} |",
    ]
    if perf is not None and not perf.empty:
        cols_fr = [
            str(c)
            .replace("model (backtest)", "Fonds (backtest)")
            .replace("benchmark 60/40", "60/40")
            .replace("paper book", "Carnet papier")
            for c in perf.columns
        ]
        L += ["", "| Période | " + " | ".join(cols_fr) + " |", "|---|" + "---|" * len(perf.columns)]
        fr = {
            "week": "Semaine",
            "month to date": "Mois en cours",
            "quarter to date": "Trimestre en cours",
            "year to date": "Depuis le 1er janvier",
            "last 12 months": "12 derniers mois",
            "since inception (annualised)": "Depuis l'origine (annualisé)",
        }
        lab = lambda k: fr.get(k, k.replace("last month", "Mois précédent"))  # noqa: E731
        L += [f"| {lab(str(k))} | " + " | ".join(_p(v) for v in r) + " |" for k, r in perf.iterrows()]
    fb = b.get("fund_benchmarks")
    if isinstance(fb, pd.DataFrame) and not fb.empty and "Sharpe" in fb.index:
        L += [
            "",
            "**Face aux fonds achetables** (historique commun) : "
            + ", ".join(f"{c} Sharpe {fb.loc['Sharpe', c]:.2f}".replace(".", ",") for c in fb.columns)
            + ".",
        ]
    cal = b.get("calendar_returns")
    if isinstance(cal, pd.DataFrame) and not cal.empty:
        cols = [c for c in cal.columns if c not in ("benchmark", "excess")]
        L += [
            "",
            "## Rendements mensuels",
            "",
            "| Année | " + " | ".join(cols) + " | 60/40 |",
            "|---|" + "---|" * (len(cols) + 1),
        ]
        for y, r in cal.head(6).iterrows():
            L.append(
                f"| {y} | "
                + " | ".join("" if pd.isna(r[c]) else _p(r[c]) for c in cols)
                + f" | {_p(r.get('benchmark'))} |"
            )
    w = b["target"]
    w = w[w.abs() > 1e-4]
    by = (
        w.groupby([cfg["universe"].get(a, {}).get("sleeve", "other") for a in w.index])
        .sum()
        .sort_values(ascending=False)
    )
    L += ["", "## Allocation", "", "| Poche | Poids net |", "|---|---|"] + [
        f"| {k} | {_p(v, sign=False)} |" for k, v in by.items()
    ]
    L += [
        "",
        f"Exposition brute {_p(b['gross'], 0, False)}, actions nettes {_p(b['net_equity'], 0, False)}.",
        "",
        "**Principales positions** : "
        + ", ".join(
            f"{name(a)} {_p(v)}"
            for a, v in w.reindex(w.abs().sort_values(ascending=False).index).head(10).items()
        )
        + ".",
    ]
    r = b["risk"]
    fs = b.get("forward_stress", pd.DataFrame())
    L += [
        "",
        "## Risque",
        "",
        f"- Volatilité ex ante {_p(r['volatility'], sign=False)} (60/40 {_p(r['benchmark volatility'], sign=False)}), tracking error {_p(r['tracking error'], sign=False)}.",
        f"- VaR 95 % à une semaine {_p(r['VaR 95% (1 week)'])}, expected shortfall {_p(r['expected shortfall 95% (1 week)'])}.",
    ]
    if isinstance(fs, pd.DataFrame) and not fs.empty:
        worst = fs.sort_values("book").iloc[0]
        L.append(
            f"- Pire scénario prospectif : {fs.sort_values('book').index[0]}, {_p(worst['book'])} (60/40 {_p(worst['benchmark'])})."
        )
    L += [
        "",
        "## Robustesse statistique",
        "",
        f"- Deflated Sharpe {b.get('deflated_sharpe', float('nan')):.2f} sur {b.get('trials', 'n.d.')} configurations (seuil 0,95 pour conclure à un alpha).".replace(
            ".", ",", 1
        ),
        "- Les verdicts des hypothèses pré-enregistrées sont publiés dans le journal de recherche et sur la page Stratégie.",
    ]
    if verdict:
        L += ["", "## Avis du comité d'investissement", "", verdict]
    L += [
        "",
        "---",
        "*Sources : données publiques (FRED, Yahoo Finance, SEC, BCE, BoJ) ; calcul automatique GitHub Actions.*",
    ]
    return "\n".join(L) + "\n"
