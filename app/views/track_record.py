import streamlit as st

from components import chart, footer, header, show_status, theme
from macro import archive
from macro.figures import track_record_chart
from macro.pipeline import track_record
from macro.utils import is_demo

header(
    "Track record",
    "Every scheduled run archives its forecasts with the data vintage; later outcomes are compared with them.",
)
th = theme()
a = archive.read()
st.caption(
    f"Archive: `{archive.archive_path().relative_to(archive.archive_path().parents[1])}` — {len(a)} rows, "
    f"{a['data_as_of'].nunique() if len(a) else 0} vintages. Rows are never overwritten; model versions are frozen within a "
    "calendar month (see Model cards → changelog)."
)
if is_demo() and len(a):
    st.warning(
        "Demo archive: includes pseudo out-of-sample forecasts backfilled from the inflation module so this page can be "
        "exercised. The live archive only contains forecasts actually made by scheduled runs.",
    )

rows, summ = track_record()
n_eval = int(rows["actual"].notna().sum()) if len(rows) else 0
if n_eval < 2:
    st.info(
        f"{n_eval} evaluation point(s) so far. The track record appears once at least two archived forecasts have outcomes."
    )
else:
    show_status("good", f"{n_eval} archived forecasts have outcomes.")
    st.subheader("Accuracy by variable, model and horizon")
    st.dataframe(summ.round(3), use_container_width=True, hide_index=True)
    st.caption(
        "MAE and RMSE of archived point forecasts; bias = mean(outcome − forecast); coverage = share of outcomes inside the "
        "archived 68% and 90% bands (well-calibrated: about 0.68 and 0.90)."
    )
    for var in summ["variable"].unique():
        fig = track_record_chart(rows, var)
        chart(fig, rows[rows["variable"] == var], key=f"tr_{var}")
with st.expander("Raw archive"):
    st.dataframe(a.tail(500), use_container_width=True, hide_index=True)
    st.download_button("Download archive CSV", a.to_csv(index=False).encode(), "forecasts.csv", "text/csv")
footer()
