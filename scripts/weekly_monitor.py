"""Weekly Monitor (2 pages, PDF): scorecard, what changed this week, calendar, positioning, one chart.

MACRO_MODE=live python scripts/weekly_monitor.py
MACRO_MODE=demo python scripts/weekly_monitor.py --allow-demo   # tests/CI only; SYNTHETIC on every page
"""

from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd

import _bootstrap  # noqa: F401
from macro import figures, pipeline
from macro.config import calendar
from macro.reports import Report, out_dir
from macro.utils import is_demo
from macro.views import format_value


def build(allow_demo: bool = False) -> str:
    if is_demo() and not allow_demo:
        raise SystemExit(
            "Refusing to build a report from synthetic data (MACRO_MODE=demo). Use --allow-demo for tests only."
        )
    v = pipeline.build_views()
    gb = pipeline.growth_bundle()
    posb = pipeline.positioning_bundle()
    asof = pd.Timestamp(v["as_of"]).date()
    r = Report("Weekly Macro Tightening Monitor", f"week ending {asof}")
    r.add_page()
    r.h1(f"Weekly Monitor — week ending {asof}")
    r.para(" ".join(v["comments"].values()))
    r.h2("Scorecard")
    sc = v["scorecard"].copy()
    sc["value"] = [format_value(x, u) for x, u in zip(sc["value"], sc["unit"], strict=True)]
    r.table(
        sc[["bank", "metric", "value", "status"]],
        col_widths=[12, 104, 40, 26],
        status_col="status",
        index=False,
    )
    r.h2("What changed this week")
    ch = v["changes"].reset_index()
    ch["change"] = ch["change"].map(lambda x: f"{x:+.2f}")
    r.table(ch, col_widths=[70, 40, 30], index=False)
    nc = gb["nowcast"]
    news = gb["weekly"].iloc[-1]
    cats = {
        k.replace("news: ", ""): val for k, val in news.items() if str(k).startswith("news: ") and val == val
    }
    r.para(
        f"GDP nowcast for {nc['target']}: {nc['point']:.1f}% annualised (68% band {nc['lo68']:.1f} to {nc['hi68']:.1f}); "
        f"weekly change {v['nowcast_change']:+.2f} pp"
        + (f", driven by: {', '.join(f'{k} {x:+.2f}' for k, x in cats.items())}." if cats else ".")
    )
    r.add_page()
    r.h2("Calendar: next 14 days")
    today = asof
    ev = [e for e in calendar().events if today <= e.date <= today + dt.timedelta(days=14)]
    if ev:
        r.bullets([f"{e.date}: {e.label}" + ("" if e.verified else " (date unverified)") for e in ev])
    else:
        r.para(
            "No events in config/calendar.yaml for the next 14 days (add data releases from the official calendars)."
        )
    r.h2("Positioning snapshot (CFTC TFF, Tuesday reference date)")
    if posb["adjusted"]:
        t = posb["table"].reset_index()[["series", "net", "4w change", "percentile (3y)", "flag"]]
        r.table(t, col_widths=[86, 26, 26, 22, 22], index=False)
    r.h2("One chart that matters")
    r.image_fig(figures.nowcast_news(gb), px=(1000, 430))
    path = out_dir() / f"weekly_monitor_{asof}.pdf"
    r.output(str(path))
    return str(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-demo", action="store_true")
    print(build(ap.parse_args().allow_demo))
