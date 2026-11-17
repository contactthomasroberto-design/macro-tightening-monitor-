from pathlib import Path

import pandas as pd
import streamlit as st

from components import footer, header, sidebar_controls
from macro import research_tracker as rt
from macro.config import ROOT
from portfolio_ui import DISCLAIMER, bundle, name

header(
    "Research",
    "What banks, asset managers and hedge funds publish, compared with the fund's signals; the research team's "
    "daily notes and the evening reports.",
)
ctl = sidebar_controls()
b = bundle()

# ------------------------------------------------------------------ consensus vs us
st.subheader("Published consensus against our signals")
arch = rt.read_archive()
cons = rt.consensus(arch) if not arch.empty else pd.DataFrame()
views = pd.DataFrame(b["views"]).mean(axis=1)
hv = pd.DataFrame(b["views"]).get("house")
rows = []
for a in sorted(set(cons.index) | set(hv.dropna().index if hv is not None else [])):
    rows.append(
        {
            "instrument": name(b, a),
            "house views (curated)": hv.get(a) if hv is not None else None,
            "headlines, 30 days": cons["net stance"].get(a) if not cons.empty else None,
            "mentions": cons["mentions"].get(a) if not cons.empty else None,
            "our signals (average)": views.get(a),
            "our weight": b["target"].get(a, 0.0),
        }
    )
if rows:
    t = pd.DataFrame(rows).set_index("instrument")
    st.dataframe(
        t.style.format(
            {
                "house views (curated)": "{:+.2f}",
                "headlines, 30 days": "{:+.2f}",
                "mentions": "{:.0f}",
                "our signals (average)": "{:+.2f}",
                "our weight": "{:+.1%}",
            },
            na_rep="",
        ),
        use_container_width=True,
    )
st.caption(
    "House views: dated, sourced stances recorded in config/house_views.yaml (they enter the allocation with a "
    "confidence of 10% for six months). Headlines: stances extracted from explicit wording in publications collected "
    "every two hours (research tracker). A disagreement is information, not an instruction."
)

# ------------------------------------------------------------------ house views
st.subheader("Outlooks on file")
for v in sorted(b.get("house_views", []), key=lambda x: str(x["date"]), reverse=True):
    st.markdown(
        f"**{v['institution']}** — [{v['title']}]({v['url']}) ({v['date']})  \n{v.get('summary', '')}  \n"
        + "<small>"
        + ", ".join(f"{name(b, a)} {s:+g}" for a, s in v.get("stances", {}).items())
        + "</small>",
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------------ latest publications
st.subheader("Latest publications collected")
if arch.empty:
    st.info(
        "The research tracker's first run happens in the next portfolio-monitor workflow (every two hours)."
    )
else:
    only = st.toggle("Only those with an explicit stance", value=True, key="rt_only")
    d = arch[arch["stances"].map(bool)] if only else arch
    d = d.sort_values("first_seen", ascending=False).head(60)
    for _, r in d.iterrows():
        st_ = ", ".join(f"{name(b, k)} {'+' if v > 0 else '−'}" for k, v in r["stances"].items())
        when = f"{r['published']:%d %b}" if pd.notna(r["published"]) else ""
        st.markdown(
            f"**{r['institution']}** · [{r['title']}]({r['link']}) <small>{when}{' · ' + st_ if st_ else ''}</small>",
            unsafe_allow_html=True,
        )

# ------------------------------------------------------------------ notes and reports
st.subheader("Research notes and evening reports")
for label, folder in (
    ("Research team notes", "docs/research/daily"),
    ("Evening reports", "docs/reports/daily"),
):
    files = sorted(Path(ROOT / folder).glob("*.md"), reverse=True)
    with st.expander(f"{label} ({len(files)})", expanded=False):
        if not files:
            st.markdown("None yet: the first one is written tonight.")
        for f in files[:1]:
            st.markdown(f.read_text(encoding="utf-8"))
        if len(files) > 1:
            st.caption("Earlier: " + ", ".join(f.stem for f in files[1:15]))
st.caption(DISCLAIMER)
footer()
