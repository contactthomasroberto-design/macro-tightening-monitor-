import numpy as np
import pandas as pd
import pytest

from macro import growth as gr
from macro import recession as rc


def test_skewt_closed_form_matches_scipy():
    from scipy import stats

    d = gr.SkewT(2.0, 5.0, 0.3, 1.7)
    s = stats.jf_skew_t(2.0, 5.0, loc=0.3, scale=1.7)
    u, x = np.array([0.01, 0.3, 0.9]), np.array([-3.0, 0.0, 2.0])
    assert np.allclose(d.ppf(u), s.ppf(u))
    assert np.allclose(d.cdf(x), s.cdf(x))
    assert np.allclose(d.logpdf(x), s.logpdf(x))


def test_skewt_fit_recovers_quantiles():
    true = gr.SkewT(2.5, 6.0, 3.0, 1.5)
    q = pd.Series(true.ppf(list(gr.QUANTILES)), index=gr.QUANTILES)
    fit = gr.fit_skewt(q)
    assert fit["fit_error"] < 0.02
    assert np.allclose(fit["dist"].ppf([0.05, 0.95]), q[[0.05, 0.95]], atol=0.05)


def test_expected_shortfall_normal_like():
    d = gr.SkewT(30.0, 30.0, 0.0, 1.0)  # close to normal with sd ~ 1/sqrt(1 - 1/(2a)) * ...
    es = gr.expected_shortfall(d, 0.05)
    assert es < d.ppf(0.05)  # ES is below VaR


def test_quantile_regression_recovers_downside_slope():
    g = np.random.default_rng(3)
    n = 400
    idx = pd.date_range("1920-01-01", periods=n, freq="QS")
    nfci = pd.Series(g.normal(0, 1, n), index=idx)
    # downside widens with NFCI: scale of left tail grows with nfci
    eps = g.normal(0, 1, n)
    y = 2.5 - 0.3 * nfci + np.where(eps < 0, (1.0 + 0.8 * np.clip(nfci, 0, None)) * eps, eps)
    lg = np.log(100) + np.concatenate([[0], np.cumsum(y[:-1] / 400)])
    gdp = pd.Series(np.exp(lg), index=idx)
    df = gr.gar_frame(gdp, nfci.shift(-0), 1)
    df["y_fwd"] = pd.Series(y, index=idx)  # plant the outcome directly
    coefs = gr.quantile_fit(df)
    assert coefs[0.05][2] < coefs[0.5][2]  # NFCI hits the 5% quantile harder than the median


def test_ar_benchmark_iterates():
    s = pd.Series([2.0] * 30, index=pd.period_range("2000Q1", periods=30, freq="Q"))
    s.iloc[-1] = 3.0
    f = gr.ar_benchmark(s, s.index[-1], s.index[-1] + 2)
    assert np.isfinite(f)


def test_sahm_rule():
    u = pd.Series([4.0] * 15 + [4.2, 4.5, 4.8, 5.0], index=pd.date_range("2000", periods=19, freq="MS"))
    s = rc.sahm(u)
    assert bool(s["triggered"].iloc[-1])
    assert not bool(s["triggered"].iloc[14])


def test_auc_and_brier():
    y = np.array([0, 0, 1, 1])
    assert rc.roc_auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert rc.roc_auc(y, np.array([0.5, 0.5, 0.5, 0.5])) == 0.5
    assert rc.brier(y, np.array([0, 0, 1, 1.0])) == 0.0


def test_probit_recovers_sign_and_bootstrap_band():
    g = np.random.default_rng(4)
    n = 600
    idx = pd.date_range("1960-01-01", periods=n, freq="MS")
    spread = pd.Series(g.normal(1, 1, n), index=idx)
    from scipy import stats

    p = stats.norm.cdf(-1.0 - 1.2 * spread)
    y = pd.Series((g.random(n) < p).astype(float), index=idx)
    df = pd.DataFrame({"spread_3m10y": spread, "y": y})
    cur = rc.current_probability(df, ["spread_3m10y"], n_boot=100, seed=1)
    assert cur["lo"] <= cur["p"] <= cur["hi"]
    m = rc._probit(y.to_numpy(), spread.to_frame().to_numpy())
    assert m.params[1] < -0.8


@pytest.mark.slow
def test_news_decomposition_adds_up():
    """News impacts by category + revisions = change in the nowcast (identity of the method)."""
    g = np.random.default_rng(5)
    n = 240
    f = np.zeros(n)
    for t in range(1, n):
        f[t] = 0.7 * f[t - 1] + g.normal()
    idx = pd.period_range("2000-01", periods=n, freq="M")
    M = pd.DataFrame(
        {sid: 0.8 * f + g.normal(0, 0.5, n) for sid in ["PAYEMS", "INDPRO", "RSAFS", "CPIAUCSL"]}, index=idx
    )
    qf = pd.Series(f, index=idx).resample("Q").mean()
    Q = (2 * qf + g.normal(0, 0.3, len(qf))).to_frame(gr.GDP_ID)
    target = Q.index[-1]
    Q_known = Q.iloc[:-1]
    old = (M.iloc[:-2].reindex(idx), Q_known)
    new = (M, Q_known)
    res = gr.fit_dfm(M.iloc[:-2], Q_known, maxiter=50)
    nd = gr.news_decomposition(res, old, new, target)
    assert sum(nd["by_category"].values()) == pytest.approx(nd["change"], abs=1e-6)
    assert "production" in nd["by_category"]
