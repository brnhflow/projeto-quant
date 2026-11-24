import numpy as np
import pandas as pd
import pytest

from quant.signals import diversification_gain, gap_from_high, yield_vs_history


def test_gap_from_high_on_a_known_path() -> None:
    days = pd.bdate_range("2025-01-01", periods=300)
    prices = pd.Series(100.0, index=days)
    prices.iloc[150] = 125.0  # the high of the last year
    prices.iloc[-1] = 75.0

    gap = gap_from_high(prices)

    assert gap is not None
    assert gap.gap == pytest.approx(-0.40)
    assert gap.high == 125.0
    assert gap.high_date == days[150]


def test_high_older_than_a_year_is_forgotten() -> None:
    days = pd.bdate_range("2024-01-01", periods=400)
    prices = pd.Series(100.0, index=days)
    prices.iloc[10] = 500.0  # more than 252 trading days ago

    gap = gap_from_high(prices)

    assert gap is not None
    assert gap.gap == pytest.approx(0.0)


def test_gap_needs_half_a_year_of_prices() -> None:
    assert (
        gap_from_high(pd.Series([1.0, 2.0], index=pd.bdate_range("2025-01-01", periods=2))) is None
    )


def test_yield_now_against_its_own_history() -> None:
    days = pd.bdate_range("2020-01-01", "2025-12-31")
    prices = pd.Series(100.0, index=days)
    prices.iloc[-1] = 50.0  # price halves at the end
    pay_days = pd.to_datetime([f"{y}-06-15" for y in range(2019, 2026)])
    dividends = pd.Series(5.0, index=pay_days)  # 5 a year: a 5% yield at 100

    check = yield_vs_history(prices, dividends)

    assert check is not None
    assert check.median == pytest.approx(0.05)
    assert check.current == pytest.approx(0.10)  # same dividend, half the price
    assert check.months >= 36


def test_yield_check_needs_three_years() -> None:
    days = pd.bdate_range("2024-06-01", "2025-12-31")
    prices = pd.Series(10.0, index=days)
    dividends = pd.Series(1.0, index=pd.to_datetime(["2025-03-01"]))

    assert yield_vs_history(prices, dividends) is None


def test_an_uncorrelated_asset_lowers_volatility() -> None:
    days = pd.bdate_range("2024-01-01", periods=300)
    rng = np.random.default_rng(1)
    portfolio = pd.Series(100 * np.exp(rng.normal(0, 0.012, 300).cumsum()), index=days)
    independent = pd.Series(100 * np.exp(rng.normal(0, 0.006, 300).cumsum()), index=days)

    result = diversification_gain(portfolio, independent)

    assert result is not None
    now, after, corr = result
    assert after < now
    assert abs(corr) < 0.2
    # Independent assets: var = 0.81 var_p + 0.01 var_c.
    p = portfolio.pct_change().dropna().iloc[-252:]
    c = independent.pct_change().dropna().iloc[-252:]
    expected = np.sqrt(0.81 * p.var() + 0.01 * c.var() + 2 * 0.09 * p.cov(c)) * np.sqrt(252)
    assert after == pytest.approx(expected)


def test_the_portfolio_itself_does_not_diversify() -> None:
    days = pd.bdate_range("2024-01-01", periods=300)
    rng = np.random.default_rng(2)
    portfolio = pd.Series(100 * np.exp(rng.normal(0, 0.01, 300).cumsum()), index=days)

    result = diversification_gain(portfolio, portfolio * 3)

    assert result is not None
    assert result[1] == pytest.approx(result[0])
    assert result[2] == pytest.approx(1.0)
