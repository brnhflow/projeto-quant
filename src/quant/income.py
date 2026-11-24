"""Expected dividend income: the next 12 months month by month, and how it may grow.

Built only from what each asset actually paid:

- Calendar: for each calendar month, the average paid in that month over the last two
  years. A fund that pays monthly shows 12 bars; a company that pays in May and November
  shows two. Summed over the year this is the average of the last two years' payments.
- Growth: the median of the year-on-year changes in the amount paid per share over the
  last five full years. The median ignores a single special dividend; it is limited to
  -30%..+30% a year, and left at zero with fewer than three years of payments.

Everything is per unit held today, converted at today's exchange rate, before taxes. A
company can cut or stop dividends at any time: this is a projection of the past.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

CALENDAR_YEARS = 2
GROWTH_YEARS = 5
GROWTH_LIMIT = 0.30
MIN_GROWTH_YEARS = 3


@dataclass(frozen=True)
class IncomeOutlook:
    """Expected payments per unit for the next 12 months, and a yearly growth rate."""

    months: list[pd.Timestamp]  # first day of each of the next 12 months
    per_unit: list[float]  # expected payment per unit in each of those months
    growth: float | None  # yearly growth of the payment per unit; None if not measurable
    paid_years: int  # full years among the last GROWTH_YEARS with any payment
    last: pd.Timestamp | None  # date of the latest payment


def next_months(last: pd.Timestamp) -> list[pd.Timestamp]:
    """First day of each of the 12 months after the month of ``last``."""
    first = (last.normalize().replace(day=1) + pd.DateOffset(months=1)).normalize()
    return [pd.Timestamp(first + pd.DateOffset(months=k)) for k in range(12)]


def outlook(dividends: pd.Series, last: pd.Timestamp) -> IncomeOutlook:
    """Project payments per unit after ``last`` from the dividend history up to it.

    Parameters
    ----------
    dividends : pd.Series
        Amount per unit, indexed by payment date (any order, may be empty).
    last : pd.Timestamp
        Date of the analysis; payments after it are ignored (no look-ahead).

    """
    if dividends.empty:
        dividends = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    paid = dividends[dividends.index <= last].sort_index()
    dates = pd.DatetimeIndex(paid.index)
    payments = [(pd.Timestamp(d), float(v)) for d, v in zip(dates, paid.to_numpy(), strict=True)]
    months = next_months(last)

    since = last - pd.DateOffset(years=CALENDAR_YEARS)
    by_month: dict[int, float] = {}
    for date, amount in payments:
        if date > since:
            by_month[date.month] = by_month.get(date.month, 0.0) + amount / CALENDAR_YEARS
    per_unit = [by_month.get(m.month, 0.0) for m in months]

    years = list(range(last.year - GROWTH_YEARS, last.year))  # full years only
    yearly = dict.fromkeys(years, 0.0)
    for date, amount in payments:
        if date.year in yearly:
            yearly[date.year] += amount
    amounts = [yearly[y] for y in years]
    paid_years = sum(1 for a in amounts if a > 0)
    growth: float | None = None
    if paid_years >= MIN_GROWTH_YEARS and all(a > 0 for a in amounts):
        changes = sorted(amounts[i] / amounts[i - 1] - 1 for i in range(1, len(amounts)))
        mid = len(changes) // 2
        median = changes[mid] if len(changes) % 2 else (changes[mid - 1] + changes[mid]) / 2
        growth = min(GROWTH_LIMIT, max(-GROWTH_LIMIT, median))
    return IncomeOutlook(
        months=months,
        per_unit=per_unit,
        growth=growth,
        paid_years=paid_years,
        last=payments[-1][0] if payments else None,
    )
