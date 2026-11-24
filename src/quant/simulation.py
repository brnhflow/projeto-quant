"""Simulate where the portfolio could be in 1 to 5 years, and check the method on the past.

Paths are built by resampling blocks of the portfolio's own daily returns (the stationary
bootstrap of :mod:`quant.validation`), so fat tails and calm or turbulent stretches are
kept as they were. Two versions are produced:

- without trend: returns are shifted to average zero, so only the size of the swings is
  taken from the past. This is the honest default: a few good years do not make good
  years more likely.
- with the historical trend: the past average return is kept, to show what repeating
  it would mean.

The method is checked like a weather forecast: month after month, using only the data
before that month, it states a range where the next month should end with 90%
probability. If the real outcome lands inside about 90% of the time, the ranges are
honest; much less means the simulation underestimates risk.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from quant import core
from quant.validation import binomial_cdf, stationary_bootstrap_matrix

Matrix = npt.NDArray[np.float64]
TRADING_DAYS = 252
MONTH = 21


def simulate_growth(
    returns: npt.NDArray[np.float64],
    days: int,
    paths: int,
    *,
    demean: bool,
    seed: int = 0,
    mean_block: float | None = None,
) -> Matrix:
    """Growth of 1 unit along ``paths`` simulated paths, one row per path.

    Parameters
    ----------
    returns : array
        Historical daily simple returns, in order.
    days : int
        Length of each path.
    paths : int
        Number of paths.
    demean : bool
        Shift log returns to average zero (no trend) before resampling.
    seed : int
        Fixed so the same history always gives the same simulation.
    mean_block : float, optional
        Average block length; default ``n ** (1/3)``, at least 5 days.

    Returns
    -------
    array of shape (paths, days)
        Value of 1 invested at the start, after each day.

    """
    simple = np.asarray(returns, dtype=float)
    if len(simple) < 20 or not np.isfinite(simple).all() or (simple <= -1).any():
        raise ValueError("need at least 20 finite returns above -100%")
    logs: Matrix = np.log1p(simple)
    if demean:
        logs = logs - logs.mean()
    block = mean_block if mean_block is not None else max(5.0, len(logs) ** (1 / 3))
    fast = core.simulate_growth(logs, days, paths, block, seed)
    if fast is not None:  # same algorithm in C++, in parallel (cpp/include/quant/risk.hpp)
        return fast
    rng = np.random.default_rng(seed)
    # Each path is built from consecutive resamples of the history.
    pieces = math.ceil(days / len(logs))
    out: Matrix = np.empty((paths, days))
    n = len(logs)
    idx = np.empty((paths, pieces * n), dtype=np.int64)
    for piece in range(pieces):
        idx[:, piece * n : (piece + 1) * n] = stationary_bootstrap_matrix(n, block, rng, paths)
    out[:] = np.exp(logs[idx[:, :days]].cumsum(axis=1))
    return out


def quantile_table(growth: Matrix, probabilities: tuple[float, ...]) -> Matrix:
    """Quantiles across paths for each day: shape (len(probabilities), days)."""
    ordered = growth.copy()
    ordered.sort(axis=0)
    n = ordered.shape[0]
    table: Matrix = np.empty((len(probabilities), ordered.shape[1]))
    for row, q in enumerate(probabilities):
        table[row] = ordered[min(n - 1, max(0, round(q * (n - 1))))]
    return table


def drawdown_probability(growth: Matrix, threshold: float) -> float:
    """Share of paths that, at some point, fall ``threshold`` (e.g. 0.2) below their peak."""
    padded: Matrix = np.ones((growth.shape[0], growth.shape[1] + 1))
    padded[:, 1:] = growth  # the start (1.0) counts as the first peak
    peaks: Matrix = np.maximum.accumulate(padded, axis=1)  # pyright: ignore[reportUnknownMemberType]
    worst = (growth / peaks[:, 1:] - 1).min(axis=1)
    return float((worst <= -threshold).mean())


@dataclass(frozen=True)
class Calibration:
    """How often the real next month landed inside the simulated range."""

    horizon: int
    level: float
    checks: int
    inside: int
    p_value: float

    @property
    def coverage(self) -> float:
        """Share of checks where the outcome was inside the range."""
        return self.inside / self.checks


def calibrate(
    returns: pd.Series,
    *,
    horizon: int = MONTH,
    level: float = 0.90,
    min_train: int = TRADING_DAYS,
    paths: int = 1000,
) -> Calibration:
    """Walk forward month by month: predict a range with past data, then check it.

    Non-overlapping windows of ``horizon`` days after the first ``min_train`` days; each
    uses only the returns before it, without trend. The p-value is a two-sided binomial
    test of the number of hits against ``level``.

    Raises
    ------
    ValueError
        If there is room for fewer than 6 checks.

    """
    values = returns.to_numpy(dtype=float)
    starts = list(range(min_train, len(values) - horizon + 1, horizon))
    if len(starts) < 6:
        raise ValueError("not enough history for a calibration test")
    tail = (1 - level) / 2
    inside = 0
    for k, t in enumerate(starts):
        growth = simulate_growth(values[:t], horizon, paths, demean=True, seed=k)
        final = growth[:, -1]
        final.sort()
        low = final[round(tail * (len(final) - 1))]
        high = final[round((1 - tail) * (len(final) - 1))]
        realized = float((1 + values[t : t + horizon]).prod())
        inside += int(low <= realized <= high)
    n = len(starts)
    below = binomial_cdf(inside, n, level)
    above = 1 - binomial_cdf(inside - 1, n, level) if inside > 0 else 1.0
    return Calibration(horizon, level, n, inside, min(1.0, 2 * min(below, above)))
