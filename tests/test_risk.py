import math

import numpy as np
import pandas as pd
import pytest

from quant.risk import (
    annualized_volatility,
    drawdown,
    effective_number_of_positions,
    historical_var_es,
    ledoit_wolf,
    max_drawdown,
    risk_adjusted_ratios,
    risk_contributions,
)

DATES = pd.date_range("2026-01-05", periods=5, freq="B")


# ---------------------------------------------------------------- volatility


def test_volatility_known_answer() -> None:
    # Mean 0; sample variance = 4 * 0.01^2 / (4 - 1) = 0.000133...; std = 0.0115470
    # annualised: 0.0115470 * sqrt(252) = 0.183303
    returns = pd.Series([0.01, -0.01, 0.01, -0.01])

    assert annualized_volatility(returns) == pytest.approx(0.0115470054 * math.sqrt(252))


def test_volatility_of_constant_returns_is_zero() -> None:
    # Exactly zero in theory; floating point leaves ~1e-17.
    assert annualized_volatility(pd.Series([0.002] * 10)) == pytest.approx(0.0, abs=1e-12)


def test_volatility_scales_with_square_root_of_periods() -> None:
    returns = pd.Series([0.01, -0.02, 0.015, 0.0, -0.005])

    daily = annualized_volatility(returns, periods_per_year=1)

    assert annualized_volatility(returns, periods_per_year=52) == pytest.approx(
        daily * math.sqrt(52)
    )


@pytest.mark.parametrize("returns", [[0.01], [0.01, float("nan"), 0.02]])
def test_volatility_rejects_too_few_or_missing(returns: list[float]) -> None:
    with pytest.raises(ValueError):
        annualized_volatility(pd.Series(returns))


# ---------------------------------------------------------------- drawdown


def test_drawdown_known_path() -> None:
    # Peaks: 100, 120, 120, 130, 130.  90/120 - 1 = -25%;  117/130 - 1 = -10%.
    value = pd.Series([100.0, 120.0, 90.0, 130.0, 117.0], index=DATES)

    result = drawdown(value)

    np.testing.assert_allclose(result.to_numpy(), [0.0, 0.0, -0.25, 0.0, -0.10])
    assert result.index.equals(DATES)
    assert max_drawdown(value) == pytest.approx(-0.25)


def test_rising_series_has_no_drawdown() -> None:
    value = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=DATES)

    assert max_drawdown(value) == 0.0


def test_drawdown_uses_only_past_peaks() -> None:
    value = pd.Series([100.0, 90.0, 95.0, 80.0, 85.0], index=DATES)
    higher_future = value.copy()
    higher_future.iloc[-1] = 500.0

    pd.testing.assert_series_equal(drawdown(value).iloc[:-1], drawdown(higher_future).iloc[:-1])


@pytest.mark.parametrize("bad", [[100.0, 0.0, 90.0], [100.0, float("nan"), 90.0]])
def test_drawdown_rejects_non_positive_or_missing(bad: list[float]) -> None:
    with pytest.raises(ValueError):
        drawdown(pd.Series(bad))


# ---------------------------------------------------------------- VaR / ES


def test_var_es_known_answer() -> None:
    # 20 daily returns; at 95% the worst 5% is 1 day out of 20: the -10% day.
    # VaR = 10% (loss not exceeded on 95% of days), ES = average of losses at or beyond it = 10%.
    returns = pd.Series([-0.10, -0.05] + [0.0] * 18)

    var, es = historical_var_es(returns, level=0.95)

    assert var == pytest.approx(0.10)
    assert es == pytest.approx(0.10)


def test_es_averages_the_tail() -> None:
    # 40 returns at 95%: the tail is the 2 worst days (-8% and -4%).
    # VaR = 4%, ES = (8% + 4%) / 2 = 6%.
    returns = pd.Series([-0.08, -0.04, -0.01] + [0.01] * 37)

    var, es = historical_var_es(returns, level=0.95)

    assert var == pytest.approx(0.04)
    assert es == pytest.approx(0.06)


