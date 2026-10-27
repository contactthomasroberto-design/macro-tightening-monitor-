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
