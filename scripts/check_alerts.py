"""Signpost alerts: open a GitHub issue when a signpost is newly crossed (GitHub e-mails the owner).

MACRO_MODE=live python scripts/check_alerts.py            # evaluate, update archive/signposts_state.json
MACRO_MODE=live python scripts/check_alerts.py --issue    # also open issues (needs the gh CLI and GH_TOKEN)

The state file records which signposts were crossed at the last check, so an alert fires once when a
threshold is crossed, not on every run while it stays crossed.
"""

from __future__ import annotations

import argparse
import json
import subprocess

import _bootstrap  # noqa: F401
from macro import signposts as sp
from macro.config import ROOT
from macro.data import try_series
from macro.utils import is_demo

STATE = ROOT / "archive" / "signposts_state.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", action="store_true", help="open a GitHub issue per newly crossed signpost")
    args = ap.parse_args()
    if is_demo():
        print("demo mode: no alerts")
        return 0
    now = sp.evaluate(try_series)
    prev = json.loads(STATE.read_text()) if STATE.exists() else {}
    new = sp.newly_crossed(now, prev)
    for i in new:
        r = now.loc[i]
        title = f"Signpost crossed: {r['label']} {r['op']} {r['threshold']}{r['unit']} ({r['latest']:.2f} on {r['date']})"
        body = (
            f"**{r['label']}** is {r['latest']:.2f}{r['unit']} ({r['date']}), {r['op']} the threshold "
            f"{r['threshold']}{r['unit']}.\n\nWhat it would change: {r['meaning']}.\n\n"
            "Opened automatically by the refresh workflow (scripts/check_alerts.py). Research product, not "
            "investment advice."
        )
        print("ALERT:", title)
        if args.issue:
            subprocess.run(["gh", "issue", "create", "--title", title, "--body", body], check=False)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps({i: bool(r["crossed"]) for i, r in now.iterrows() if r["crossed"] is not None}, indent=2)
    )
    print(f"{int(now['crossed'].fillna(False).sum())} of {len(now)} signposts crossed; {len(new)} new")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
