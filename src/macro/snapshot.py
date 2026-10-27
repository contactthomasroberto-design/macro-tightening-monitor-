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
    return out
