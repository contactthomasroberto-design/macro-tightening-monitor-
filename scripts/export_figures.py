"""LinkedIn exports (BRIEF §11): PNG at 1200x627 and a carousel PDF. Titles state the finding,
footers carry source, as-of date and the repository link. Refuses to run on synthetic data.

    MACRO_MODE=live python scripts/export_figures.py
"""

from __future__ import annotations

from fpdf import FPDF

import _bootstrap  # noqa: F401
from macro import figures, pipeline
from macro.config import ROOT
from macro.reports import ensure_browser, out_dir
from macro.utils import DISCLAIMER, is_demo

REPO = "github.com/contactthomasroberto-design/macro-tightening-monitor-"
W, H = 1200, 627


def collect() -> dict:
    gb = pipeline.growth_bundle()
    sb = pipeline.scenario_bundle()
    sr = pipeline.scenario_results(sb, sb["base_weights"])
    figs = {
        "1_policy_behind_the_curve": figures.policy_rules(pipeline.policy_bundle("fed")),
        "2_how_much_tightening_left": figures.fci_decomposition(pipeline.fincond_bundle()),
        "3_growth_at_risk_recession": figures.recession_and_gar(gb),
        "4_term_premium_sovereigns": figures.term_premium_and_spreads(pipeline.curves_bundle()),
        "5_policy_fan": figures.fan(sb, sr, "i"),
    }
    rows, summ = pipeline.track_record()
    if not summ.empty and rows["actual"].notna().sum() >= 2:
        var = summ.iloc[0]["variable"]
        figs["6_track_record"] = figures.track_record_chart(rows, var)
    return figs


def main() -> int:
    if is_demo():
        raise SystemExit(
            "export_figures.py refuses to run in demo mode: LinkedIn figures must come from real data."
        )
    ensure_browser()
    d = out_dir() / "linkedin"
    d.mkdir(parents=True, exist_ok=True)
    pngs = []
    for name, fig in collect().items():
        fig.add_annotation(
            text=f"{REPO} · {DISCLAIMER}",
            xref="paper",
            yref="paper",
            x=1,
            y=0,
            yanchor="top",
            yshift=-66,
            xanchor="right",
            showarrow=False,
            font={"size": 9, "color": "#6a737d"},
        )
        fig.update_layout(margin={"b": 110})
        path = d / f"{name}.png"
        fig.write_image(str(path), width=W, height=H, scale=1)
        fig.write_image(
            str(ROOT / "docs" / "figures" / f"{name}.png"), width=W, height=H, scale=1
        )  # README results
        pngs.append(path)
        print("wrote", path)
    pdf = FPDF(orientation="L", unit="pt", format=(H, W))
    for p in pngs:
        pdf.add_page()
        pdf.image(str(p), x=0, y=0, w=W, h=H)
    pdf.output(str(d / "carousel.pdf"))
    print("wrote", d / "carousel.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
