"""Module bundles: panels -> models -> Results, cached on disk.

Pages, `scripts/run_all.py` and the reports all go through these functions, so the dashboard,
the PDFs and the archive show the same numbers.
"""

from __future__ import annotations

import pandas as pd

from macro import inflation as inf
from macro import panels
from macro import policy as pol
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


BANKS = ("fed", "ecb", "boj")
BANK_REGION = {"fed": "US", "ecb": "EA", "boj": "JP"}


def policy_bundle(bank: str = "fed", force: bool = False) -> dict:
    """Heavy, parameter-free parts of the policy module (rule prescriptions are cheap and are
    recomputed in the page with the user's parameters)."""

    def compute() -> dict:
        pp = panels.policy_panel(bank)
        q = pp["quarterly"]
        rstar_pub = {}
        for sid in pp["ids"]["rstar"]:
            s = try_series(sid)
            if s is not None and not s.dropna().empty:
                rstar_pub[sid] = {
                    "value": float(s.dropna().iloc[-1]),
                    "date": s.dropna().index[-1],
                    "series": s,
                }
        out = {
            "bank": bank,
            "panel": pp,
            "rstar_published": rstar_pub,
            "rf_full": pol.reaction_function(q),
            "rf_pre2008": pol.reaction_function(q, end="2007-12-31"),
            "rf_post2008": pol.reaction_function(q, start="2008-01-01"),
            "rf_rolling": pol.rolling_reaction(q),
        }
        last = pp["monthly"].dropna(subset=["i", "pi"]).iloc[-1]
        out["current"] = {
            "date": pp["monthly"].dropna(subset=["i", "pi"]).index[-1],
            "i": float(last["i"]),
            "pi": float(last["pi"]),
            "y": float(pp["monthly"]["y"].dropna().iloc[-1]) if pp["monthly"]["y"].notna().any() else 0.0,
            "u": float(last["u"]) if "u" in last and last["u"] == last["u"] else None,
            "ustar": float(pp["monthly"]["ustar"].dropna().iloc[-1])
            if "ustar" in pp["monthly"] and pp["monthly"]["ustar"].notna().any()
            else None,
            "y2": float(pp["y2"].dropna().iloc[-1]) if pp["y2"] is not None else None,
        }
        out["as_of"] = out["current"]["date"]
        ids = [pp["ids"][k] for k in ("rate", "infl", "unemp", "ustar", "gdp", "pot", "y2") if k in pp["ids"]]
        return stamp(out, ids + pp["ids"]["rstar"], out["as_of"])

    return load_or_compute(f"policy:{bank}", compute, force=force)


def cross_bank_bundle(force: bool = False) -> dict:
    def compute() -> dict:
        rates = pd.DataFrame({b: panels.monthly(panels.POLICY_IDS[b]["rate"]) for b in BANKS}).dropna()
        sync = pol.synchronisation(rates)
        us2 = get_series("DGS2")
        ea2 = try_series("EA_YC_2Y")
        fx = {}
        if ea2 is not None:
            diff = (ea2 - us2.reindex(ea2.index)).dropna()
            fx["EURUSD"] = {
                "beta": pol.fx_differential_beta(get_series("EURUSD"), diff),
                "diff": diff,
                "label": "EA 2Y AAA minus US 2Y",
            }
        us10, jp10 = get_series("DGS10"), try_series("JP_10Y")
        if jp10 is not None:
            d = (panels.monthly("DGS10") - jp10).dropna()
            dd = d.resample("D").interpolate().reindex(us10.index).ffill().dropna()
            fx["USDJPY"] = {
                "beta": pol.fx_differential_beta(get_series("USDJPY"), dd),
                "diff": dd,
                "label": "US 10Y minus JGB 10Y (monthly, interpolated)",
            }
        return {"rates": rates, "sync": sync, "fx": fx, "as_of": rates.index[-1]}

    return load_or_compute("policy:cross_bank", compute, force=force)


def as_of_str(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m") if ts is not None else "n/a"
