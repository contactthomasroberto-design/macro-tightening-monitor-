"""Module bundles: panels -> models -> Results, cached on disk.

Pages, `scripts/run_all.py` and the reports all go through these functions, so the dashboard,
the PDFs and the archive show the same numbers.
"""

from __future__ import annotations

import pandas as pd

from macro import inflation as inf
from macro import panels
from macro.config import assumptions, catalogue
from macro.data import get_series, try_series
from macro.data.vintages import LATEST_VINTAGE_LABEL
from macro.results import load_or_compute
from macro.utils import Result

INFL_TARGET_SERIES = {"US": "CPIAUCSL", "EA": "EA_HICP", "JP": "JP_CPI"}
BANK_OF = {"US": "fed", "EA": "ecb", "JP": "boj"}


def _lag(series_id: str) -> tuple[str, int]:
    s = catalogue().get(series_id)
    return s.freq, s.release_lag_days


def stamp(bundle: dict, ids: list[str], as_of) -> dict:
    """Attach provenance (source ids, as-of date) to every Result in a bundle that lacks it."""
    for v in bundle.values():
        if isinstance(v, Result):
            if not v.sources:
                v.sources = list(dict.fromkeys(ids))
            if v.as_of is None:
                v.as_of = pd.Timestamp(as_of).strftime("%Y-%m-%d") if as_of is not None else None
    return bundle


def inflation_bundle(region: str = "US", force: bool = False) -> dict:
    def compute() -> dict:
        p = panels.inflation_panel(region)
        bank = assumptions()["central_banks"][BANK_OF[region]]
        target = float(bank["inflation_target"])
        out: dict = {
            "region": region,
            "target": target,
            "panel": p,
            "decomposition": inf.decomposition(p),
            "momentum": inf.momentum(p["headline"]),
        }
        if "core" in p:
            out["momentum_core"] = inf.momentum(p["core"])
            out["persistence"] = inf.persistence(inf.annualised(p["core"], 1))
        if region == "US":
            out["underlying"] = inf.underlying(p)
        if {"food", "energy", "services", "goods"} <= set(p.columns):
            out["broadening"] = inf.broadening(p, target)
        if "core" in p and p["oil"].notna().sum() > 60:
            out["energy_passthrough"] = inf.energy_passthrough(p)
        if "gscpi" in p:
            out["supply"] = inf.supply_passthrough(p)
        if region == "US":
            exp = panels.expectations_panel()
            out["expectations"] = inf.expectations_factor(exp, inf.yoy(p["headline"]))
            out["expectations_panel"] = exp
            cie = try_series("CIE")
            out["cie_published"] = cie
        # forecasting (US and EA: enough components and a real-side gap)
        if region in ("US", "EA") and "core" in p:
            ugap = panels.unemployment_gap(region, p)
            exp_long = try_series("SPF_CPI10") if region == "US" else None
            lags = {
                "gscpi": _lag("GSCPI"),
                "ugap": _lag("UNRATE" if region == "US" else "EA_UNRATE"),
                "exp": _lag("SPF_CPI10"),
            }
            cpi_lag = catalogue().get(INFL_TARGET_SERIES[region]).release_lag_days
            inp = inf.build_inputs(p, exp_long, ugap, get_series("DCOILBRENTEU"), lags, cpi_lag=cpi_lag)
            spf = None
            if region == "US":
                spf_raw = try_series("SPF_CPI_1Y")
                if spf_raw is not None:
                    spf = inf.realtime_value(spf_raw, *_lag("SPF_CPI_1Y"), inp.X.index)
            oos = inf.pseudo_oos(inp, spf=spf)
            fc = inf.latest_forecasts(inp, oos)
            margin = float(assumptions()["inflation"]["exceed_margin_pp"])
            comb12 = fc[(fc["model"] == "COMB") & (fc["h"] == 12)].iloc[0]
            out["oos"] = oos
            out["forecasts"] = fc
            out["prob_exceed"] = {
                "threshold": target + margin,
                "margin": margin,
                "h": 12,
                "p": inf.prob_exceed(comb12["point"], comb12["sigma"], target + margin),
                "point": comb12["point"],
                "sigma": comb12["sigma"],
            }
            out["vintage_label"] = LATEST_VINTAGE_LABEL
        out["as_of"] = p["headline"].dropna().index.max()
        ids = [*panels.INFLATION_IDS[region].values(), "DCOILBRENTEU", "GSCPI"]
        if region == "US":
            ids += panels.EXPECTATION_IDS
        return stamp(out, ids, out["as_of"])

    return load_or_compute(f"inflation:{region}", compute, force=force)


def as_of_str(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m") if ts is not None else "n/a"
