import numpy as np
import pandas as pd

from macro import plotting


def test_synthetic_banner_in_demo(monkeypatch):
    monkeypatch.setenv("MACRO_MODE", "demo")
    df = pd.DataFrame({"a": [1, 2, 3], "b": [3, 2, 1]}, index=pd.date_range("2020", periods=3, freq="MS"))
    fig = plotting.line_chart(df, "A falls as B rises", "test", "2020-03-01")
    texts = [a.text for a in fig.layout.annotations]
    assert any("SYNTHETIC" in t for t in texts)
    assert any(t.startswith("Source: test") for t in texts)
    assert fig.layout.showlegend is True


def test_no_banner_in_live(monkeypatch):
    monkeypatch.setenv("MACRO_MODE", "live")
    df = pd.DataFrame({"a": [1, 2]}, index=pd.date_range("2020", periods=2, freq="MS"))
    fig = plotting.line_chart(df, "t", "s", None)
    assert not any("SYNTHETIC" in (a.text or "") for a in fig.layout.annotations)


def test_fan_colors_single_hue_increasing_opacity():
    cols = plotting.fan_colors("#2a78d6", 4)
    alphas = [float(c.rsplit(",", 1)[1].rstrip(")")) for c in cols]
    assert alphas == sorted(alphas)
    assert len({c.rsplit(",", 1)[0] for c in cols}) == 1


def test_fit_time_axis_cuts_to_window_and_drops_old_shading():
    import plotly.graph_objects as go

    from macro.plotting import add_recession_shading, fit_time_axis

    idx = pd.date_range("1990-01-01", "2026-09-01", freq="MS")
    fig = go.Figure(go.Scatter(x=idx, y=np.arange(len(idx), dtype=float)))
    rec = pd.Series(0, index=pd.date_range("1854-01-01", "2026-09-01", freq="MS"))
    rec.loc["1860-01-01":"1861-06-01"] = 1
    rec.loc["2008-01-01":"2009-06-01"] = 1
    add_recession_shading(fig, rec)
    fit_time_axis(fig, "2000-01-01")
    x = pd.to_datetime(fig.data[0].x)
    assert x.min() == pd.Timestamp("2000-01-01") and x.max() == pd.Timestamp("2026-09-01")
    assert fig.data[0].y[0] == float(idx.get_loc(pd.Timestamp("2000-01-01")))  # y cut with x
    assert len(fig.layout.shapes) == 1  # the 1860 recession is gone, 2008 kept
    assert pd.Timestamp(fig.layout.xaxis.range[0]) == pd.Timestamp("2000-01-01")


def test_fit_time_axis_thins_dense_series_and_ignores_non_date_axes():
    import plotly.graph_objects as go

    from macro.plotting import fit_time_axis

    d = pd.bdate_range("1960-01-01", "2026-09-30")
    fig = go.Figure(go.Scatter(x=d, y=np.ones(len(d))))
    fit_time_axis(fig, None, max_points=1000)
    assert len(fig.data[0].x) <= 1001 and pd.Timestamp(fig.data[0].x[-1]) == d[-1]
    bar = go.Figure(go.Bar(x=["1-2pp", "2-4pp"], y=[1, 2]))
    fit_time_axis(bar, "2000-01-01")
    assert list(bar.data[0].x) == ["1-2pp", "2-4pp"] and bar.layout.xaxis.range is None
