"""Three one-day VaR models, each forecasting day ``t`` only from returns before it.

- Historical simulation (HS): the empirical quantile of the last ``window`` returns
  (:func:`quant.validation.rolling_var`). No model, but slow to react: after a calm year it
  forecasts calm until the crisis has been in the window long enough to move the quantile.
- EWMA normal (RiskMetrics, 1996): volatility ``s_t^2 = lam s_{t-1}^2 + (1 - lam) r_{t-1}^2``
  with ``lam = 0.94``, and VaR ``= -z_{1-level} s_t``. Reacts within days, but assumes normal
  tails.
- Filtered historical simulation (FHS; Hull and White, 1998; Barone-Adesi, Giannopoulos and
  Vosper, 1999): each past return divided by the EWMA volatility of its own day, the empirical
  quantile of those standardised returns, rescaled by today's volatility. Reacts like EWMA and
  keeps the shape of the real tails.

Every model returns the same table as :func:`quant.validation.rolling_var`, so all three go
through the same Kupiec, Christoffersen and Basel tests (:func:`quant.validation.evaluate_var`).
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import numpy.typing as npt
import pandas as pd

from quant.validation import rolling_var

LAMBDA = 0.94  # RiskMetrics decay for daily data
SEED_DAYS = 30  # returns used to start the EWMA variance

Vector = npt.NDArray[np.float64]


def ewma_volatility(returns: pd.Series, lam: float = LAMBDA, seed: int = SEED_DAYS) -> pd.Series:
    """Volatility forecast for each day from the returns before it.

    The variance starts as the mean square of the first ``seed`` returns, which are then not
    forecast (their value is NaN). Mean zero, as is standard for daily returns.
    """
    if not 0 < lam < 1:
        raise ValueError("lam must be between 0 and 1")
    r = returns.to_numpy(dtype=np.float64)
    if len(r) <= seed or seed < 2:
        raise ValueError("need more returns than the seed window")
    out = np.full(len(r), np.nan)
    variance = float((r[:seed] ** 2).mean())
    for t in range(seed, len(r)):
        out[t] = math.sqrt(variance)
        variance = lam * variance + (1 - lam) * r[t] ** 2
    return pd.Series(out, index=returns.index)


def _table(returns: pd.Series, var: pd.Series) -> pd.DataFrame:
    tested = returns[var.notna()]
    v = var[var.notna()]
    return pd.DataFrame({"return": tested, "var": v, "breach": tested < -v})


def historical_var(returns: pd.Series, window: int = 250, level: float = 0.95) -> pd.DataFrame:
    """Historical simulation; see :func:`quant.validation.rolling_var`."""
    return rolling_var(returns, window, level)


def ewma_var(
    returns: pd.Series, window: int = 250, level: float = 0.95, lam: float = LAMBDA
) -> pd.DataFrame:
    """EWMA volatility with normal tails, tested on the same days as a ``window`` HS model."""
    sigma = ewma_volatility(returns, lam)
    z = NormalDist().inv_cdf(1 - level)
    var = (-z * sigma).where(np.arange(len(returns)) >= window)
    return _table(returns, var)


def filtered_historical_var(
    returns: pd.Series, window: int = 250, level: float = 0.95, lam: float = LAMBDA
) -> pd.DataFrame:
    """Forecast with filtered historical simulation: the empirical tail of standardised returns.

    For day ``t``: ``z_s = r_s / s_s`` for the ``window`` days before ``t``, where ``s_s`` is
    the EWMA forecast for day ``s``; the VaR is ``-q_{1-level}(z) * s_t`` with the same "lower"
    empirical quantile as the historical model.
    """
    sigma = ewma_volatility(returns, lam)
    r = returns.to_numpy(dtype=np.float64)
    s = sigma.to_numpy(dtype=np.float64)
    standard = r / s
    out = np.full(len(r), np.nan)
    first = max(window, SEED_DAYS + window)
    k = math.floor(round((window - 1) * (1 - level), 9))
    for t in range(first, len(r)):
        past = standard[t - window : t].copy()
        past.sort()
        out[t] = -past[k] * s[t]
    return _table(returns, pd.Series(out, index=returns.index))
