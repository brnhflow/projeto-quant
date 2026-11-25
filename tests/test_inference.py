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
