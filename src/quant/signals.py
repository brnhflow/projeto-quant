"""Rule-based signals worth a closer look. Each rule is fixed, simple and explained.

They are prompts to investigate, never advice: a price far below its high may be a
bargain or a company in trouble; a high dividend yield may be a cheap stock or a dividend
about to be cut. The report says so next to every signal.

- Far from the 52-week high: the last price at least 20% below the highest close of the
  last 252 trading days.
- Dividend yield above its own history: trailing-12-month dividends over today's price,
  at least 25% above the median of the same ratio measured at each month-end of the
  last five years.
- Diversifier: an index that, if it took 10% of the portfolio (taken proportionally from
  every position), would lower the volatility of the last year the most.
- Concentration: one position over 25% of the value, or over 35% of the risk.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

HIGH_WINDOW = 252
FAR_FROM_HIGH = -0.20
YIELD_YEARS = 5
YIELD_PREMIUM = 1.25
DIVERSIFIER_WEIGHT = 0.10
MIN_VOL_GAIN = 0.003  # 0.3 percentage points of annual volatility
CONCENTRATION_WEIGHT = 0.25
CONCENTRATION_RISK = 0.35


@dataclass(frozen=True)
class HighGap:
    """How far the last price is below the highest close of the last year."""

    gap: float  # e.g. -0.32 for 32% below the high
    high: float
    high_date: pd.Timestamp
    last: float


def gap_from_high(prices: pd.Series) -> HighGap | None:
    """Last price against the highest close of the last :data:`HIGH_WINDOW` prices."""
    known = prices.dropna()
    if len(known) < HIGH_WINDOW // 2:
        return None
    window = known.iloc[-HIGH_WINDOW:]
    high_at = window.idxmax()
    high = float(window.max())
    last = float(known.iloc[-1])
    if not high > 0:
        return None
    return HighGap(last / high - 1, high, pd.Timestamp(str(high_at)), last)


@dataclass(frozen=True)
class YieldCheck:
    """Trailing dividend yield today against its own five-year median."""

    current: float
    median: float
    months: int


def yield_vs_history(prices: pd.Series, dividends: pd.Series) -> YieldCheck | None:
    """Trailing-12-month yield now and its median at past month-ends.

    Needs at least three years of month-ends with a price and some dividend in the
    trailing year; otherwise None.
    """
    known = prices.dropna()
    if known.empty or dividends.empty:
        return None
    last = pd.Timestamp(known.index[-1])
    points: list[float] = []
    start = last - pd.DateOffset(years=YIELD_YEARS)
    for end in pd.date_range(start, last, freq="ME"):
        if end >= last:
            continue
        before = known[known.index <= end]
        if before.empty:
            continue
        price = float(before.iloc[-1])
        paid = dividends[
            (dividends.index > end - pd.DateOffset(years=1)) & (dividends.index <= end)
        ]
        if paid.empty or not price > 0:
            continue
        points.append(float(paid.sum()) / price)
    if len(points) < 36:
        return None
    ttm = dividends[(dividends.index > last - pd.DateOffset(years=1)) & (dividends.index <= last)]
    current = float(ttm.sum()) / float(known.iloc[-1])
    return YieldCheck(current, float(np.median(points)), len(points))


def diversification_gain(
    portfolio: pd.Series, candidate: pd.Series, weight: float = DIVERSIFIER_WEIGHT
) -> tuple[float, float, float] | None:
    """Annual volatility now, with ``weight`` moved into ``candidate``, and their correlation.

    Uses daily returns of the last year where both have prices. Returns
    ``(vol_now, vol_with, correlation)`` or None with fewer than 120 common days.
    """
    joined = pd.concat(
        [portfolio.pct_change(fill_method=None), candidate.pct_change(fill_method=None)],
        axis=1,
        keys=["p", "c"],
    ).dropna()
    joined = joined.iloc[-HIGH_WINDOW:]
    if len(joined) < 120:
        return None
    p = joined["p"].to_numpy(dtype=float)
    c = joined["c"].to_numpy(dtype=float)
    mixed = (1 - weight) * p + weight * c
    scale = math.sqrt(252)
    corr = float(np.corrcoef(p, c)[0, 1])  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    return float(p.std(ddof=1) * scale), float(mixed.std(ddof=1) * scale), corr
