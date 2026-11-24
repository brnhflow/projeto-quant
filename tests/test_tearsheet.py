import math

import numpy as np
import pandas as pd
import pytest

from quant.tearsheet import (
    annual_returns,
    drawdown_periods,
    monthly_returns,
    return_histogram,
    rolling_sharpe,
    rolling_volatility,
    summary,
)


def _series(values: list[float], start: str = "2024-01-01") -> pd.Series:
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_monthly_returns_run_from_one_month_end_to_the_next() -> None:
    dates = pd.bdate_range("2024-01-01", "2024-03-29")
    value = pd.Series(100.0, index=dates)
    value[dates.month == 2] = 110.0
    value[dates.month == 3] = 99.0

    months = monthly_returns(value)

    assert months.tolist() == pytest.approx([0.0, 0.10, -0.10])
    assert [d.month for d in months.index] == [1, 2, 3]


def test_monthly_returns_compound_to_the_total() -> None:
    rng = np.random.default_rng(1)
    value = _series(list(100 * np.cumprod(1 + rng.normal(0, 0.01, 400))))

    months = monthly_returns(value)

    assert float((1 + months).prod()) == pytest.approx(value.iloc[-1] / value.iloc[0])


def test_annual_returns_with_a_partial_first_year() -> None:
    value = pd.Series(
        [100.0, 120.0, 150.0],
        index=pd.DatetimeIndex(["2023-06-01", "2023-12-29", "2024-12-31"]),
    )

    years = annual_returns(value)

    assert years.to_dict() == pytest.approx({2023: 0.20, 2024: 0.25})


def test_drawdown_periods_have_peak_trough_and_recovery() -> None:
    value = _series([100, 120, 90, 120, 130, 117, 140])

    periods = drawdown_periods(value)

    first, second = periods
    assert first.depth == pytest.approx(-0.25)
    assert (first.peak, first.trough, first.recovery) == (
        value.index[1],
        value.index[2],
        value.index[3],
    )
    assert (first.days_down, first.days_to_recover) == (1, 1)
    assert second.depth == pytest.approx(-0.10)
    assert second.recovery == value.index[6]


def test_an_open_drawdown_has_no_recovery() -> None:
    value = _series([100, 110, 99, 105])

    (period,) = drawdown_periods(value)

    assert period.recovery is None
    assert period.days_to_recover is None
    assert period.depth == pytest.approx(-0.10)


def test_drawdown_periods_keep_the_deepest_ones() -> None:
    value = _series([100, 99, 100, 90, 100, 95, 100, 80, 100])

    depths = [p.depth for p in drawdown_periods(value, top=2)]

    assert depths == pytest.approx([-0.20, -0.10])


def test_rolling_ratios_match_the_window_computed_directly() -> None:
    rng = np.random.default_rng(2)
    value = _series(list(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, 300))))
    last = value.pct_change().dropna().iloc[-126:]

    sharpe, vol = rolling_sharpe(value), rolling_volatility(value)

    assert sharpe.iloc[-1] == pytest.approx(last.mean() / last.std() * math.sqrt(252))
    assert vol.iloc[-1] == pytest.approx(last.std() * math.sqrt(252))
    assert len(sharpe) == 299 - 125


def test_histogram_counts_every_day_and_the_normal_matches_in_total() -> None:
    rng = np.random.default_rng(3)
    value = _series(list(100 * np.cumprod(1 + rng.normal(0, 0.01, 2000))))

    h = return_histogram(value)

    assert sum(h.counts) == 1999
    assert len(h.edges) == len(h.counts) + 1
    # Within four standard deviations a normal holds 99.99% of the mass.
    assert sum(h.normal) == pytest.approx(1999, rel=1e-3)


def test_summary_on_a_known_series() -> None:
    # Doubles in exactly one year of trading days, with a single 10% fall on the way.
    up = (2 / 0.9) ** (1 / 251)
    values = [100.0]
    for k in range(252):
        values.append(values[-1] * (0.9 if k == 100 else up))
    value = _series(values)

    s = summary(value)

    assert s["cagr"] == pytest.approx(1.0)
    assert s["maxDrawdown"] == pytest.approx(-0.10)
    assert s["worstDay"] == pytest.approx(-0.10)
    assert s["positiveDays"] == pytest.approx(251 / 252)
    assert s["days"] == 252
    # A day of -10% among gains is a heavy left tail.
    assert s["skew"] is not None and s["skew"] < -10
    assert s["kurtosis"] is not None and s["kurtosis"] > 100


def test_summary_of_a_normal_sample_has_small_skew_and_kurtosis() -> None:
    rng = np.random.default_rng(4)
    steps = np.asarray(rng.normal(0, 0.01, 5000), dtype=np.float64)
    value = _series((100 * np.exp(steps.cumsum())).tolist())

    s = summary(value)

    assert abs(s["skew"] or 0) < 0.15
    assert abs(s["kurtosis"] or 0) < 0.3


def test_invalid_input_is_refused() -> None:
    with pytest.raises(ValueError):
        summary(_series([100.0]))
    with pytest.raises(ValueError):
        monthly_returns(_series([100.0, -1.0]))
