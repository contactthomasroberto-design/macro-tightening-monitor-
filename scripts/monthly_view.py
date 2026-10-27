"""Monthly Macro View (4-6 pages, PDF): regime, fans, scenarios, priced vs model, financial-conditions
gap, risks, limitations, model changes of the month.

    MACRO_MODE=live python scripts/monthly_view.py
    MACRO_MODE=demo python scripts/monthly_view.py --allow-demo   # tests/CI only
"""

from __future__ import annotations

import argparse

import pandas as pd

import _bootstrap  # noqa: F401
from macro import figures, pipeline
from macro.reports import Report, changelog_rows, out_dir
from macro.utils import is_demo
from macro.views import format_value

LIMITATIONS = (
    "Few recessions and hiking cycles; r* and the output gap are unobservable; data are revised and evaluations use latest-vintage "
    "data unless stated; structural breaks; the policy-surprise proxy mixes information effects; free data only (no OIS curve, "
    "2-year yields as priced-path proxies); scenario probabilities and paths are subjective."
)


def build(allow_demo: bool = False) -> str:
    if is_demo() and not allow_demo:
        raise SystemExit(
            "Refusing to build a report from synthetic data (MACRO_MODE=demo). Use --allow-demo for tests only."
        )
    v = pipeline.build_views()
    sb = pipeline.scenario_bundle()
    sr = v["scenario"]
    rb = pipeline.regime_bundle()
    fcb = pipeline.fincond_bundle()
    asof = pd.Timestamp(v["as_of"])
    month = asof.strftime("%Y-%m")
    t = v["template"]
    r = Report("Monthly Macro View", asof.strftime("%B %Y"))
    # page 1: executive summary
    r.add_page()
    r.h1(f"Monthly Macro View — {asof:%B %Y}")
    r.h2("View")
    r.para(t["View"])
    r.h2("Evidence")
    r.bullets(t["Evidence"])
    h = rb["history"].iloc[-1]
    r.h2("Regime")
    r.para(
        f"{h['regime']}: 4-quarter growth {h['growth']:.1f}% vs trend {h['trend']:.1f}%, core PCE {h['inflation']:.1f}%."
    )
    r.h2("Scorecard")
    sc = v["scorecard"].copy()
    sc["value"] = [format_value(x, u) for x, u in zip(sc["value"], sc["unit"], strict=True)]
    r.table(
        sc[["bank", "metric", "value", "status"]],
        col_widths=[12, 104, 40, 26],
        status_col="status",
        index=False,
    )
    # page 2: fans
    r.add_page()
    r.h2("Fan charts (central projection = mode; bands of 10% up to 90%)")
    r.image_fig(figures.fan(sb, sr, "i"), px=(1000, 440))
    r.image_fig(figures.fan(sb, sr, "pi"), px=(1000, 440))
    r.para(
        "How to read: each pair of bands adds 10% probability; outcomes outside the fan are expected about one time in ten. "
        "Skew from probability-weighted scenarios, width from the dispersion of historical errors.",
        size=8,
    )
    # page 3: scenarios and pricing
    r.add_page()
    r.h2("Scenarios (probability-weighted)")
    r.table(sr["table"].round(2), col_widths=[60, 22, 26, 26, 26, 22])
    r.h2("Probability of further 25bp moves within 4 quarters")
    r.table(sr["moves"].round(3), col_widths=[20, 50, 50])
    r.h2("Priced vs model")
    pvm = v["priced_vs_model"][
        ["bank", "item", "priced", "model (median)", "model 68% low", "model 68% high"]
    ]
    r.table(pvm.round(2), col_widths=[14, 70, 22, 26, 25, 25], index=False)
    # page 4: financial conditions and risks
    r.add_page()
    r.h2("How much tightening is left? (FCI-lite)")
    r.image_fig(figures.fci_decomposition(fcb), px=(1000, 460))
    eq = fcb["equivalences"][["central", "low (16%)", "high (84%)", "unit", "reliable"]]
    r.para(
        "Equivalences — the change in one variable that alone would close the gap (sensitivities, not forecasts):",
        size=8.5,
    )
    r.table(eq.round(1), col_widths=[60, 24, 24, 24, 16, 22])
    r.h2("Risks and what would change the view")
    r.bullets(t["Risks"] + t["What would change the view"])
    r.h2("Catalysts")
    r.bullets(t["Catalysts (calendar)"] or ["No calendar entries."])
    r.box("Limitations", LIMITATIONS)
    r.h2(f"Model changes effective {month}")
    cl = changelog_rows(month)
    if cl.empty:
        r.para("No model change this month.")
    else:
        r.table(cl, col_widths=[18, 26, 16, 60, 62], index=False)
    path = out_dir() / f"monthly_view_{month}.pdf"
    r.output(str(path))
    return str(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-demo", action="store_true")
    print(build(ap.parse_args().allow_demo))
