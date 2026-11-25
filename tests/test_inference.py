import numpy as np
import pytest

from quant.inference import holm, normal_sf, ols_hac


def test_slope_and_white_errors_match_the_matrix_formula() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=400)
    y = 0.5 + 2.0 * x + rng.normal(size=400) * (1 + np.abs(x))  # heteroskedastic

    fit = ols_hac(y, x, lags=0)

    design = np.ones((400, 2))
    design[:, 1] = x
    bread = np.linalg.inv(design.T @ design)
    beta = bread @ design.T @ y
    e = y - design @ beta
    white = bread @ (design.T * e**2) @ design @ bread
    assert fit.slope == pytest.approx(beta[1])
    assert fit.se_slope == pytest.approx(np.sqrt(white[1, 1]))
    assert fit.p_slope < 1e-6


def test_overlapping_returns_get_wider_errors_with_newey_west() -> None:
    # Regress a 20-day overlapping sum of noise on an unrelated, slowly moving signal.
    rng = np.random.default_rng(1)
    daily = rng.normal(size=3000)
    forward = np.convolve(daily, np.ones(20), mode="valid")[: 3000 - 20]
    signal = np.convolve(rng.normal(size=3000), np.ones(60) / 60, mode="same")[: len(forward)]

    naive = ols_hac(forward, signal, lags=0)
    hac = ols_hac(forward, signal, lags=19)

    assert hac.se_slope > 2 * naive.se_slope
    assert abs(hac.t_slope) < abs(naive.t_slope)


def test_missing_values_are_dropped_and_bad_input_refused() -> None:
    fit = ols_hac([1.0, 2.0, np.nan, 4.0, 5.0], [1.0, 2.0, 3.0, np.nan, 5.0], lags=0)
    assert fit.n == 3 and fit.slope == pytest.approx(1.0)
    with pytest.raises(ValueError):
        ols_hac([1.0, 2.0], [1.0, 2.0], lags=0)


def test_holm_adjusts_in_rank_order_and_stays_monotone() -> None:
    assert holm([0.01, 0.04, 0.03, 0.5]) == pytest.approx([0.04, 0.09, 0.09, 0.5])
    assert holm([0.9, 0.9]) == [1.0, 1.0]
    assert normal_sf(1.959964) == pytest.approx(0.025, abs=1e-6)


def test_fitted_value_error_at_a_dummy_is_the_error_of_that_group_mean() -> None:
    # With a 0/1 regressor, intercept + slope is the mean of the "1" group; with lags = 0 its
    # error is the robust error of that group's mean.
    rng = np.random.default_rng(3)
    group = rng.random(600) < 0.3
    y = group.astype(float) + rng.normal(size=600)

    fit = ols_hac(y, group.astype(float), lags=0)

    inside = y[group]
    expected = np.sqrt(((inside - inside.mean()) ** 2).sum()) / len(inside)
    assert fit.intercept + fit.slope == pytest.approx(inside.mean())
    assert fit.se_at(1.0) == pytest.approx(expected, rel=1e-9)


def test_mean_hac_matches_white_without_lags_and_widens_with_overlap() -> None:
    from quant.inference import mean_hac

    y = np.array([1.0, 2.0, 3.0, 4.0, np.nan])
    mean, se, n = mean_hac(y, lags=0)
    assert (mean, n) == (2.5, 4)
    assert se == pytest.approx(np.sqrt(np.mean((y[:4] - 2.5) ** 2) / 4))

    rng = np.random.default_rng(5)
    overlapping = np.convolve(rng.normal(size=2000), np.ones(12), mode="valid")
    assert mean_hac(overlapping, 11)[1] > 2.5 * mean_hac(overlapping, 0)[1]
    with pytest.raises(ValueError):
        mean_hac([1.0], 0)


def test_wald_joint_accepts_an_unbiased_forecast_and_rejects_a_biased_one() -> None:
    from quant.inference import wald_joint

    rng = np.random.default_rng(6)
    forecast = rng.normal(5, 2, size=500)
    unbiased = forecast + rng.normal(size=500)

    fit = ols_hac(unbiased, forecast, lags=0)
    stat, p = wald_joint(fit, 0.0, 1.0)
    assert p > 0.01 and p == pytest.approx(np.exp(-stat / 2))

    # A forecast that runs 1 point too high is rejected even though its slope is right.
    biased = ols_hac(unbiased - 1.0, forecast, lags=0)
    assert wald_joint(biased, 0.0, 1.0)[1] < 1e-6
    # With a diagonal covariance the statistic is the sum of the two squared t-statistics.
    t_slope = (fit.slope - 1.0) / fit.se_slope
    t_int = fit.intercept / np.sqrt(fit.cov[0][0])
    corr = fit.cov[0][1] / np.sqrt(fit.cov[0][0] * fit.cov[1][1])
    expected = (t_int**2 + t_slope**2 - 2 * corr * t_int * t_slope) / (1 - corr**2)
    assert stat == pytest.approx(expected)
