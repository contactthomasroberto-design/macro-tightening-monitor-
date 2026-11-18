import numpy as np
import pandas as pd
import pytest

from macro import fund_process as fp


def _dec(**kw):
    d = dict(
        date="2026-01-05",
        agent="macro-strategist",
        claim="SPY up",
        target="SPY",
        metric="return",
        direction="above",
        threshold=0.0,
        horizon="2026-02-05",
        probability=0.7,
        source="comité",
    )
    return d | kw


def test_registry_add_resolve_and_brier(tmp_path):
    p = tmp_path / "d.csv"
    assert fp.add_decisions([_dec(), _dec(claim="SPY down", direction="below", probability=0.4)], p) == 2
    assert fp.add_decisions([_dec()], p) == 0  # duplicate claim skipped
    idx = pd.bdate_range("2025-12-01", "2026-03-01")
    px = pd.Series(np.linspace(100, 110, len(idx)), idx)
    df = fp.resolve(fp.read_decisions(p), lambda k: px if k == "SPY" else None, pd.Timestamp("2026-03-01"))
    assert (df["status"] == "resolved").all()
    assert list(df["outcome"].astype(int)) == [1, 0]
    bt = fp.brier_table(df)
    # (0.7-1)² = 0.09 and (0.4-0)² = 0.16
    assert bt.loc["macro-strategist", "Brier"] == pytest.approx(0.125)


def test_resolve_waits_for_data_and_voids_unknown():
    idx = pd.bdate_range("2026-01-01", "2026-01-20")
    px = pd.Series(1.0, idx)
    df = pd.DataFrame([_dec(id="a"), _dec(id="b", target="XXX")]).assign(status="open")
    for c in ("date", "horizon"):
        df[c] = pd.to_datetime(df[c])
    out = fp.resolve(df, lambda k: px if k == "SPY" else None, pd.Timestamp("2026-03-01"))
    assert out.loc[0, "status"] == "open"  # horizon not yet in the data
    assert out.loc[1, "status"] == "void"


def test_validate_rejects_bad_decisions():
    with pytest.raises(ValueError):
        fp.validate(_dec(probability=1.2))
    with pytest.raises(ValueError):
        fp.validate(_dec(horizon="2025-01-01"))
    with pytest.raises(ValueError):
        fp.validate(_dec(metric="vibes"))


def test_losers_and_post_mortem():
    idx = pd.date_range("2023-01-06", periods=200, freq="W-FRI")
    rng = np.random.default_rng(0)
    r = pd.DataFrame({"SPY": rng.normal(0.002, 0.02, 200), "HYNIX": rng.normal(0.003, 0.05, 200)}, idx)
    r.iloc[-4:, 1] = -0.10  # four bad weeks for HYNIX
    r.iloc[-4:, 0] = 0.0
    w = pd.DataFrame({"SPY": 0.5, "HYNIX": 0.05}, idx)
    lose = fp.losers(w, r, threshold=0.01, weeks=4)
    assert list(lose.index) == ["HYNIX"] and lose["HYNIX"] == pytest.approx(-0.02)
    cfg = {"universe": {"HYNIX": {"min": 0.015, "max": 0.08}, "SPY": {"min": 0, "max": 1}}}
    pm = fp.post_mortem("HYNIX", w, r, cfg, 4)
    assert pm["move in sigmas"] < -2 and "signal" in pm["verdict"] or "marché" in pm["verdict"]
    assert "Revue de perte" in fp.post_mortem_markdown(pm, -0.02, "2026-01-01")


def test_forward_stress_limits_and_hedge():
    a = ["SPY", "AGG", "GLD"]
    vol = np.array([0.16, 0.05, 0.15])
    corr = np.array([[1, -0.2, 0.1], [-0.2, 1, 0.3], [0.1, 0.3, 1]])
    cov = pd.DataFrame(np.outer(vol, vol) * corr, a, a)
    spec = {
        "limits": {"absolute": 0.10, "relative_to_benchmark": 1.0},
        "scenarios": {"crash": {"label": "crash", "shocks": {"SPY": -30}}},
    }
    bench = pd.Series({"SPY": 0.6, "AGG": 0.4})
    heavy = pd.Series({"SPY": 0.9, "AGG": 0.1})
    out = fp.forward_stress(heavy, bench, cov, spec)
    assert out.loc["crash", "book"] < out.loc["crash", "benchmark"] < 0
    assert "benchmark" in out.loc["crash", "breach"] and "15" not in out.loc["crash", "breach"]
    hedged = fp.forward_stress(heavy, bench, cov, spec, {"hedged share of NAV": 0.9, "moneyness": 0.95})
    assert hedged.loc["crash", "of which tail hedge"] == pytest.approx(0.9 * 0.25)
    assert hedged.loc["crash", "book"] > out.loc["crash", "book"]


