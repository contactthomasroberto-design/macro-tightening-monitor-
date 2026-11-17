"""Score the latest headlines with FinBERT and append them to archive/news_scored.csv.

MACRO_MODE=live python scripts/score_news.py            # score and archive
MACRO_MODE=live python scripts/score_news.py --issue    # also open an issue on an extreme holding score

Runs in the portfolio-monitor workflow (needs requirements-news.txt and CPU torch). An alert fires
when a holding's news score is beyond ±0.6 with at least 3 fresh, distinct headlines: information for
the owner, not a trade (the news family's weight in the allocation follows research log H32)."""

from __future__ import annotations

import argparse
import json
import subprocess

import pandas as pd

import _bootstrap  # noqa: F401
from macro import news
from macro import news_scoring as ns
from macro.config import ROOT

STATE = ROOT / "archive" / "news_alerts.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", action="store_true")
    args = ap.parse_args()
    cfg = news.load()
    df, failed = news.headlines(cfg)
    if failed:
        print("feeds unavailable:", ", ".join(failed))
    scored = ns.score(df, ns.finbert(), cfg)
    n = ns.append_archive(scored)
    print(f"{len(df)} headlines, {len(scored)} tagged, {n} new -> {ns.ARCHIVE.relative_to(ROOT)}")
    from macro import research_tracker as rt

    pubs, rfail = rt.collect()
    print(
        f"research tracker: {len(pubs)} publications, {rt.append_archive(pubs)} new; feeds failed: {list(rfail)}"
    )
    arch = ns.read_archive()
    recent = arch[arch["first_seen"] >= arch["first_seen"].max() - pd.Timedelta(days=3)]
    a = ns.asset_scores(recent, cfg)
    print(a.round(3).to_string())
    hot = a[(a["news score"].abs() >= 0.6) & (a["headlines"] >= 3) & (a.index != "MARKET")]
    prev = json.loads(STATE.read_text()) if STATE.exists() else {}
    fresh = {k: round(float(v), 2) for k, v in hot["news score"].items() if k not in prev}
    if fresh and args.issue:
        body = "\n".join(f"- **{k}**: news score {v:+.2f}" for k, v in fresh.items())
        body += "\n\nHeadlines: Portfolio → News. Information only: no position changes on news alone."
        subprocess.run(
            ["gh", "issue", "create", "--title", f"News alert: {', '.join(fresh)}", "--body", body],
            check=False,
        )
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({k: round(float(v), 2) for k, v in hot["news score"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
