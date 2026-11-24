"""Compare the portfolio with a benchmark: did it beat the market, and at what risk.

All statistics use daily simple returns in the same currency over the same dates.

- Beta: ``cov(p, b) / var(b)``, how much the portfolio moves per 1% of the benchmark.
- Alpha (Jensen, no risk-free rate): ``mean(p - beta * b) * 252``, the yearly return
  not explained by the benchmark exposure.
- Tracking error: ``std(p - b) * sqrt(252)``, how far the portfolio wanders from it.
- Information ratio: ``mean(p - b) * 252 / tracking error``, excess return per unit of
  tracking error. Above 0.5 is good for a professional manager.
- Up and down capture: the portfolio's average return on the benchmark's up days (down
  days) over the benchmark's average on those days. Below 1 on down days means it fell
  less than the market when the market fell.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass(frozen=True)
class BenchmarkStats:
    """How the portfolio behaved against one benchmark over one window."""

    portfolio_return: float
    benchmark_return: float
    beta: float
    alpha: float
    correlation: float
    tracking_error: float
    information_ratio: float | None
    up_capture: float | None
    down_capture: float | None
    days: int


def compare(portfolio: pd.Series, benchmark: pd.Series) -> BenchmarkStats:
    """Statistics of ``portfolio`` against ``benchmark`` on the dates both have values.

    Parameters
    ----------
    portfolio, benchmark : pd.Series
        Values (prices or portfolio value) in the same currency, indexed by date.

    Raises
    ------
    ValueError
        With fewer than 20 common daily returns, or a benchmark that never moves.

    """
    joined = pd.concat([portfolio, benchmark], axis=1, keys=["p", "b"], sort=True).dropna()
    returns = joined.pct_change().dropna()
    if len(returns) < 20:
        raise ValueError("need at least 20 common returns")
    p = returns["p"].to_numpy(dtype=float)
    b = returns["b"].to_numpy(dtype=float)
    var_b = float(b.var(ddof=1))
    if var_b <= 0:
        raise ValueError("the benchmark never moves")
    cov = float(((p - p.mean()) * (b - b.mean())).sum() / (len(p) - 1))
    beta = cov / var_b
    excess = p - b
    tracking = float(excess.std(ddof=1)) * math.sqrt(TRADING_DAYS)
    sd_p = float(p.std(ddof=1))
    up, down = b > 0, b < 0

    def capture(mask: np.ndarray) -> float | None:
        if mask.sum() < 5 or b[mask].mean() == 0:
            return None
        return float(p[mask].mean() / b[mask].mean())

    first, last = joined.iloc[0], joined.iloc[-1]
    return BenchmarkStats(
        portfolio_return=float(last["p"] / first["p"] - 1),
        benchmark_return=float(last["b"] / first["b"] - 1),
        beta=beta,
        alpha=float((p - beta * b).mean()) * TRADING_DAYS,
        correlation=cov / (sd_p * math.sqrt(var_b)) if sd_p > 0 else 0.0,
        tracking_error=tracking,
        information_ratio=float(excess.mean()) * TRADING_DAYS / tracking
        if tracking > 1e-12
        else None,
        up_capture=capture(up),
        down_capture=capture(down),
        days=len(returns),
    )
