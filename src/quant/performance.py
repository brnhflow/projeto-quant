"""Gain on the money actually invested, and its annual rate (money-weighted return).

The rest of the report treats today's quantities as held over the whole history, which
describes the portfolio. Here the question is what *you* earned: each position's cost (the
average price paid, converted at the exchange rate of the purchase date) against what it is
worth today.

The money-weighted return is the internal rate of return of those cash flows (XIRR): the
yearly rate ``r`` that makes ``sum(flow_k / (1 + r) ** (days_k / 365))`` zero. Unlike the
time-weighted return, it rewards or punishes the timing of the money put in.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

YEAR_DAYS = 365.0


def npv(rate: float, flows: Sequence[tuple[pd.Timestamp, float]]) -> float:
    """Net present value at the date of the first flow, with actual/365 year fractions."""
    start = min(date for date, _ in flows)
    return sum(amount / (1 + rate) ** ((date - start).days / YEAR_DAYS) for date, amount in flows)


def xirr(flows: Sequence[tuple[pd.Timestamp, float]]) -> float | None:
    """Annual internal rate of return of dated cash flows (negative = money paid in).

    Solved by bisection on ``(-99.99%, 1,000,000%)``, where the NPV is monotonic for flows
    that start with money paid in and end with money received.

    Returns
    -------
    float or None
        None when the flows do not have both signs, span less than one day, or have no
        root in the interval.

    """
    if len(flows) < 2:
        return None
    amounts = [a for _, a in flows]
    dates = [d for d, _ in flows]
    if not (min(amounts) < 0 < max(amounts)) or (max(dates) - min(dates)).days < 1:
        return None
    low, high = -0.9999, 10_000.0
    f_low, f_high = npv(low, flows), npv(high, flows)
    if math.isnan(f_low) or math.isnan(f_high) or f_low * f_high > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = npv(mid, flows)
        if f_mid == 0 or high - low < 1e-12:
            return mid
        if f_low * f_mid < 0:
            high, f_high = mid, f_mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2
