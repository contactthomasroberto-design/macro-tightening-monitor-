"""Module bundles: panels -> models -> Results, cached on disk.

Pages, `scripts/run_all.py` and the reports all go through these functions, so the dashboard,
the PDFs and the archive show the same numbers.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from macro import curves as cv
from macro import fans, panels
from macro import fincond as fc
from macro import growth as gr
from macro import history as hist
from macro import inflation as inf
from macro import policy as pol
from macro import positioning as pos
from macro import recession as rc
from macro import regimes as rg
from macro import scenarios as scn
from macro import transmission as tr
from macro import views as vw
from macro.config import assumptions, catalogue
from macro.data import get_series, try_series
from macro.data.vintages import LATEST_VINTAGE_LABEL
from macro.results import load_or_compute
from macro.utils import Result, ols_hac

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


def fincond_bundle(force: bool = False) -> dict:
    def compute() -> dict:
        pn = panels.fincond_panel()
        lv, gdp = pn["levels_q"], pn["gdp_q"]
        f1 = fc.fci_lite(lv, gdp, lookback=4)
        f3 = fc.fci_lite(lv, gdp, lookback=12)
        a = assumptions()["fincond"]
        gap_now = float(pn["output_gap_q"].dropna().iloc[-1])
        g = fc.gap_to_neutral(float(f1.value.iloc[-1]), gap_now, int(a["output_gap_closure_quarters"]))
        eq = fc.equivalences(g["gap"], f1.extra["beta_draws"], float(a["fci_multiplier_uncertainty"]))
        # projected FCI under simple paths (scenario engine paths are added on the Scenarios page)
        last_q = lv.dropna().index[-1]
        fut = pd.date_range(last_q + pd.offsets.QuarterBegin(1), periods=8, freq="QS")
        y2 = float(panels.monthly("DGS2").dropna().iloc[-1])
        pr = float(lv["policy_rate"].dropna().iloc[-1])
        y10 = float(lv["y10"].dropna().iloc[-1])
        eqty = float(lv["equity"].dropna().iloc[-1])
        ramp = np.linspace(0, 1, 4).tolist() + [1.0] * 4
        paths = {
            "Unchanged rates and prices": {},
            "Policy rate moves to the 2Y-yield proxy": {
                "policy_rate": pd.Series([pr + (y2 - pr) * w for w in ramp], index=fut)
            },
            "10Y yield +50bp": {"y10": pd.Series([y10 + 0.5 * w for w in ramp], index=fut)},
            "Equities -10%": {"equity": pd.Series([eqty * (1 - 0.10 * w) for w in ramp], index=fut)},
        }
        proj = pd.DataFrame({k: fc.project_fci(lv, f1.extra["betas"]["beta"], v) for k, v in paths.items()})
        stat = fc.statistical_fci(pn["stat_panel"])
        indices = {
            "FCI-lite 1y (this project)": f1.value,
            "FCI-lite 3y (this project)": f3.value,
            "Chicago Fed NFCI": pn["nfci"],
            "Statistical factor (this project)": stat,
        }
        if pn["fcig"] is not None:
            indices["Fed Board FCI-G 1y (published)"] = pn["fcig"]
        comp = fc.index_comparison(indices)
        q_idx = pd.concat({k: v.resample("QS").mean() for k, v in indices.items()}, axis=1)
        out = {
            "panel": pn,
            "fci_1y": f1,
            "fci_3y": f3,
            "gap": g,
            "equivalences": eq,
            "projection": proj,
            "statistical": stat,
            "comparison": comp,
            "indices_q": q_idx,
            "as_of": lv.dropna().index[-1],
            "fcig_available": pn["fcig"] is not None,
        }
        ids = [*panels.FCI_IDS.values(), "GDPC1", "GDPPOT", "NFCI", "BAA10Y", "VIXCLS", "T10Y3M", "DGS2"]
        return stamp(out, ids, out["as_of"])

    return load_or_compute("fincond:US", compute, force=force)


def curves_bundle(force: bool = False) -> dict:
    def compute() -> dict:
        y = pd.DataFrame(
            {
                "3m": get_series("DGS3MO"),
                "2y": get_series("DGS2"),
                "5y": get_series("DGS5"),
                "10y": get_series("DGS10"),
                "30y": get_series("DGS30"),
            }
        ).dropna()
        spreads = cv.us_spreads(y)
        tp = {
            k: s
            for k, s in (
                ("Kim-Wright (Fed Board)", try_series("THREEFYTP10")),
                ("ACM (NY Fed)", try_series("ACMTP10")),
            )
            if s is not None
        }
        dec = cv.ten_year_decompositions(get_series("DGS10"), get_series("DFII10"), get_series("T10YIE"), tp)
        reg = cv.classify_regime(get_series("DGS2"), get_series("DGS10"))
        hiking = get_series("DFEDTARU").diff(126) > 0  # policy rate higher than ~6 months earlier
        freq = cv.regime_frequencies(reg, hiking)
        de = panels.monthly("DE_10Y")
        sov = (
            pd.DataFrame(
                {
                    "OAT-Bund": panels.monthly("FR_10Y") - de,
                    "BTP-Bund": panels.monthly("IT_10Y") - de,
                    "Bonos-Bund": panels.monthly("ES_10Y") - de,
                }
            ).dropna()
            * 100
        )
        stress = cv.sovereign_stress(sov)
        ea = pd.DataFrame(
            {
                "AAA 2Y": panels.monthly("EA_YC_2Y", optional=True),
                "AAA 10Y": panels.monthly("EA_YC_10Y", optional=True),
                "Bund 10Y": de,
            }
        )
        y10 = pd.DataFrame(
            {
                "US": panels.monthly("DGS10"),
                "DE": de,
                "JP": panels.monthly("JP_10Y"),
                "FR": panels.monthly("FR_10Y"),
                "IT": panels.monthly("IT_10Y"),
            }
        ).dropna()
        dur = cv.duration_factor(y10)
        jp = panels.monthly("JP_10Y")
        out = {
            "yields": y,
            "spreads": spreads,
            "decomp": dec,
            "regimes": reg,
            "regime_freq": freq,
            "sovereign": sov,
            "stress": stress,
            "ea_curve": ea,
            "y10": y10,
            "duration": dur,
            "jgb": jp,
            "jgb_reference": assumptions()["market_pricing"].get("jgb_10y_reference"),
            "as_of": y.index[-1],
        }
        ids = [
            "DGS3MO",
            "DGS2",
            "DGS5",
            "DGS10",
            "DGS30",
            "DFII10",
            "T10YIE",
            "THREEFYTP10",
            "ACMTP10",
            "DE_10Y",
            "FR_10Y",
            "IT_10Y",
            "ES_10Y",
            "JP_10Y",
            "EA_YC_2Y",
            "EA_YC_10Y",
        ]
        return stamp(out, ids, out["as_of"])

    return load_or_compute("curves:all", compute, force=force)


def growth_bundle(force: bool = False, eval_start: str = "2008Q1") -> dict:
    """Nowcast (DFM + news), real-time evaluation, Growth-at-Risk, recession probabilities."""
    from macro.data.health import reference_today

    def compute() -> dict:
        today = pd.Timestamp(reference_today())
        raw = panels.growth_raw()

        def vfn(d):
            return panels.growth_vintage(raw, d)

        M, Q = vfn(today)
        res = gr.fit_dfm(M, Q)
        target = Q[gr.GDP_ID].dropna().index.max() + 1
        now = gr.nowcast(res, M, Q, target)
        weekly = gr.weekly_history(res, vfn, today, weeks=12)
        gdp_g = 400 * np.log(raw[gr.GDP_ID]).diff()
        gdp_g.index = pd.PeriodIndex(gdp_g.index, freq="Q")
        last_pub = Q[gr.GDP_ID].dropna().index.max()
        quarters = pd.period_range(eval_start, last_pub, freq="Q")
        spf = try_series("SPF_RGDP_CQ")
        if spf is not None:
            spf.index = pd.PeriodIndex(spf.index, freq="Q")
        ev_rt = gr.realtime_evaluation(vfn, gdp_g, quarters, spf_cq=spf)
        # external, published nowcasts for the same target quarter (benchmarks, not inputs)
        external: dict = {}
        if (gn := try_series("GDPNOW")) is not None:
            gn.index = pd.PeriodIndex(gn.index, freq="Q")
            if target in gn.index:
                external["Atlanta Fed GDPNow"] = float(gn.loc[target])
        if (wei := try_series("WEI")) is not None and not wei.dropna().empty:
            external["Weekly Economic Index (y/y, latest week)"] = float(wei.dropna().iloc[-1])
            external["WEI week"] = wei.dropna().index[-1].date().isoformat()
        nfci_q = panels.monthly("NFCI").resample("QS").mean()
        gdp_q = raw[gr.GDP_ID]
        gar = {h: gr.growth_at_risk(gdp_q, nfci_q, h) for h in (1, 4)}
        gar_bt = {h: gr.gar_backtest(gdp_q, nfci_q, h) for h in (1, 4)}
        rdf, rec = panels.recession_panel("US")
        rmod = rc.recession_model(rdf, rec)
        sahm = rc.sahm(panels.monthly("UNRATE"))
        ea = None
        try:
            edf, erec = panels.recession_panel("EA")
            cols = ["spread_2y10y", "d6_unemp"]
            if edf[["y", *cols]].dropna()["y"].sum() >= 2:
                ea = {
                    "current": rc.current_probability(edf, cols),
                    "episodes": rc.episodes(erec),
                    "n": len(edf[["y", *cols]].dropna()),
                    "cols": cols,
                }
        except Exception as exc:  # optional block: report, do not fail the bundle
            ea = {"error": str(exc)}
        out = {
            "dfm": {
                "params": res.params,
                "llf": float(res.llf),
                "nobs": int(res.nobs),
                "factors": gr.factor_structure(),
            },
            "nowcast": now,
            "external_nowcasts": external,
            "weekly": weekly,
            "realtime": ev_rt,
            "gar": gar,
            "gar_backtest": gar_bt,
            "recession": rmod,
            "sahm": sahm,
            "ea_recession": ea,
            "as_of": today,
            "gdp_growth": gdp_g,
            "vintage_label": LATEST_VINTAGE_LABEL,
        }
        ids = [
            *gr.GROWTH_SPEC,
            gr.GDP_ID,
            "NFCI",
            "T10Y3M",
            "BAA10Y",
            "UNRATE",
            "USREC",
            "SPF_RGDP_CQ",
            "GDPNOW",
            "WEI",
        ]
        return stamp(out, ids, today)

    return load_or_compute("growth:US", compute, force=force)


def history_bundle(force: bool = False) -> dict:
    """Historical tightening cycles from the Global Macro Database (annual, cross-country)."""
    from macro.data import gmd
    from macro.data.health import reference_today

    panel, version = gmd.load_panel()
    last = gmd.last_actual_year(reference_today())

    def compute() -> dict:
        cyc = hist.add_buckets(hist.find_cycles(panel, last))
        cyc_ex = hist.add_buckets(hist.find_cycles(panel, last, ignore_years=(2020,)))
        cur = hist.current_position(panel, last)
        similar = {
            iso: hist.similar_share(
                cyc, r["rise (pp)"], r["inflation at peak"], exclude=(str(iso), int(r["trough"]))
            )
            for iso, r in cur.iterrows()
        }
        return {
            "version": version,
            "last_actual_year": last,
            "cycles": cyc,
            "by_era": hist.summarise(cyc, "era"),
            "by_rise": hist.summarise(cyc, "rise bucket"),
            "by_inflation": hist.summarise(cyc, "inflation at peak"),
            "by_era_ex2020": hist.summarise(cyc_ex, "era"),
            "logit": hist.logit_recession(cyc),
            "current": cur,
            "similar": similar,
            "n_countries": int(cyc["ISO3"].nunique()) if len(cyc) else 0,
            "citation": gmd.CITATION,
            "licence": gmd.LICENCE,
        }

    return load_or_compute(f"history:GMD_{version}", compute, force=force)


AI_BASKET = ["NVDA", "MSFT", "GOOGL", "AMZN", "META"]


def ai_basket() -> pd.Series | None:
    """Equal-weight index of available AI-leader stocks (daily rebalanced: mean of log returns)."""
    rets = {t: np.log(s).diff() for t in AI_BASKET if (s := try_series(t)) is not None}
    if not rets:
        return None
    r = pd.DataFrame(rets).mean(axis=1, skipna=True).dropna()
    return 100 * np.exp(r.cumsum())


def transmission_bundle(force: bool = False) -> dict:
    def compute() -> dict:
        spx = get_series("SPX")
        eq_m = 100 * np.log(spx.resample("MS").last()).diff()
        d10_m = get_series("DGS10").resample("MS").last().diff()
        core = panels.monthly("CPILFESL")
        core_yoy = 100 * (core / core.shift(12) - 1)
        sb = tr.stock_bond_by_regime(eq_m, d10_m, core_yoy)
        sb_roll = tr.rolling_stock_bond(eq_m, d10_m)
        events = tr.policy_events(get_series("DFEDTARU"))
        prices = {
            "2Y yield": get_series("DGS2"),
            "10Y yield": get_series("DGS10"),
            "S&P 500": spx,
            "Euro Stoxx 50": try_series("SX5E"),
            "Semiconductors (SOX)": try_series("SOX"),
            "Broad dollar": get_series("DTWEXBGS"),
        }
        prices = {k: v for k, v in prices.items() if v is not None}  # optional Yahoo series may be missing
        kinds = {k: ("yield" if "yield" in k else "price") for k in prices}
        es = {t: tr.event_study(prices, kinds, events.index[events["type"] == t]) for t in ("hike", "cut")}
        # weekly returns and real-yield / breakeven changes
        w = lambda s: s.resample("W-FRI").last()  # noqa: E731
        assets = {"S&P 500": spx}
        sox = try_series("SOX")
        if sox is not None:
            assets["Semiconductors (SOX)"] = sox
        ai = ai_basket()
        if ai is not None:
            assets["AI leaders (equal weight)"] = ai
        ret_w = pd.DataFrame({k: 100 * np.log(w(v)).diff() for k, v in assets.items()})
        d_real = w(get_series("DFII10")).diff()
        d_be = w(get_series("T10YIE")).diff()
        regime = pd.cut(
            core_yoy, [-np.inf, 2, 3, np.inf], labels=["core < 2%", "core 2-3%", "core > 3%"]
        ).astype(str)
        regime = regime.where(core_yoy.notna())
        betas = tr.real_yield_betas(ret_w, d_real, d_be, regime)
        roll = {k: tr.rolling_real_beta(ret_w[k], d_real, d_be) for k in ret_w}
        d2 = get_series("DGS2").diff()
        surprise = d2.reindex(events.index)
        lp = tr.local_projections_surprise(
            {
                "10Y yield": (get_series("DGS10"), "yield"),
                "S&P 500": (spx, "price"),
                "Broad dollar": (get_series("DTWEXBGS"), "price"),
            },
            surprise,
        )
        us2 = panels.monthly("DGS2")
        fx = {}
        if (ea2 := panels.monthly("EA_YC_2Y", optional=True)) is not None:
            fx["EURUSD"] = tr.fx_differential_model(
                panels.monthly("EURUSD", how="last"), (ea2 - us2).dropna(), "EURUSD"
            )
            fx["EURUSD"].extra["diff_label"] = "EA 2Y AAA minus US 2Y (pp)"
        if (jp10 := panels.monthly("JP_10Y", optional=True)) is not None:
            fx["USDJPY"] = tr.fx_differential_model(
                panels.monthly("USDJPY", how="last"), (panels.monthly("DGS10") - jp10).dropna(), "USDJPY"
            )
            fx["USDJPY"].extra["diff_label"] = "US 10Y minus JGB 10Y (pp)"
        out = {
            "stock_bond": sb,
            "stock_bond_rolling": sb_roll,
            "events": events,
            "event_study": es,
            "real_betas": betas,
            "rolling_betas": roll,
            "lp": lp,
            "fx": fx,
            "as_of": spx.index[-1],
            "n_events": events["type"].value_counts().to_dict(),
        }
        ids = [
            "SPX",
            "SX5E",
            "SOX",
            "DGS2",
            "DGS10",
            "DFII10",
            "T10YIE",
            "DTWEXBGS",
            "DFEDTARU",
            "CPILFESL",
            "EURUSD",
            "USDJPY",
            "EA_YC_2Y",
            "JP_10Y",
            *AI_BASKET,
        ]
        return stamp(out, ids, out["as_of"])

    return load_or_compute("transmission:all", compute, force=force)


def positioning_bundle(force: bool = False) -> dict:
    def compute() -> dict:
        ids = list(pos.LABELS)
        prices = {k: get_series(k) for k in ("SPX", "EURUSD", "USDJPY")}
        adj = {}
        for sid in ids:
            s = try_series(sid)
            if s is not None:
                adj[sid] = pos.adjust(s, sid, prices)
        tab, pct = pos.positioning_table(adj)
        lag = catalogue().get(ids[0]).release_lag_days
        last = max(s.index[-1] for s in adj.values()) if adj else None
        return {"adjusted": adj, "table": tab, "percentiles": pct, "as_of": last, "lag_days": lag}

    return load_or_compute("positioning:all", compute, force=force)


def scenario_bundle(force: bool = False, n_per: int = 10_000) -> dict:
    """Quarterly US engine, Monte Carlo per scenario (mixed later with the user's probabilities)."""
    from macro.config import scenarios as load_scenarios

    def compute() -> dict:
        a = assumptions()
        pce = panels.monthly("PCEPILFE")
        q = pd.DataFrame(
            {
                "pi": (100 * (pce / pce.shift(12) - 1)).resample("QS").mean(),
                "u": panels.monthly("UNRATE").resample("QS").mean(),
                "ustar": panels.monthly("NROU").resample("QS").mean(),
                "oil4": (100 * np.log(panels.monthly("DCOILBRENTEU").resample("QS").mean())).diff(4),
            }
        )
        coefs, resid_pi, n_pc, pc_tab = scn.estimate_phillips(q)
        pb = policy_bundle("fed")
        rf = pb["rf_full"]
        t = rf.value["estimate"]
        qi = pb["panel"]["quarterly"]["i"]
        resid_i = (qi - rf.extra["fitted"]).dropna().to_numpy()
        du = q["u"].diff().loc["1990":]
        ar = ols_hac(du, du.shift(1).to_frame("lag"))
        resid_du = ar.resid.clip(*ar.resid.quantile([0.025, 0.975])).to_numpy()
        lo, hi = a["rstar"]["user_range"]
        cb = a["central_banks"]["fed"]
        init_q = q.dropna(subset=["pi", "u"]).iloc[-1]
        tp = try_series("ACMTP10") if try_series("ACMTP10") is not None else try_series("THREEFYTP10")
        p = scn.EngineParams(
            c=coefs["c"],
            rho=coefs["rho"],
            kappa=coefs["kappa"],
            theta=coefs["theta"],
            resid_pi=resid_pi,
            rf_rho=float(t["rho"]),
            rf_a=float(t["a"]),
            rf_b=float(t["b (inflation)"]),
            rf_c=float(t["c (output gap)"]) if t["c (output gap)"] == t["c (output gap)"] else 0.0,
            resid_i=resid_i,
            resid_du=resid_du,
            okun=float(a["rules"]["unemployment_gap"]["okun"]),
            ustar=float(q["ustar"].dropna().iloc[-1]),
            rstar=float((lo + hi) / 2),
            pi_star=float(cb["inflation_target"]),
            max_step_q=2 * float(cb["max_step_bp"]) / 100,
            n_obs=n_pc,
        )
        init = {
            "pi": float(init_q["pi"]),
            "u": float(init_q["u"]),
            "i": float(pb["current"]["i"]),
            "oil4_base": float(q["oil4"].dropna().iloc[-1]),
            "tp": float(tp.dropna().iloc[-1]) if tp is not None else 0.0,
        }
        sc = load_scenarios()
        scen = {k: v.model_dump() for k, v in sc.scenarios.items()}
        sims = scn.run_monte_carlo(p, init, scen, n_per=n_per, quarters=sc.horizon_quarters, seed=1)
        last_q = init_q.name
        fut = pd.date_range(last_q + pd.offsets.QuarterBegin(1), periods=sc.horizon_quarters, freq="QS")
        # market-mapping betas: quarterly changes of 2Y / 10Y on changes in the policy rate
        qq = (
            pd.DataFrame(
                {
                    "i": qi,
                    "y2": panels.monthly("DGS2").resample("QS").mean(),
                    "y10": panels.monthly("DGS10").resample("QS").mean(),
                }
            )
            .diff()
            .dropna()
        )
        b2 = ols_beta(qq["y2"], qq["i"])
        b10 = ols_beta(qq["y10"], qq["i"])
        pot = get_series("GDPPOT")
        g_star = float(100 * np.log(pot).diff(4).dropna().iloc[-1])
        y2_now = float(panels.monthly("DGS2").dropna().iloc[-1])
        priced, priced_src = pol.priced_rate_proxy(
            y2_now, init["i"], panels.market_priced("fed", a["market_pricing"].get("fed_terminal_rate"))
        )
        out = {
            "params": p,
            "init": init,
            "scenarios": scen,
            "base_weights": {k: v.probability for k, v in sc.scenarios.items()},
            "sims": sims,
            "future": fut,
            "phillips": pc_tab,
            "phillips_n": n_pc,
            "history": q,
            "policy_hist": qi,
            "beta2": b2,
            "beta10": b10,
            "g_star": g_star,
            "priced_12m": priced,
            "priced_src": priced_src,
            "as_of": last_q,
            "rf_table": rf.value,
        }
        ids = ["PCEPILFE", "UNRATE", "NROU", "DCOILBRENTEU", "DFF", "DGS2", "DGS10", "GDPPOT", "ACMTP10"]
        return stamp(out, ids, last_q)

    return load_or_compute("scenarios:US", compute, force=force)


def ols_beta(y: pd.Series, x: pd.Series) -> tuple[float, float]:
    r = ols_hac(y, x.to_frame("x"))
    return float(r.params["x"]), float(r.bse["x"])


def scenario_results(sb: dict, weights: dict[str, float]) -> dict:
    """Mix the per-scenario Monte Carlo with `weights` (cheap; called by the page on every edit)."""
    sims, fut, init = sb["sims"], sb["future"], sb["init"]
    tot = sum(weights.values())
    w = {k: v / tot for k, v in weights.items()}
    out: dict[str, Any] = {"weights": w}
    qs = [0.05, 0.16, 0.5, 0.84, 0.95]
    for var in ("i", "pi", "u", "y10"):
        vals, ww = scn.mixture(sims, w, var)
        out[f"q_{var}"] = pd.DataFrame(scn.weighted_quantile(vals, ww, qs).T, index=fut, columns=qs)
        out[f"mean_{var}"] = pd.Series(np.average(vals, axis=0, weights=ww), index=fut)
    vals_i, ww = scn.mixture(sims, w, "i")
    vals_u, _ = scn.mixture(sims, w, "u")
    out["moves"] = scn.moves_probabilities(vals_i, ww, init["i"])
    out["recession_prob"] = scn.recession_probability(vals_u, ww, init["u"])
    rows = []
    for k, s in sims.items():
        rows.append(
            {
                "scenario": sb["scenarios"][k]["label"],
                "probability": w[k],
                "policy rate 4Q (median)": float(np.median(s["mc"]["i"][:, 3])),
                "policy rate 8Q (median)": float(np.median(s["mc"]["i"][:, -1])),
                "core PCE 4Q (median)": float(np.median(s["mc"]["pi"][:, 3])),
                "P(Sahm-type trigger)": float(scn.sahm_trigger(s["mc"]["u"], init["u"]).mean()),
            }
        )
    tab = pd.DataFrame(rows).set_index("scenario")
    tab.loc["Probability-weighted"] = [
        1.0,
        float(np.sum(tab["probability"] * tab["policy rate 4Q (median)"])),
        float(np.sum(tab["probability"] * tab["policy rate 8Q (median)"])),
        float(np.sum(tab["probability"] * tab["core PCE 4Q (median)"])),
        out["recession_prob"],
    ]
    out["table"] = tab
    out["reverse"] = scn.reverse_stress(sims, w, sb["priced_12m"])
    # fans: mode = modal scenario's deterministic path; mean = probability-weighted deterministic paths;
    # sigma = dispersion of the modal scenario's Monte Carlo paths (bootstrap of historical errors)
    modal = max(w, key=lambda k: w[k])
    out["modal"] = modal
    fan = {}
    for var in ("i", "pi", "growth"):
        if var == "growth":
            det = {
                k: sb["g_star"] - sb["params"].okun * 4 * np.diff(np.r_[init["u"], s["det"]["u"][0]])
                for k, s in sims.items()
            }
            mc_modal = sb["g_star"] - sb["params"].okun * 4 * np.diff(
                np.c_[np.full(len(sims[modal]["mc"]["u"]), init["u"]), sims[modal]["mc"]["u"]], axis=1
            )
        else:
            det = {k: s["det"][var][0] for k, s in sims.items()}
            mc_modal = sims[modal]["mc"][var]
        mode = pd.Series(det[modal], index=fut)
        mean = pd.Series(sum(w[k] * det[k] for k in det), index=fut)
        sig = pd.Series(mc_modal.std(0), index=fut)
        fan[var] = fans.fan_quantiles(mode, sig, mean)
    out["fans"] = fan
    # market mapping of the weighted change in the expected policy rate at 4 quarters
    d_pol = np.array([out["mean_i"].iloc[3] - init["i"], 0.25, 0.5, -0.5])
    from macro.transmission import real_yield_betas  # noqa: F401  (betas from the transmission bundle)

    tb = transmission_bundle()
    rb = tb["real_betas"]
    spx = rb[(rb["asset"] == "S&P 500") & (rb["regime"] == "all")].iloc[0]
    out["mapping"] = scn.market_mapping(
        d_pol, sb["beta2"], sb["beta10"], (float(spx["b_real"]), float(spx["se_real"]))
    )
    return out


def regime_bundle(force: bool = False) -> dict:
    def compute() -> dict:
        gdp = get_series("GDPC1")
        pot = get_series("GDPPOT")
        g4 = 100 * np.log(gdp).diff(4)
        trend = 100 * np.log(pot.reindex(gdp.index)).diff(4)
        pce = panels.monthly("PCEPILFE")
        core = (100 * (pce / pce.shift(12) - 1)).resample("QS").mean()
        tgt = float(assumptions()["central_banks"]["fed"]["inflation_target"])
        hist = rg.two_by_two(g4, trend, core, tgt)
        cpi_core = panels.monthly("CPILFESL")
        x = 100 * ((cpi_core / cpi_core.shift(3)) ** 4 - 1)
        ms = rg.markov_inflation(x.loc["1990":])
        return {"history": hist, "markov": ms, "target": tgt, "as_of": hist.index[-1]}

    return load_or_compute("regimes:US", compute, force=force)


def as_of_str(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m") if ts is not None else "n/a"


def _chg(series_id: str, days: int, kind: str) -> float:
    s = try_series(series_id)
    if s is None or len(s.dropna()) <= days:
        return np.nan
    s = s.dropna()
    return (
        float(100 * (s.iloc[-1] - s.iloc[-1 - days]))
        if kind == "bp"
        else float(100 * np.log(s.iloc[-1] / s.iloc[-1 - days]))
    )


def build_views(weights: dict[str, float] | None = None) -> dict:
    """Scorecard per central bank, commentary, weekly changes, priced vs model, market confirmation,
    and the structured view. Reads the cached bundles; cheap enough to run on every page load."""
    from macro.config import calendar

    a = assumptions()
    lo, hi = a["rstar"]["user_range"]
    mid = (lo + hi) / 2
    sb = scenario_bundle()
    w = weights or sb["base_weights"]
    sr = scenario_results(sb, w)
    fcb, cvb, gb, posb = fincond_bundle(), curves_bundle(), growth_bundle(), positioning_bundle()
    rows, comments = [], {}
    for bank in BANKS:
        pb = policy_bundle(bank)
        cur = pb["current"]
        tgt = float(a["central_banks"][bank]["inflation_target"])
        r93 = a["rules"]["taylor1993"]
        presc = pol.taylor(cur["pi"], cur["y"], mid, tgt, r93["a_pi"], r93["a_gap"])
        infl_gap = cur["pi"] - tgt
        pgap = presc - cur["i"]

        def add(metric, value, unit, status, note="", _bank=bank):
            rows.append({"bank": _bank.upper(), **vw.scorecard_row(metric, value, unit, status, note)})

        add(
            f"Inflation vs target ({pb['panel']['ids']['infl_label']})",
            infl_gap,
            "pp",
            vw.status_from(abs(infl_gap), (0.5, 1.0, 2.0)),
        )
        add(
            f"Policy gap (Taylor at r*={mid:.2f} minus actual)",
            pgap,
            "pp",
            vw.status_from(abs(pgap), (0.5, 1.0, 2.0)),
            "positive = rule above actual (behind the curve on this metric)",
        )
        if bank == "fed":
            g = fcb["gap"]["gap"]
            add(
                "Financial-conditions gap (FCI-lite)",
                g,
                "pp of growth",
                vw.status_from(abs(g), (0.25, 0.5, 1.0)),
            )
            sp = cvb["spreads"].iloc[-1]
            reg = cvb["regimes"]["regime"].iloc[-1]
            add(
                "Curve 3m10y / regime",
                float(sp["3m10y"]),
                "bp",
                "serious" if sp["3m10y"] < 0 else "good",
                reg,
            )
            rp = gb["recession"].value
            add("Recession probability, 12m (probit)", rp, "prob.", vw.status_from(rp, (0.2, 0.35, 0.5)))
            gq = float(gb["gar"][4].extra["quantiles"][0.05])
            add(
                "Growth-at-Risk 5%, 4Q ahead",
                gq,
                "% ann.",
                vw.status_from(gq, (0.0, -1.0, -2.0), higher_is_worse=False),
            )
            n_crowd = int((posb["table"]["flag"] != "").sum()) if posb["adjusted"] else 0
            add(
                "Crowded positions (CFTC TFF)",
                n_crowd,
                "count",
                "good" if n_crowd == 0 else "warning" if n_crowd <= 2 else "serious",
            )
        if bank == "ecb":
            lat = cvb["stress"]["latest"]
            flags = int((lat["level flag"] | lat["speed flag"]).sum())
            add(
                "Sovereign stress flags (OAT/BTP/Bonos-Bund)",
                flags,
                "count",
                "good" if flags == 0 else "serious",
            )
            ea = gb.get("ea_recession") or {}
            if "current" in ea:
                pe = ea["current"]["p"]
                add(
                    "Recession probability, 12m (EA probit)",
                    pe,
                    "prob.",
                    vw.status_from(pe, (0.2, 0.35, 0.5)),
                )
        if bank == "boj":
            jp = cvb["jgb"].dropna()
            add("JGB 10Y, 12-month change", float(100 * (jp.iloc[-1] - jp.iloc[-13])), "bp", "good")
        stance = "below" if pgap > 0 else "above"  # pgap = rule - actual
        comments[bank] = (
            f"{bank.upper()}: {pb['panel']['ids']['infl_label']} inflation is {cur['pi']:.1f}% "
            f"({infl_gap:+.1f} pp vs target); the policy rate ({cur['i']:.2f}%) is {abs(pgap):.2f} pp {stance} a Taylor (1993) "
            f"prescription with r* at the middle of the {lo:.2f}-{hi:.2f}% range."
        )
    score = pd.DataFrame(rows)
    # what changed over the last 5 business days
    changes = pd.DataFrame(
        [
            {"indicator": "US 2Y yield", "change": _chg("DGS2", 5, "bp"), "unit": "bp"},
            {"indicator": "US 10Y yield", "change": _chg("DGS10", 5, "bp"), "unit": "bp"},
            {"indicator": "10Y breakeven", "change": _chg("T10YIE", 5, "bp"), "unit": "bp"},
            {"indicator": "Euro area 2Y (AAA)", "change": _chg("EA_YC_2Y", 5, "bp"), "unit": "bp"},
            {"indicator": "Broad dollar", "change": _chg("DTWEXBGS", 5, "pct"), "unit": "%"},
            {"indicator": "EURUSD", "change": _chg("EURUSD", 5, "pct"), "unit": "%"},
            {"indicator": "USDJPY", "change": _chg("USDJPY", 5, "pct"), "unit": "%"},
            {"indicator": "S&P 500", "change": _chg("SPX", 5, "pct"), "unit": "%"},
            {"indicator": "Baa-10Y credit spread", "change": _chg("BAA10Y", 5, "bp"), "unit": "bp"},
        ]
    ).set_index("indicator")
    wk = gb["weekly"]
    nowcast_change = (
        float(wk["change"].iloc[-1]) if "change" in wk and wk["change"].notna().iloc[-1] else np.nan
    )
    # priced vs model (Fed)
    init = sb["init"]
    q_i = sr["q_i"]
    pvm = [
        {
            "bank": "FED",
            "item": "Policy rate in 4 quarters",
            "priced": sb["priced_12m"],
            "model (median)": q_i.iloc[3][0.5],
            "model 68% low": q_i.iloc[3][0.16],
            "model 68% high": q_i.iloc[3][0.84],
            "priced source": sb["priced_src"],
        }
    ]
    model_2y = float(sr["mean_i"].mean())
    pvm.append(
        {
            "bank": "FED",
            "item": "2Y yield (avg expected policy over 8Q)",
            "priced": float(panels.monthly("DGS2").dropna().iloc[-1]),
            "model (median)": model_2y,
            "model 68% low": float(sr["q_i"][0.16].mean()),
            "model 68% high": float(sr["q_i"][0.84].mean()),
            "priced source": "FRED DGS2",
        }
    )
    pvm.append(
        {
            "bank": "FED",
            "item": "10Y yield (engine, next quarter)",
            "priced": float(panels.monthly("DGS10").dropna().iloc[-1]),
            "model (median)": float(sr["q_y10"].iloc[0][0.5]),
            "model 68% low": float(sr["q_y10"].iloc[0][0.16]),
            "model 68% high": float(sr["q_y10"].iloc[0][0.84]),
            "priced source": "FRED DGS10",
        }
    )
    for bank in ("ecb", "boj"):
        pb = policy_bundle(bank)
        rf = pb["rf_full"].value
        if rf is None:
            continue
        t = rf["estimate"]
        c_gap = t["c (output gap)"] if t["c (output gap)"] == t["c (output gap)"] else 0.0
        target_rate = t["a"] + t["b (inflation)"] * pb["current"]["pi"] + c_gap * pb["current"]["y"]
        priced = pb["current"]["y2"]
        pvm.append(
            {
                "bank": bank.upper(),
                "item": "Policy rate (reaction-function long-run target)",
                "priced": priced if priced is not None else np.nan,
                "model (median)": target_rate,
                "model 68% low": np.nan,
                "model 68% high": np.nan,
                "priced source": "2Y AAA yield proxy" if priced is not None else "not available",
            }
        )
    pvm = pd.DataFrame(pvm)
    # market confirmation of the model's policy direction
    d4 = float(sr["mean_i"].iloc[3] - init["i"])
    view = "tightening" if d4 > 0.125 else "easing" if d4 < -0.125 else "on hold"
    moves = {
        "2Y yield": _chg("DGS2", 20, "bp"),
        "10Y breakeven": _chg("T10YIE", 20, "bp"),
        "Broad dollar": _chg("DTWEXBGS", 20, "pct"),
        "Credit spread": _chg("BAA10Y", 20, "bp"),
        "S&P 500": _chg("SPX", 20, "pct"),
    }
    conf = vw.market_confirmation(moves, view) if view != "on hold" else pd.DataFrame()
    cal = [e for e in calendar().events if e.date >= pd.Timestamp(gb["as_of"]).date()][:4]
    catalysts = [f"{e.date}: {e.label}{'' if e.verified else ' (date unverified)'}" for e in cal]
    nc = gb["nowcast"]
    evidence = [
        comments["fed"],
        f"GDP nowcast for {nc['target']}: {nc['point']:.1f}% annualised (68% band {nc['lo68']:.1f} to {nc['hi68']:.1f}).",
        f"Financial-conditions gap {fcb['gap']['gap']:+.2f} pp of growth (FCI-lite; positive = more tightening needed to close the output gap).",
        f"12-month recession probability {100 * gb['recession'].value:.0f}% (probit, {gb['recession'].extra['episodes']} episodes in sample).",
    ]
    view_txt = {
        "tightening": "The models imply further Fed tightening over the next four quarters",
        "easing": "The models imply Fed easing over the next four quarters",
        "on hold": "The models imply a broadly unchanged Fed policy rate over the next four quarters",
    }[view]
    vt = vw.view_template(
        view=f"{view_txt} (probability-weighted mean change {d4:+.2f} pp).",
        evidence=evidence,
        priced=f"Priced policy rate in 12 months: {sb['priced_12m']:.2f}% ({sb['priced_src']}); model median {q_i.iloc[3][0.5]:.2f}%.",
        change_view=[
            "Core inflation momentum (3m annualised) falling below target for two consecutive prints.",
            "A Sahm-type rise in unemployment.",
            "A sharp tightening of financial conditions (FCI-lite up 0.5 pp).",
        ],
        risks=[
            f"{sb['scenarios'][k]['label']} ({100 * v:.0f}%)"
            for k, v in sorted(sr["weights"].items(), key=lambda x: -x[1])
        ],
        catalysts=catalysts,
        implications=[
            f"A +25bp shift in the expected policy path is consistent with about {25 * sb['beta2'][0]:.0f}bp on the 2Y "
            f"and {25 * sb['beta10'][0]:.0f}bp on the 10Y (estimated sensitivities).",
            "Equity sensitivity to real yields is reported on the Transmission page with bands.",
        ],
    )
    return {
        "scorecard": score,
        "comments": comments,
        "changes": changes,
        "nowcast_change": nowcast_change,
        "priced_vs_model": pvm,
        "view": view,
        "confirmation": conf,
        "template": vt,
        "scenario": sr,
        "as_of": gb["as_of"],
    }


ARCHIVE_VARIABLES = {
    "US headline inflation yoy": ("CPIAUCSL", "yoy"),
    "EA headline inflation yoy": ("EA_HICP", "yoy"),
    "JP headline inflation yoy": ("JP_CPI", "yoy"),
    "US real GDP growth q/q annualised": ("GDPC1", "qoq_ann"),
}


def archive_outcomes() -> dict[str, pd.Series]:
    """Realised values (latest vintage) for every archived variable, indexed by target date."""
    out = {}
    for var, (sid, kind) in ARCHIVE_VARIABLES.items():
        s = try_series(sid)
        if s is None:
            continue
        out[var] = 100 * (s / s.shift(12) - 1) if kind == "yoy" else 400 * np.log(s).diff()
    return out


def track_record() -> tuple[pd.DataFrame, pd.DataFrame]:
    from macro import archive

    return archive.track_record(archive.read(), archive_outcomes())