def test_es_is_never_below_var() -> None:
    rng = np.random.default_rng(0)
    returns = pd.Series(rng.normal(0.0, 0.01, 500))

    var, es = historical_var_es(returns)

    assert es >= var > 0


def test_var_rejects_sample_smaller_than_tail() -> None:
    with pytest.raises(ValueError, match="at least 20"):
        historical_var_es(pd.Series([0.01] * 19), level=0.95)


# ---------------------------------------------------------------- risk contributions


def _two_assets(vol_a: float, vol_b: float, n: int = 400, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    a, b = rng.standard_normal(n), rng.standard_normal(n)
    # Remove sample correlation and scale to the exact sample volatility wanted.
    da, db = a - a.mean(), b - b.mean()
    b = b - a * float(da @ db) / float(da @ da)
    a = (a - a.mean()) / a.std(ddof=1) * vol_a
    b = (b - b.mean()) / b.std(ddof=1) * vol_b
    return pd.DataFrame({"A": a, "B": b})


def test_uncorrelated_equal_assets_share_risk_equally() -> None:
    returns = _two_assets(0.01, 0.01)

    result = risk_contributions(returns, pd.Series({"A": 0.5, "B": 0.5}))

    np.testing.assert_allclose(result.to_numpy(), [0.5, 0.5])


def test_uncorrelated_contribution_known_answer() -> None:
    # Uncorrelated: contribution_i = w_i^2 s_i^2 / sum_j w_j^2 s_j^2.
    # A: 0.5^2 * 0.02^2 = 0.0001; B: 0.5^2 * 0.01^2 = 0.000025 -> A = 0.8, B = 0.2
    returns = _two_assets(0.02, 0.01)

    result = risk_contributions(returns, pd.Series({"A": 0.5, "B": 0.5}))

    np.testing.assert_allclose(result.to_numpy(), [0.8, 0.2])


def test_contributions_sum_to_one() -> None:
    rng = np.random.default_rng(3)
    returns = pd.DataFrame(rng.normal(0, 0.01, (300, 4)), columns=list("ABCD"))
    returns["D"] += returns["A"]  # some correlation

    result = risk_contributions(returns, pd.Series({"A": 0.4, "B": 0.3, "C": 0.2, "D": 0.1}))

    assert result.sum() == pytest.approx(1.0)


def test_risk_contributions_rejects_missing_or_mismatched() -> None:
    returns = _two_assets(0.01, 0.01)
    with pytest.raises(ValueError, match="weights"):
        risk_contributions(returns, pd.Series({"A": 1.0}))
    returns.iloc[3, 0] = float("nan")
    with pytest.raises(ValueError, match="missing"):
        risk_contributions(returns, pd.Series({"A": 0.5, "B": 0.5}))


# ---------------------------------------------------------------- concentration


@pytest.mark.parametrize(
    ("weights", "expected"),
    [
        ([0.25, 0.25, 0.25, 0.25], 4.0),  # 1 / (4 * 0.25^2)
        ([1.0, 0.0, 0.0], 1.0),
        ([0.5, 0.3, 0.2], 1 / (0.25 + 0.09 + 0.04)),
        ([2.0, 2.0], 2.0),  # weights are normalised first
    ],
)
def test_effective_number_of_positions(weights: list[float], expected: float) -> None:
    assert effective_number_of_positions(pd.Series(weights)) == pytest.approx(expected)


def test_var_exact_quantile_position_is_not_rounded_down() -> None:
    # 11 returns -0.50, -0.49, ..., -0.40 at 90%: position (11 - 1) * 0.1 = 1 exactly,
    # so VaR is the second worst day (0.49), not the worst (0.50).
    returns = pd.Series(np.arange(11) / 100 - 0.5)

    var, _ = historical_var_es(returns, level=0.9)

    assert var == pytest.approx(0.49)


def test_max_drawdown_rejects_empty() -> None:
    with pytest.raises(ValueError):
        max_drawdown(pd.Series([], dtype=float))


@pytest.mark.parametrize("level", [0.0, 1.0, 1.5])
def test_var_rejects_invalid_level(level: float) -> None:
    with pytest.raises(ValueError, match="level"):
        historical_var_es(pd.Series([0.01] * 50), level=level)


def test_var_rejects_missing_returns() -> None:
    returns = pd.Series([0.01] * 30)
    returns.iloc[5] = float("nan")

    with pytest.raises(ValueError, match="missing"):
        historical_var_es(returns)


def test_risk_contributions_rejects_zero_variance() -> None:
    returns = pd.DataFrame({"A": [0.01] * 30, "B": [0.02] * 30})

    with pytest.raises(ValueError, match="variance"):
        risk_contributions(returns, pd.Series({"A": 0.5, "B": 0.5}))


@pytest.mark.parametrize("weights", [[0.5, -0.5], [0.0, 0.0], [0.5, float("nan")]])
def test_effective_number_rejects_bad_weights(weights: list[float]) -> None:
    with pytest.raises(ValueError):
        effective_number_of_positions(pd.Series(weights))


# ---------------------------------------------------------------- Ledoit-Wolf


def _correlated(n: int, p: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.normal(size=(n, p)) @ rng.normal(size=(p, p)) * 0.01)


def test_ledoit_wolf_matches_scikit_learn() -> None:
    # Reference: sklearn.covariance.LedoitWolf().fit(x).shrinkage_ on this same data
    # (scikit-learn 1.x, checked on 2026-11-24).
    cov, shrinkage = ledoit_wolf(_correlated(60, 8))

    assert shrinkage == pytest.approx(0.15923760527622885, rel=1e-12)
    assert cov.shape == (8, 8)


def test_ledoit_wolf_keeps_the_average_variance_and_shrinks_the_rest() -> None:
    returns = _correlated(60, 8)
    x = returns - returns.mean()
    sample = (x.T @ x) / len(x)

    cov, shrinkage = ledoit_wolf(returns)

    assert 0 < shrinkage < 1
    assert float(cov.to_numpy().trace()) == pytest.approx(float(sample.to_numpy().trace()))
    off = ~np.eye(8, dtype=bool)
    assert np.abs(cov.to_numpy()[off]).sum() == pytest.approx(
        (1 - shrinkage) * np.abs(sample.to_numpy()[off]).sum()
    )
    assert np.linalg.eigvalsh(cov.to_numpy()).min() > 0


def test_ledoit_wolf_shrinks_less_with_more_data() -> None:
    _, few = ledoit_wolf(_correlated(30, 8, seed=1))
    _, many = ledoit_wolf(_correlated(3000, 8, seed=1))

    assert many < few


def test_ledoit_wolf_rejects_gaps() -> None:
    with pytest.raises(ValueError):
        ledoit_wolf(pd.DataFrame({"a": [0.01, None, 0.02]}))


# ---------------------------------------------------------------- ratios


def test_ratios_on_a_known_path() -> None:
    value = pd.Series([100.0, 110.0, 99.0, 108.9])  # +10%, -10%, +10%

    ratios = risk_adjusted_ratios(value)

    r = np.array([0.1, -0.1, 0.1])
    assert ratios["sharpe"] == pytest.approx(r.mean() / r.std(ddof=1) * np.sqrt(252))
    assert ratios["sortino"] == pytest.approx(r.mean() / np.sqrt(0.01 / 3) * np.sqrt(252))
    annual = (108.9 / 100) ** (252 / 3) - 1
    assert ratios["calmar"] == pytest.approx(annual / 0.1)


def test_ratios_without_falls_or_variation_are_undefined() -> None:
    ratios = risk_adjusted_ratios(pd.Series([100.0, 101.0, 102.01]))

    assert ratios["sortino"] is None
    assert ratios["calmar"] is None
    assert ratios["sharpe"] is None  # constant 1% a day: no variation
