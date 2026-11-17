"""The GitHub desk: every computable analyst note, at every refresh, without AI tokens (src/macro/desk.py).

MACRO_MODE=live python scripts/desk_run.py

Writes docs/research/desk/<agent>.md (the latest note of each member, overwritten), docs/research/desk/README.md
(the index with the points to debate) and one line per member and day in archive/desk_log.csv, so the Team page
shows what each member is working on."""

from __future__ import annotations

import pandas as pd

import _bootstrap  # noqa: F401
from macro import desk, team
from macro import portfolio as pf
from macro.config import ROOT
from macro.pipeline import portfolio_bundle, try_series
from macro.utils import is_demo

OUT = ROOT / "docs" / "research" / "desk"
TAG = "(calcul GitHub)"


def main() -> int:
    b = portfolio_bundle()
    px = pf.usd_prices(try_series, b["config"])
    ctx = desk.Context(b=b, get=try_series, px=px)
    notes = desk.run(ctx)
    now = pd.Timestamp.now(tz="UTC")
    stamp = f"{now:%d/%m/%Y %H:%M} UTC"
    OUT.mkdir(parents=True, exist_ok=True)
    seen: dict[str, int] = {}
    index = [
        f"# Desk GitHub — {stamp}",
        "",
        "Notes calculées à chaque rafraîchissement, sans IA : chiffres, scores des "
        "familles de signaux sur tout l'univers, scans de tous les marchés suivis. Le comité du soir les débat.",
        "",
        "| Membre | Note | En bref |",
        "|---|---|---|",
    ]
    rows = []
    for n in notes:
        k = seen.get(n.agent, 0)
        seen[n.agent] = k + 1
        fname = f"{n.agent}.md" if k == 0 else f"{n.agent}-{k + 1}.md"
        if not is_demo():
            (OUT / fname).write_text(desk.markdown(n, stamp), encoding="utf-8")
        index.append(f"| `{n.agent}` | [{n.task}]({fname}) | {n.summary.replace('|', '/')} |")
        if k == 0:
            rows.append(
                {
                    "date": now.date().isoformat(),
                    "agent": n.agent,
                    "status": "terminé",
                    "task": n.task if TAG in n.task else f"{n.task} {TAG}",
                    "summary": n.summary,
                    "link": f"docs/research/desk/{fname}",
                }
            )
    watch = [f"- `{n.agent}` : {w}" for n in notes if n.agent != "chief-investment-officer" for w in n.watch]
    index += ["", f"## Points à débattre ({len(watch)})", "", *(watch or ["- aucun"])]
    print("\n".join(index[: 8 + len(notes)]))
    if is_demo():
        return 0
    (OUT / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    # one desk line per member and day in archive/desk_log.csv (the committee keeps archive/team_log.csv)
    log = team.read_log(team.DESK_LOG, desk=None)
    if not log.empty:
        log = log[log["date"].dt.date.astype(str) != now.date().isoformat()]
        log["date"] = log["date"].dt.date
        log.to_csv(team.DESK_LOG, index=False)
    team.append_log(rows, team.DESK_LOG)
    print(f"{len(notes)} notes -> {OUT.relative_to(ROOT)}, {len(rows)} team-log lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
