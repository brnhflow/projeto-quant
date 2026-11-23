import math

import numpy as np
import pandas as pd
import pytest

from quant.risk import (
    annualized_volatility,
    drawdown,
    effective_number_of_positions,
    historical_var_es,
    max_drawdown,
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
