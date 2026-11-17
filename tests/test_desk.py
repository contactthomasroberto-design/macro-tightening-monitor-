import numpy as np
import pandas as pd

from macro import desk


def _ctx(n=900):
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.random.default_rng(1)
    spy = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
    a = 50 * np.exp(np.cumsum(rng.normal(0.0008, 0.02, n)))
    c = 80 * np.exp(np.cumsum(rng.normal(-0.0004, 0.015, n)))
    px = pd.DataFrame({"SPY": spy, "EWJ": a, "VGK": c}, idx)
    views = {
        "trend": pd.Series({"EWJ": 0.8, "VGK": -0.6, "SPY": 0.2}),
        "value": pd.Series({"EWJ": 0.3, "VGK": 0.4}),
    }
    b = {
        "config": {"universe": {k: {"name": k, "sleeve": "equity"} for k in px}},
        "views": views,
        "target": pd.Series({"SPY": 0.4, "EWJ": 0.05, "VGK": -0.02}),
        "w_eq": pd.Series({"SPY": 0.38, "EWJ": 0.03, "VGK": 0.09}),
        "mu": pd.Series({"SPY": 0.06, "EWJ": 0.09, "VGK": 0.03}),
        "pi": pd.Series({"SPY": 0.05, "EWJ": 0.05, "VGK": 0.05}),
        "house_views": [{"date": "2026-11-01", "stances": {"VGK": 1, "EWJ": 1}}],
        "as_of": idx[-1],
    }
    return desk.Context(b=b, get=lambda k: px.get(k, None), px=px)


def test_coverage_table_stance_and_conflict():
    ctx = _ctx()
    t = desk.coverage_table(ctx, ["SPY", "EWJ", "VGK", "MISSING"])
    assert set(t.index) == {"SPY", "EWJ", "VGK"}
    assert t.loc["EWJ", "stance"] == "positive" and t.loc["EWJ", "agreement"] == 1.0
    assert t.loc["VGK", "agreement"] == 0.5  # trend and value disagree
    assert abs(t.loc["EWJ", "model tilt (pp/yr)"] - 4.0) < 1e-9


def test_scan_line_and_spread():
    idx = pd.bdate_range("2020-01-01", periods=1500)
    s = pd.Series(np.linspace(1, 2, 1500), idx)
    s.iloc[-1] += 1.0  # a jump: big z-score
    line, z = desk.scan_line(s, "x", "level")
    assert "percentile 5 ans 100 %" in line and z > 2 and "⚠" in line
    get = {"A": pd.Series(3.0, idx), "B": pd.Series(1.0, idx)}.get
    assert desk.series_of(get, "A-B").iloc[-1] == 2.0
    m = pd.Series(np.linspace(100, 112, 40), pd.date_range("2023-01-01", periods=40, freq="MS"))
    line, _ = desk.scan_line(m, "cpi", "yoy")
    assert "sur un an" in line


def test_senior_metrics_and_relative_value():
    ctx = _ctx()
    sm = desk.senior_metrics(ctx, ["SPY", "EWJ", "VGK"])
    assert {"12-1 momentum", "1m z", "5y percentile", "beta SPY"} <= set(sm.columns)
    assert np.isnan(sm.loc["SPY", "beta SPY"])
    rv = desk.relative_value(ctx, ["SPY", "EWJ", "VGK"])
    assert rv is not None and "long EWJ / short VGK" in rv


def test_markdown_renders_table():
    ctx = _ctx()
    n = desk._coverage_note(ctx, "japan-asia-analyst", "Japon")
    desk.enrich(ctx, n)
    md = desk.markdown(n, "now")
    assert md.startswith("# Japon") and "| EWJ |" in md


def test_task_board(tmp_path):
    from macro import team

    st = tmp_path / "status.csv"
    team.set_status(
        [{"agent": "macro-strategist", "stage": "tour 1", "status": "en cours", "task": "note"}], st
    )
    team.set_status(
        [{"agent": "macro-strategist", "stage": "tour 1", "status": "terminé", "task": "note"}], st
    )
    idx = tmp_path / "README.md"
    idx.write_text(
        "# Desk GitHub — 17/11/2026 16:47 UTC\n\n| `fx-strategist` | [Changes (calcul GitHub)](fx.md) | x |\n"
    )
    b = team.board(st, idx, hours=10_000)
    m = b[b["agent"] == "macro-strategist"]
    assert len(m) == 1 and m.iloc[0]["status"] == "terminé"
    d = b[b["agent"] == "fx-strategist"].iloc[0]
    assert d["source"] == "desk" and d["time"].hour == 16
    import pytest

    with pytest.raises(ValueError):
        team.set_status([{"agent": "x", "stage": "s", "status": "fini", "task": "t"}], st)


def test_conflicts_use_the_stance():
    ctx = _ctx()
    n = desk._coverage_note(ctx, "japan-asia-analyst", "x")  # EWJ: positive stance, house +1: no conflict
    assert not any("EWJ" in w for w in n.watch)
    n = desk._coverage_note(ctx, "europe-analyst", "x")  # VGK: negative stance, house +1: conflict
    assert any("VGK" in w and "contredisent" in w for w in n.watch)
