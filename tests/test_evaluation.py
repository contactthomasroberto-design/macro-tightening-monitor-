import numpy as np
from scipy import integrate, stats

from macro import evaluation as ev


def test_crps_matches_numerical_integral():
    y, mu, s = 1.3, 0.5, 0.8
    num, _ = integrate.quad(lambda x: (stats.norm.cdf(x, mu, s) - (x >= y)) ** 2, -20, 20, points=[y])
    assert abs(ev.crps_normal(y, mu, s) - num) < 1e-6


def test_log_score_and_pit():
    assert ev.log_score_normal(0, 0, 1) == stats.norm.logpdf(0)
    assert ev.pit_normal(0, 0, 1) == 0.5


def test_dm_detects_better_model():
    g = np.random.default_rng(0)
    e_good = g.normal(0, 1, 400)
    e_bad = g.normal(0, 1.5, 400)
    r = ev.diebold_mariano(e_good, e_bad, h=1)
    assert r["dm"] < 0 and r["pvalue"] < 0.01
    r2 = ev.diebold_mariano(e_good, e_good + g.normal(0, 1e-3, 400), h=1)
    assert r2["pvalue"] > 0.05


def test_rmse_mae_ignore_nan():
    assert ev.rmse([3, 4, np.nan]) == np.sqrt(12.5)
    assert ev.mae([-1, 1, np.nan]) == 1
