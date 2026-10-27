import pandas as pd
import streamlit as st

from components import footer, header, show_status
from macro.data import load_demo_into_store, store
from macro.data.health import health_table, reference_today
from macro.utils import is_demo

header("Data health", "Freshness, coverage and fetch status of every catalogue series.")


@st.cache_data(ttl=600, show_spinner="Checking cache…")
def _table(mode: str) -> pd.DataFrame:
    st_ = store()
    if is_demo() and st_.last_fetched("DGS10") is None:
        load_demo_into_store(st_)
    return health_table(st_)


h = _table("demo" if is_demo() else "live")
counts = h["status"].value_counts()
cols = st.columns(4)
for c, lvl in zip(cols, ["good", "warning", "serious", "critical"], strict=True):
    c.metric(lvl.capitalize(), int(counts.get(lvl, 0)))

st.caption(
    f"Reference date {reference_today()} · stale = last observation older than one period + release lag + slack · "
    "serious = last fetch failed (cached copy in use) · critical = no data."
)
bad = h[h["status"] != "good"]
if not bad.empty:
    for _, r in bad.iterrows():
        msg = f"`{r['id']}` ({r['source']}) last obs {r['last_obs']}, age {r['age_days']} d (max {r['max_age_days']})"
        if r["last_error"]:
            msg += f" — last error: {r['last_error']}"
        show_status(r["status"], msg)

n_verify = int(h["verify_flag"].sum())
st.warning(
    f"{n_verify} series carry a `verify` flag in config/series.yaml: their ID, units or freshness has not yet been "
    "confirmed against the live source (run `make test-live`).",
    icon="🔎",
)
region = st.multiselect("Region", sorted(h["region"].unique()), default=sorted(h["region"].unique()))
st.dataframe(h[h["region"].isin(region)], use_container_width=True, hide_index=True)
st.download_button("Download CSV", h.to_csv(index=False).encode(), "data_health.csv", "text/csv")
with st.expander("Fetch log (latest 200)"):
    st.dataframe(store().fetch_log(200), use_container_width=True, hide_index=True)
footer()
