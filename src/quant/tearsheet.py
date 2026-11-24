"""Tearsheet: the standard one-page summary of a return series.

The layout follows what fund factsheets and libraries such as pyfolio and QuantStats show:
annual statistics, a month-by-month return table, rolling Sharpe and volatility, the worst
drawdowns with their recovery, and the distribution of daily returns against a normal.

Every function takes a value series (positive, in date order, business days) and uses only
its own dates, so a benchmark can be summarised the same way on the days it traded.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt
import pandas as pd

from quant.risk import TRADING_DAYS, drawdown, historical_var_es, risk_adjusted_ratios

ROLLING_WINDOW = 126  # six months of trading days
TOP_DRAWDOWNS = 5

Vector = npt.NDArray[np.float64]


def _check(value: pd.Series) -> None:
    if len(value) < 2 or value.isna().any() or (value <= 0).any():
        raise ValueError("need at least two positive values and no missing ones")
    if not value.index.is_monotonic_increasing:
        raise ValueError("dates must be in increasing order")


def _period_ends(
    value: pd.Series, key: npt.NDArray[np.int64]
) -> tuple[npt.NDArray[np.bool_], Vector]:
    """Mask of each period's last day, and the return of each period.

    Each period runs from the previous period's last value to its own last value; the first
    one starts at the first value.
    """
    v = value.to_numpy(dtype=np.float64)
    last = np.ones(len(key), dtype=np.bool_)
    last[:-1] = key[1:] != key[:-1]
    ends = v[last]
    previous = np.empty_like(ends)
    previous[0] = v[0]
    previous[1:] = ends[:-1]
    return last, ends / previous - 1


def monthly_returns(value: pd.Series) -> pd.Series:
    """Return of each calendar month, from the previous month's last value to this one's.

    The first month is measured from the first value, so a series that starts mid-month
    gets a partial first month (as fund factsheets show it).

    Returns
    -------
    pd.Series
        Indexed by month-end ``Timestamp``; decimals.

    """
    _check(value)
    dates = pd.DatetimeIndex(value.index)
    key = np.asarray(dates.year * 12 + dates.month, dtype=np.int64)
    last, returns = _period_ends(value, key)
    month_ends = (dates[last] + pd.offsets.MonthEnd(0)).normalize()
    return pd.Series(returns, index=month_ends)


def annual_returns(value: pd.Series) -> pd.Series:
    """Return of each calendar year (the first and last years may be partial)."""
    _check(value)
    key = np.asarray(pd.DatetimeIndex(value.index).year, dtype=np.int64)
    last, returns = _period_ends(value, key)
    return pd.Series(returns, index=key[last])


@dataclass(frozen=True)
class DrawdownPeriod:
    """One fall from a peak and, if it happened, the recovery to that peak."""

    peak: pd.Timestamp
    trough: pd.Timestamp
    recovery: pd.Timestamp | None  # first date back at the peak; None if not yet
    depth: float  # negative decimal
    days_down: int  # trading days from peak to trough
    days_to_recover: int | None  # trading days from trough to recovery


def drawdown_periods(value: pd.Series, top: int = TOP_DRAWDOWNS) -> list[DrawdownPeriod]:
    """Find the ``top`` deepest drawdowns, each counted once from peak to recovery.

    A drawdown period starts at the last high before the value falls and ends on the first
    day the value is back at that high. The open drawdown at the end of the series is
    included, with ``recovery`` None.
    """
    _check(value)
    dd: Vector = drawdown(value).to_numpy(dtype=np.float64)
    dates = pd.DatetimeIndex(value.index)
    periods: list[DrawdownPeriod] = []
    i, n = 0, len(dd)
    while i < n:
        if dd[i] >= 0:
            i += 1
            continue
        start = i - 1  # the peak: the last day at a high (dd[0] is always 0)
        end = i
        while end < n and dd[end] < 0:
            end += 1
        segment = dd[i:end]
        low = i + int(segment.argmin())
        recovered = end < n
        periods.append(
            DrawdownPeriod(
                peak=pd.Timestamp(dates[start]),
                trough=pd.Timestamp(dates[low]),
                recovery=pd.Timestamp(dates[end]) if recovered else None,
                depth=float(dd[low]),
                days_down=low - start,
                days_to_recover=end - low if recovered else None,
            )
        )
        i = end
    periods.sort(key=lambda p: p.depth)
    return periods[:top]


def rolling_sharpe(value: pd.Series, window: int = ROLLING_WINDOW) -> pd.Series:
    """Annualised Sharpe ratio (no risk-free rate) over a moving window of daily returns."""
    _check(value)
    r = value.pct_change().dropna()
    mean = r.rolling(window).mean()
    sd = r.rolling(window).std(ddof=1)
    return (mean / sd.where(sd > 1e-12) * math.sqrt(TRADING_DAYS)).dropna()


def rolling_volatility(value: pd.Series, window: int = ROLLING_WINDOW) -> pd.Series:
    """Annualised volatility over a moving window of daily returns."""
    _check(value)
    r = value.pct_change().dropna()
    return (r.rolling(window).std(ddof=1) * math.sqrt(TRADING_DAYS)).dropna()


@dataclass(frozen=True)
class Histogram:
    """Daily returns in equal bins, with the counts a normal distribution would give."""

    edges: list[float]
    counts: list[int]
    normal: list[float]


def return_histogram(value: pd.Series, bins: int = 41) -> Histogram:
    """Histogram of daily returns, symmetric around zero and clipped at 4 standard deviations.

    Returns beyond the outer edges are counted in the outer bins, so the tails stay visible.
    ``normal`` is the expected count in each bin under a normal distribution with the same
    mean and standard deviation.
    """
    _check(value)
    r = value.pct_change().dropna().to_numpy(dtype=np.float64)
    sd = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    reach = 4 * sd if sd > 0 else max(abs(float(r.min())), abs(float(r.max())), 1e-4)
    edges = [-reach + 2 * reach * k / bins for k in range(bins + 1)]
    # Each return goes to its bin; beyond the outer edges, to the outer bins.
    counts = [0] * bins
    for x in r.tolist():
        k = math.floor((x + reach) / (2 * reach) * bins)
        counts[min(bins - 1, max(0, k))] += 1
    mean = float(r.mean())
    if sd > 0:
        cdf = [0.5 * (1 + math.erf((e - mean) / (sd * math.sqrt(2)))) for e in edges]
        normal = [(b - a) * len(r) for a, b in itertools.pairwise(cdf)]
    else:
        normal = [0.0] * bins
    return Histogram(edges=edges, counts=counts, normal=normal)


def summary(value: pd.Series) -> dict[str, float | int | None]:
    """Compute the tearsheet's statistics table for one value series.

    Keys: ``cagr``, ``volatility``, ``sharpe``, ``sortino``, ``calmar``, ``maxDrawdown``,
    ``longestDrawdown`` (trading days from a peak back to it, or to the end if open),
    ``skew``, ``kurtosis`` (excess), ``bestDay``, ``worstDay``, ``positiveDays``,
    ``bestMonth``, ``worstMonth``, ``positiveMonths``, ``var``, ``es`` (95%, one day),
    ``years`` and ``days``.

    Skew and kurtosis are the bias-adjusted sample estimates (as pandas computes them); a
    normal distribution has both at zero.
    """
    _check(value)
    r = value.pct_change().dropna()
    days = len(r)
    years = days / TRADING_DAYS
    growth = float(value.iloc[-1] / value.iloc[0])
    ratios = risk_adjusted_ratios(value)
    months = monthly_returns(value)
    dd = drawdown(value).to_numpy(dtype=float)
    longest = run = 0
    for x in dd:
        run = run + 1 if x < 0 else 0
        longest = max(longest, run)
    var_es = historical_var_es(r) if days >= 20 else None
    sd = float(r.std(ddof=1)) if days > 1 else math.nan
    return {
        "cagr": growth ** (1 / years) - 1 if years > 0 else None,
        "volatility": sd * math.sqrt(TRADING_DAYS) if days > 1 else None,
        "sharpe": ratios["sharpe"],
        "sortino": ratios["sortino"],
        "calmar": ratios["calmar"],
        "maxDrawdown": float(dd.min()),
        "longestDrawdown": longest,
        "skew": float(cast(float, r.skew())) if days > 2 else None,
        "kurtosis": float(cast(float, r.kurt())) if days > 3 else None,
        "bestDay": float(r.max()),
        "worstDay": float(r.min()),
        "positiveDays": float((r > 0).mean()),
        "bestMonth": float(months.max()),
        "worstMonth": float(months.min()),
        "positiveMonths": float((months > 0).mean()),
        "var": var_es[0] if var_es else None,
        "es": var_es[1] if var_es else None,
        "years": years,
        "days": days,
    }
