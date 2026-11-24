"""Check whether the risk numbers deserve trust: VaR backtests and bootstrap intervals.

A risk model is only useful if what it predicts happens about as often as it says. This
module replays the historical VaR day by day, using only data available before each day,
and counts how often the loss was worse than predicted (a "breach"). Three standard
tests judge the count and the timing of breaches:

- Kupiec (1995), proportion of failures: are there too many or too few breaches?
- Christoffersen (1998), independence: do breaches come in clusters (crises)?
- Basel Committee (1996) traffic light: the zone regulators use for banks' models.

Bootstrap intervals answer a different question: how much would a number change if
history had been a little different? They resample blocks of consecutive days, so calm
and turbulent stretches stay together (Politis and Romano, 1994).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

TRADING_DAYS = 252
FloatArray = npt.NDArray[np.float64]
IndexArray = npt.NDArray[np.int64]


def chi2_sf(x: float, dof: int) -> float:
    """Probability that a chi-squared variable with 1 or 2 degrees of freedom exceeds ``x``.

    Closed forms: ``erfc(sqrt(x / 2))`` for 1 degree, ``exp(-x / 2)`` for 2. These are the
    only cases the backtests need, so no statistics library is required.

    Raises
    ------
    ValueError
        If ``dof`` is not 1 or 2, or ``x`` is negative.

    """
    if x < 0 or math.isnan(x):
        raise ValueError("x must be a non-negative number")
    if dof == 1:
        return math.erfc(math.sqrt(x / 2))
    if dof == 2:
        return math.exp(-x / 2)
    raise ValueError("only 1 or 2 degrees of freedom are supported")


def _xlogy(x: float, y: float) -> float:
    """``x * log(y)`` with the convention ``0 * log(0) = 0``."""
    return 0.0 if x == 0 else x * math.log(y)


def binomial_cdf(k: int, n: int, p: float) -> float:
    """Probability of at most ``k`` successes in ``n`` trials with probability ``p``.

    Summed in log space, so it stays exact for thousands of trials.
    """
    if not 0 < p < 1 or n < 0:
        raise ValueError("need 0 < p < 1 and n >= 0")
    total = 0.0
    for i in range(min(k, n) + 1):
        log_term = (
            math.lgamma(n + 1)
            - math.lgamma(i + 1)
            - math.lgamma(n - i + 1)
            + i * math.log(p)
            + (n - i) * math.log1p(-p)
        )
        total += math.exp(log_term)
    return min(total, 1.0)


@dataclass(frozen=True)
class TestResult:
    """Likelihood-ratio statistic and its p-value (small p-value: reject the model)."""

    statistic: float
    p_value: float


def kupiec_pof(n: int, breaches: int, p: float) -> TestResult:
    """Kupiec proportion-of-failures test.

    Compares the observed breach rate ``breaches / n`` with the rate ``p`` the model
    promises: ``LR = -2 ln[(1-p)^(n-x) p^x] + 2 ln[(1-x/n)^(n-x) (x/n)^x]``, chi-squared
    with 1 degree of freedom under a correct model.

    Parameters
    ----------
    n : int
        Days tested.
    breaches : int
        Days where the loss exceeded the VaR.
    p : float
        Expected breach probability, ``1 - level`` (0.05 for a 95% VaR).

    """
    if n <= 0 or not 0 <= breaches <= n or not 0 < p < 1:
        raise ValueError("need n > 0, 0 <= breaches <= n and 0 < p < 1")
    x = breaches
    rate = x / n
    null = _xlogy(n - x, 1 - p) + _xlogy(x, p)
    observed = _xlogy(n - x, 1 - rate) + _xlogy(x, rate)
    statistic = max(0.0, -2 * (null - observed))
    return TestResult(statistic, chi2_sf(statistic, 1))


def christoffersen_independence(breaches: pd.Series | npt.NDArray[np.bool_]) -> TestResult:
    """Christoffersen test that a breach today does not make one tomorrow more likely.

    Counts transitions between consecutive days (no breach to breach, breach to breach)
    and compares a model where the breach probability depends on yesterday with one
    where it does not. Chi-squared with 1 degree of freedom.

    Parameters
    ----------
    breaches : sequence of bool
        One value per tested day, in date order.

    """
    b = np.asarray(breaches, dtype=bool)
    if len(b) < 2:
        raise ValueError("need at least two days")
    prev, curr = b[:-1], b[1:]
    n00 = int((~prev & ~curr).sum())
    n01 = int((~prev & curr).sum())
    n10 = int((prev & ~curr).sum())
    n11 = int((prev & curr).sum())
    pi0 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi1 = n11 / (n10 + n11) if n10 + n11 else 0.0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)
    null = _xlogy(n00 + n10, 1 - pi) + _xlogy(n01 + n11, pi)
    alternative = _xlogy(n00, 1 - pi0) + _xlogy(n01, pi0) + _xlogy(n10, 1 - pi1) + _xlogy(n11, pi1)
    statistic = max(0.0, -2 * (null - alternative))
    return TestResult(statistic, chi2_sf(statistic, 1))


def traffic_light(n: int, breaches: int, p: float) -> str:
    """Basel traffic-light zone: ``"green"``, ``"yellow"`` or ``"red"``.

    Green while the chance of seeing this many breaches or fewer from a correct model is
    below 95%; red from 99.99%. For 250 days of a 99% VaR this gives the regulatory
    table: green 0-4, yellow 5-9, red 10 or more breaches.
    """
    probability = binomial_cdf(breaches, n, p)
    if probability < 0.95:
        return "green"
    if probability < 0.9999:
        return "yellow"
    return "red"


def rolling_var(returns: pd.Series, window: int, level: float = 0.95) -> pd.DataFrame:
    """Historical VaR forecast for each day from the ``window`` days before it.

    The forecast for day ``t`` uses returns ``t - window`` to ``t - 1`` only, never day
    ``t`` itself, so the test sees exactly what the model would have said that morning.

    Returns
    -------
    pd.DataFrame
        Indexed by the tested days, with ``return``, ``var`` (a positive loss) and
        ``breach`` (``return < -var``).

    Raises
    ------
    ValueError
        If there are not more returns than ``window``.

    """
    if window < 2 or len(returns) <= window:
        raise ValueError("need more returns than the window")
    values = returns.to_numpy(dtype=float)
    # Row t holds the ``window`` returns before day ``window + t``; the forecast is the same
    # "lower" empirical quantile as :func:`quant.risk.historical_var_es`, for all rows at once.
    windows: FloatArray = np.lib.stride_tricks.sliding_window_view(values, window)[:-1]  # pyright: ignore[reportUnknownMemberType]
    k = math.floor(round((window - 1) * (1 - level), 9))
    ordered = windows.copy()
    ordered.partition(k, axis=1)
    forecasts = -ordered[:, k]
    tested = returns.iloc[window:]
    var = pd.Series(forecasts, index=tested.index)
    return pd.DataFrame({"return": tested, "var": var, "breach": tested < -var})


@dataclass(frozen=True)
class VarBacktest:
    """Outcome of replaying the VaR model over history."""

    level: float
    window: int
    days: int
    breaches: int
    expected: float
    kupiec: TestResult
    independence: TestResult
    conditional_p_value: float
    zone: str
    table: pd.DataFrame


def backtest_var(returns: pd.Series, level: float = 0.95, window: int = 250) -> VarBacktest:
    """Replay the historical VaR and run the Kupiec, Christoffersen and Basel checks.

    The conditional-coverage p-value combines both statistics (chi-squared, 2 degrees).
    """
    return evaluate_var(rolling_var(returns, window, level), level, window)


def evaluate_var(table: pd.DataFrame, level: float, window: int) -> VarBacktest:
    """Run the Kupiec, Christoffersen and Basel checks on any model's forecasts.

    Parameters
    ----------
    table : pd.DataFrame
        One row per tested day with a boolean ``breach`` column, in date order (as
        :func:`rolling_var` and the models in :mod:`quant.var_models` return).
    level : float
        The VaR's confidence level.
    window : int
        Days of history behind each forecast, for the record.

    """
    p = 1 - level
    n = len(table)
    x = int(table["breach"].sum())
    kupiec = kupiec_pof(n, x, p)
    independence = christoffersen_independence(table["breach"])
    combined = chi2_sf(kupiec.statistic + independence.statistic, 2)
    return VarBacktest(
        level=level,
        window=window,
        days=n,
        breaches=x,
        expected=n * p,
        kupiec=kupiec,
        independence=independence,
        conditional_p_value=combined,
        zone=traffic_light(n, x, p),
        table=table,
    )


def stationary_bootstrap_matrix(
    n: int, mean_block: float, rng: np.random.Generator, rows: int
) -> IndexArray:
    """Positions for ``rows`` stationary-bootstrap resamples of a series of length ``n``.

    Each step either continues the current block (probability ``1 - 1/mean_block``) or
    jumps to a random day; blocks wrap around the end. Block lengths are geometric, so
    the resampled series is stationary (Politis and Romano, 1994). All rows are drawn in
    one vectorised pass.
    """
    if n < 1 or mean_block < 1 or rows < 1:
        raise ValueError("need n >= 1, mean_block >= 1 and rows >= 1")
    starts = rng.random((rows, n)) < 1 / mean_block
    starts[:, 0] = True
    jumps = rng.integers(0, n, size=(rows, n))
    steps = np.arange(n)
    # For each step, where its block began; the position walks on from that block's jump.
    marked = steps * starts  # a step's own index where a block starts, else 0
    block_start = np.asarray(np.maximum.accumulate(marked, axis=1), dtype=np.int64)  # pyright: ignore[reportUnknownMemberType]
    first = np.take_along_axis(jumps, block_start, axis=1)
    return np.asarray((first + steps - block_start) % n, dtype=np.int64)


def stationary_bootstrap_indices(n: int, mean_block: float, rng: np.random.Generator) -> IndexArray:
    """Positions for one stationary-bootstrap resample; see :func:`stationary_bootstrap_matrix`."""
    return stationary_bootstrap_matrix(n, mean_block, rng, 1)[0]


@dataclass(frozen=True)
class Interval:
    """Point estimate and a bootstrap confidence interval."""

    estimate: float
    low: float
    high: float
    level: float


Statistic = Callable[[FloatArray], FloatArray]


def bootstrap_interval(
    returns: pd.Series,
    statistic: Statistic,
    *,
    level: float = 0.90,
    resamples: int = 2000,
    mean_block: float | None = None,
    seed: int = 0,
) -> Interval:
    """Percentile confidence interval of ``statistic`` by stationary block bootstrap.

    Parameters
    ----------
    returns : pd.Series
        Daily returns in date order, no missing values.
    statistic : callable
        Takes a 2-D array (one resample per row) and returns one number per row; the
        statistics below all work that way, so every resample is computed at once.
    level : float, default 0.90
        Coverage: 0.90 means 5% of resamples fall below ``low`` and 5% above ``high``.
    resamples : int, default 2000
        More resamples give steadier bounds; 2000 keeps the third digit stable.
    mean_block : float, optional
        Average block length in days; default ``n ** (1/3)`` (at least 5), a common rule.
    seed : int, default 0
        Fixed so the same data always gives the same interval.

    Assumptions
    -----------
    - The past behaviour is representative: resampling cannot create a crisis that the
      sample never had, so intervals from calm samples are too narrow.

    """
    values = returns.to_numpy(dtype=float)
    n = len(values)
    if n < 20 or np.isnan(values).any():
        raise ValueError("need at least 20 returns without missing values")
    block = mean_block if mean_block is not None else max(5.0, n ** (1 / 3))
    rng = np.random.default_rng(seed)
    rows = stationary_bootstrap_matrix(n, block, rng, resamples)
    stats = pd.Series(statistic(values[rows]))
    tail = (1 - level) / 2
    estimate = float(statistic(values[np.newaxis, :])[0])
    return Interval(estimate, float(stats.quantile(tail)), float(stats.quantile(1 - tail)), level)


# Statistics of daily returns, computed along the last axis: a 1-D array gives one number,
# a 2-D array one number per row.


def annualized_vol(values: FloatArray) -> FloatArray:
    """Sample standard deviation times sqrt(252), as :func:`quant.risk.annualized_volatility`."""
    return np.std(values, ddof=1, axis=-1) * math.sqrt(TRADING_DAYS)


def annualized_return(values: FloatArray) -> FloatArray:
    """Compound growth per year: ``prod(1 + r) ** (252 / n) - 1`` (-100% if wiped out)."""
    growth = np.prod(1 + values, axis=-1)
    alive = growth > 0
    compounded = np.maximum(growth, 1e-300) ** (TRADING_DAYS / values.shape[-1]) - 1
    return alive * compounded - (~alive) * 1.0


def sharpe_ratio(values: FloatArray) -> FloatArray:
    """Annualized mean over annualized volatility, with no risk-free rate subtracted."""
    sd = np.std(values, ddof=1, axis=-1)
    mean = np.mean(values, axis=-1)
    moving = sd > 1e-12  # rounding noise of constant returns
    return moving * mean / (sd + ~moving) * math.sqrt(TRADING_DAYS)


def var_95(values: FloatArray) -> FloatArray:
    """Historical 95% one-day VaR, the "lower" quantile of :func:`quant.risk.historical_var_es`."""
    k = math.floor(round((values.shape[-1] - 1) * 0.05, 9))
    ordered = values.copy()
    ordered.sort(axis=-1)
    return -ordered[..., k]
