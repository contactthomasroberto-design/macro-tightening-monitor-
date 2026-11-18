"""Automatic bug detection, run by the refresh workflow after the models and the desk.

MACRO_MODE=live python scripts/health_check.py           # write archive/health.json and docs/engineering/health.md
MACRO_MODE=live python scripts/health_check.py --issue   # also open a GitHub issue (label "bug") for each new failure

Checks what a fund's QA would check every day: every view family produces views, nothing is dated in the
future, no non-positive or stale prices, monthly macro series without silent gaps, every desk note computed.
The nightly engineering team (software-engineer, qa-engineer) reads the result and fixes the bugs with a
regression test (docs/engineering/bugs.md)."""

from __future__ import annotations

import argparse
import json
import subprocess

import pandas as pd

import _bootstrap  # noqa: F401
from macro import portfolio as pf
from macro.config import ROOT
from macro.pipeline import portfolio_bundle, try_series
from macro.utils import is_demo

STATE = ROOT / "archive" / "health.json"
OUT = ROOT / "docs" / "engineering" / "health.md"
EXPECTED_EMPTY = {
    "news",
    "committee",
    "valuation",
    "positioning",
    "earnings",
}  # gated, forward-only or candidates
MONTHLY = ("CPIAUCSL", "CPILFESL", "PCEPILFE", "UNRATE", "PAYEMS", "INDPRO", "EA_HICP", "JP_CPI")


def checks() -> list[dict]:
    out: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        out.append({"check": name, "ok": bool(ok), "detail": detail})

    b = portfolio_bundle()
    cfg = b["config"]
    t = pd.Timestamp(b["as_of"])
    for fam in pf.FAMILIES:
        v = b["views"].get(fam)
        n = 0 if v is None else int(pd.Series(v).dropna().size)
        if fam not in EXPECTED_EMPTY:
            add(f"view family '{fam}' produces views", n > 0, f"{n} instruments")
    reg = pf.regime_series(try_series("INDPRO"), try_series("CPIAUCSL")).dropna()
    add("regime series is computed", not reg.empty, f"{len(reg)} weeks")
    if not reg.empty:
        used = reg.loc[:t]
        add(
            "regime used by the model is not dated after the as-of date",
            not used.empty and used.index[-1] <= t,
            f"label '{used.iloc[-1] if not used.empty else 'n.d.'}' at {used.index[-1].date() if not used.empty else 'n.d.'}",
        )
    px = pf.usd_prices(try_series, cfg)
    raw_bad = []
    for a in cfg["universe"]:
        s = try_series(a)
        if s is not None and (s.dropna() <= 0).any():
            raw_bad.append(a)
    add(
        "no non-positive raw prices (masked in the model, to clean at the source)",
        not raw_bad,
        ", ".join(raw_bad) or "none",
    )
    if not px.empty:
        today = px.index[-1] if is_demo() else pd.Timestamp.today().normalize()
        last = px.apply(lambda s: s.dropna().index[-1] if s.notna().any() else pd.NaT)
        stale = [a for a, d in last.items() if a in cfg["universe"] and pd.notna(d) and (today - d).days > 7]
        add("universe prices less than a week old", not stale, ", ".join(stale) or "none")
    gaps = []
    for sid in MONTHLY:
        s = try_series(sid)
        if s is None or len(s.dropna()) < 30:
            continue
        m = s.dropna().resample("MS").last().iloc[-36:]
        miss = [d.strftime("%Y-%m") for d in m.index[m.isna()]]
        if miss:
            gaps.append(f"{sid}: {', '.join(miss)}")
    add(
        "monthly macro series without missing months (36 months)",
        not gaps,
        "; ".join(gaps) + (" (changes must use calendar months, see desk.monthly_change)" if gaps else "")
        or "none",
    )
    readme = ROOT / "docs" / "research" / "desk" / "README.md"
    if readme.exists():
        bad = [
            ln.split("|")[1].strip()
            for ln in readme.read_text(encoding="utf-8").splitlines()
            if "Indisponible" in ln
        ]
        add("every desk note computed", not bad, ", ".join(bad) or "all")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", action="store_true")
    args = ap.parse_args()
    res = checks()
    failed = [r for r in res if not r["ok"]]
    now = pd.Timestamp.now(tz="UTC")
    lines = [
        f"# Santé du système — {now:%d/%m/%Y %H:%M} UTC",
        "",
        f"{len(res) - len(failed)} contrôles OK sur {len(res)}. Généré par scripts/health_check.py à chaque rafraîchissement ; "
        "l'équipe ingénierie corrige chaque échec avec un test (docs/engineering/bugs.md).",
        "",
        "| Contrôle | État | Détail |",
        "|---|---|---|",
    ]
    lines += [f"| {r['check']} | {'✅' if r['ok'] else '❌'} | {r['detail']} |" for r in res]
    print("\n".join(lines))
    if is_demo():
        return 0
    prev = json.loads(STATE.read_text()) if STATE.exists() else {}
    known = set(prev.get("failed", []))
    new = [r for r in failed if r["check"] not in known]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    STATE.write_text(
        json.dumps(
            {"date": now.isoformat(), "failed": [r["check"] for r in failed], "results": res}, indent=1
        )
    )
    if args.issue:
        for r in new:
            subprocess.run(
                [
                    "gh",
                    "issue",
                    "create",
                    "--title",
                    f"Bug détecté : {r['check']}",
                    "--label",
                    "bug",
                    "--body",
                    f"Contrôle automatique en échec : **{r['check']}**\n\nDétail : {r['detail']}\n\n"
                    "À corriger par l'équipe ingénierie avec un test de non-régression (docs/engineering/bugs.md).",
                ],
                check=False,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
