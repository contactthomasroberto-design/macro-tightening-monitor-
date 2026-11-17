"""Investment-process controls, run by the refresh workflow after the models (src/macro/fund_process.py).

MACRO_MODE=live python scripts/process_controls.py           # resolve decisions, write post-mortems
MACRO_MODE=live python scripts/process_controls.py --issue   # also open issues on stress-limit breaches

1. Resolves the committee's open forecasts in archive/decisions.csv whose horizon has passed (from
   prices of the portfolio universe or from any series of the data store), and prints the Brier table.
2. Writes a post-mortem note in docs/research/postmortems/ for each position that lost more than 1% of
   NAV over four weeks (once per asset and ISO week).
3. Opens an issue when a forward stress scenario breaches its limit (once per scenario and week)."""

from __future__ import annotations

import argparse
import json
import subprocess

import pandas as pd

import _bootstrap  # noqa: F401
from macro import fund_process as fp
from macro import portfolio as pf
from macro.config import ROOT
from macro.pipeline import portfolio_bundle, try_series
from macro.utils import is_demo

STATE = ROOT / "archive" / "process_alerts.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", action="store_true")
    args = ap.parse_args()
    b = portfolio_bundle()
    cfg = b["config"]
    px = pf.usd_prices(try_series, cfg)
    today = px.index[-1] if is_demo() else pd.Timestamp.today().normalize()
    week = f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"

    # 1. decision registry
    dec = fp.read_decisions()
    if not dec.empty:
        get = lambda k: px[k] if k in px else try_series(k)  # noqa: E731
        new = fp.resolve(dec, get, today)
        n = int(((new["status"] != "open") & (dec["status"] == "open")).sum())
        if not is_demo():
            fp.write_decisions(new)
        print(f"decisions: {len(new)} on record, {n} resolved today")
        print(fp.brier_table(new).round(3).to_string())
    else:
        print("decisions: none on record yet")

    # 2. post-mortems
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    done = set(state.get("post_mortems", []))
    fp.POSTMORTEMS.mkdir(parents=True, exist_ok=True)
    for pm in b.get("post_mortems", []):
        key = f"{week}:{pm['asset']}"
        if key in done:
            continue
        day = today.date().isoformat()
        path = fp.POSTMORTEMS / f"{day}-{pm['asset']}.md"
        if not is_demo():
            text = fp.post_mortem_markdown(pm, pm["loss"], day)
            path.write_text(text + f"\nSource des poids : {b.get('post_mortem_source')}.\n", encoding="utf-8")
        done.add(key)
        print(f"post-mortem: {pm['asset']} {100 * pm['loss']:+.2f}% of NAV -> {path.relative_to(ROOT)}")

    # 3. forward stress limits
    fs = b.get("forward_stress", pd.DataFrame())
    alerted = set(state.get("stress", []))
    breaches = fs[fs["breach"].astype(bool)] if not fs.empty else fs
    fresh = [k for k in breaches.index if f"{week}:{k}" not in alerted]
    if not fs.empty:
        print(fs[["book", "benchmark", "limit", "breach"]].to_string())
    if fresh and args.issue and not is_demo():
        body = "\n".join(
            f"- **{k}** : livre {100 * breaches.loc[k, 'book']:+.1f} %, benchmark "
            f"{100 * breaches.loc[k, 'benchmark']:+.1f} % ({breaches.loc[k, 'breach']}) ; "
            f"plus grosses pertes : {breaches.loc[k, 'largest losses']}"
            for k in fresh
        )
        body += "\n\nInformation pour le comité : le mandat ne change pas de lui-même. Page Portfolio → Risk."
        subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--title",
                f"Stress test : limite dépassée ({len(fresh)})",
                "--body",
                body,
            ],
            check=False,
        )
    alerted |= {f"{week}:{k}" for k in fresh}
    if not is_demo():
        STATE.write_text(json.dumps({"post_mortems": sorted(done)[-200:], "stress": sorted(alerted)[-200:]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
