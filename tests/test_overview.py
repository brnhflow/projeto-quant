import math

import numpy as np
import pandas as pd
import pytest

from quant.data.market import Series
from quant.overview import STALE_DAYS, UNIVERSE, base_position, market_overview


def _walk(
    dates: pd.DatetimeIndex, sd: float = 0.01, seed: int = 0, start: float = 100.0
) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(start * np.exp(rng.normal(0, sd, len(dates)).cumsum()), index=dates)


def _at(dates: pd.DatetimeIndex, period: str) -> pd.Timestamp:
    k = base_position(dates, period)
    assert k is not None
    return pd.Timestamp(dates[k])


def test_base_positions_use_calendar_days_on_every_market() -> None:
    weekdays = pd.bdate_range("2026-01-02", "2026-03-13")  # a Friday
    every_day = pd.date_range("2026-01-02", "2026-03-13")

    assert _at(weekdays, "1D") == pd.Timestamp("2026-03-12")
    assert _at(weekdays, "1W") == pd.Timestamp("2026-03-06")
    assert _at(every_day, "1W") == pd.Timestamp("2026-03-06")
    assert _at(weekdays, "1M") == pd.Timestamp("2026-02-13")


def test_year_to_date_needs_the_previous_year_end() -> None:
    dates = pd.bdate_range("2025-12-01", "2026-02-10")
    late = pd.bdate_range("2026-01-05", "2026-02-10")

    assert _at(dates, "YTD") == pd.Timestamp("2025-12-31")
    assert base_position(late, "YTD") is None
    assert base_position(late, "12M") is None


def test_changes_and_unusualness_follow_their_definitions() -> None:
    dates = pd.bdate_range("2025-01-01", periods=320)
    prices = _walk(dates, 0.01)
    prices.iloc[-1] = prices.iloc[-2] * 1.05  # a 5% day on a series that moves ~1%

    out = market_overview({"^GSPC": Series(prices, "S&P", "USD")})

    assert out is not None
    item = out["items"][0]
    sd = prices.pct_change().dropna().iloc[-255:-5].std()
    assert item["change"]["1D"] == pytest.approx(0.05, abs=1e-6)
    assert item["z"]["1D"] == pytest.approx(0.05 / sd, abs=0.01)
    assert item["z"]["1D"] > out["unusualZ"]
    week = base_position(pd.DatetimeIndex(prices.index), "1W")
    assert week is not None
    days = len(prices) - 1 - week
    expected = (prices.iloc[-1] / prices.iloc[week] - 1) / (sd * math.sqrt(days))
    assert item["z"]["1W"] == pytest.approx(expected, abs=0.01)


def test_rates_change_in_points_not_percent() -> None:
    dates = pd.bdate_range("2025-01-01", periods=300)
    yields = pd.Series(4.0, index=dates) + np.random.default_rng(1).normal(0, 0.03, 300).cumsum()
    yields.iloc[-1] = yields.iloc[-2] + 0.25

    out = market_overview({"^TNX": Series(yields)})

    assert out is not None
    assert out["items"][0]["rate"] is True
    assert out["items"][0]["change"]["1D"] == pytest.approx(0.0025, abs=1e-9)  # 0.25 points


def test_stale_and_short_series_are_left_out_and_order_follows_the_list() -> None:
    dates = pd.bdate_range("2025-01-01", periods=300)
    stale = _walk(dates[: -(STALE_DAYS + 5)], seed=2)
    series = {
        "BTC-USD": Series(_walk(dates, seed=3)),
        "^BVSP": Series(_walk(dates, seed=4)),
        "^GSPC": Series(stale),
        "^IXIC": Series(_walk(dates[-10:], seed=5)),
    }

    out = market_overview(series)

    assert out is not None
    order = [i.symbol for i in UNIVERSE]
    symbols = [i["symbol"] for i in out["items"]]
    assert symbols == ["^BVSP", "BTC-USD"]
    assert symbols == sorted(symbols, key=order.index)
    assert market_overview({}) is None


def test_correlation_with_the_portfolio_is_weekly_and_signed() -> None:
    dates = pd.bdate_range("2025-01-01", periods=320)
    portfolio = _walk(dates, seed=6)
    mirror = 1e4 / portfolio  # moves exactly against the portfolio

    out = market_overview(
        {
            "^GSPC": Series(portfolio),
            "^IXIC": Series(mirror),
            "^BVSP": Series(_walk(dates, seed=7)),
        },
        portfolio,
    )

    assert out is not None
    corr = {i["symbol"]: i["corr"] for i in out["items"]}
    assert corr["^GSPC"] == pytest.approx(1.0, abs=1e-6)
    assert corr["^IXIC"] < -0.95
    assert abs(corr["^BVSP"]) < 0.5


def test_spark_lines_are_compact_and_end_on_the_last_price() -> None:
    dates = pd.bdate_range("2025-01-01", periods=320)
    prices = _walk(dates, seed=8)

    out = market_overview({"^GSPC": Series(prices)})

    assert out is not None
    spark = out["items"][0]["spark"]
    assert len(spark["t"]) == len(spark["v"]) < 160
    assert spark["v"][-1] == pytest.approx(prices.iloc[-1], rel=1e-4)
    assert spark["t"] == sorted(spark["t"])