def test_scenarios_config_uses_universe():
    from macro import portfolio as pf

    uni = set(pf.load_config()["universe"])
    for k, sc in fp.load_scenarios()["scenarios"].items():
        assert set(sc["shocks"]) <= uni, k


def test_performance_tables():
    idx = pd.date_range("2024-01-05", "2026-11-13", freq="W-FRI")
    r = pd.Series(0.001, idx)
    b = pd.Series(0.0005, idx)
    p = fp.period_returns(r)
    assert p["week"] == pytest.approx(0.001)
    n_ytd = (idx >= "2026-01-01").sum()
    assert p["year to date"] == pytest.approx(1.001**n_ytd - 1)
    assert p["2025"] == pytest.approx(1.001 ** (idx.year == 2025).sum() - 1)
    s = fp.performance_summary({"m": r, "b": b})
    assert "m − b" in s.columns and (s["m − b"].dropna() > 0).all()
    cal = fp.calendar_table(r, b)
    assert list(cal.index) == [2026, 2025, 2024]
    assert cal.loc[2025, "year"] == pytest.approx((1 + cal.loc[2025, "Jan":"Dec"]).prod() - 1)
    assert cal.loc[2026, "Dec"] != cal.loc[2026, "Dec"]  # no December yet (NaN)


def test_committee_actions_only_reduce_risk(tmp_path):
    p = tmp_path / "a.csv"
    uni = {"SPY": {}, "HYNIX": {}, "BIL": {}}
    with pytest.raises(ValueError):
        fp.add_action({"date": "2026-11-18", "action": "derisk", "scale": 1.2, "reason": "x"}, uni, p)
    with pytest.raises(ValueError):
        fp.add_action({"date": "2026-11-18", "action": "derisk", "scale": 0.3, "reason": "x"}, uni, p)
    with pytest.raises(ValueError):
        fp.add_action({"date": "2026-11-18", "action": "freeze", "target": "HYNIX", "reason": ""}, uni, p)
    a = fp.add_action(
        {
            "date": "2026-11-18",
            "action": "derisk",
            "scale": 0.7,
            "reason": "NVDA results",
            "expires": "2027-01-30",
        },
        uni,
        p,
    )
    assert a["expires"] == "2026-12-02"  # capped at 14 days
    fp.add_action(
        {"date": "2026-11-18", "action": "freeze", "target": "HYNIX", "reason": "price jump"}, uni, p
    )
    act = fp.active_actions(fp.read_actions(p), pd.Timestamp("2026-11-20"))
    assert act["derisk"] == 0.7 and act["frozen"] == ["HYNIX"]
    assert fp.active_actions(fp.read_actions(p), pd.Timestamp("2026-12-10"))["derisk"] == 1.0  # lapsed
    fp.add_action(
        {"date": "2026-11-21", "action": "lift", "target": "HYNIX", "reason": "data checked"}, uni, p
    )
    assert fp.active_actions(fp.read_actions(p), pd.Timestamp("2026-11-22"))["frozen"] == []


def test_freeze_holds_weight_and_impact():
    tgt = pd.Series({"SPY": 0.5, "HYNIX": 0.08, "BIL": 0.02})
    cur = pd.Series({"SPY": 0.45, "HYNIX": 0.05, "BIL": 0.10})
    out = fp.apply_freeze(tgt, cur, ["HYNIX"])
    assert (
        out["HYNIX"] == 0.05 and out["BIL"] == pytest.approx(0.05) and out.sum() == pytest.approx(tgt.sum())
    )
    imp = fp.committee_impact(pd.Series({"SPY": 0.5, "TLT": 0.1}), pd.Series({"SPY": 0.45, "TLT": 0.1}))
    assert list(imp.index) == ["SPY"] and imp.loc["SPY", "change"] == pytest.approx(0.05)
