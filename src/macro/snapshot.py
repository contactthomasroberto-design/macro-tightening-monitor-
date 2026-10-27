"""Key scalar outputs on demo data, used by the regression test (tests/test_regression_demo.py).

A change in any of these numbers means a model or the simulator changed: update the snapshot
deliberately with `UPDATE_SNAPSHOT=1 pytest tests/test_regression_demo.py` and log the reason.
"""

from __future__ import annotations

from macro import pipeline


def collect() -> dict[str, float]:
    out: dict[str, float] = {}
    b = pipeline.inflation_bundle("US")
    out["infl_US_headline_last"] = float(b["decomposition"]["headline"].dropna().iloc[-1])
    out["infl_US_persistence_rho"] = float(b["persistence"].value)
    out["infl_US_passthrough"] = float(b["energy_passthrough"].value)
    out["infl_US_comb_rmse_h12"] = float(b["oos"]["scores"][12].loc["COMB", "rmse"])
    out["infl_US_prob_exceed"] = float(b["prob_exceed"]["p"])
    p = pipeline.policy_bundle("fed")
    rf = p["rf_full"].value
    out["policy_fed_rf_b"] = float(rf.loc["b (inflation)", "estimate"])
    out["policy_fed_rf_rho"] = float(rf.loc["rho", "estimate"])
    f = pipeline.fincond_bundle()
    out["fincond_fci1y_last"] = float(f["fci_1y"].value.iloc[-1])
    out["fincond_gap"] = float(f["gap"]["gap"])
    c = pipeline.curves_bundle()
    out["curves_2s10s_last"] = float(c["spreads"]["2s10s"].iloc[-1])
    out["curves_duration_share"] = float(c["duration"].value)
    return out
