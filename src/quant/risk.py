"""Risk measures for return and value series."""

import math

import pandas as pd

TRADING_DAYS = 252


def annualized_volatility(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    """Annualised volatility: sample standard deviation of returns times sqrt(periods per year).

    Parameters
    ----------
    returns : pd.Series
        Periodic simple returns as decimals, no missing values, at least two.
    periods_per_year : int, default 252
        Number of return periods in a year (252 trading days, 52 weeks, 12 months).

    Returns
    -------
    float
        Volatility as a decimal (0.18 means 18% a year).

    Raises
    ------
    ValueError
        If there are fewer than two returns or any is NaN.

    Assumptions
    -----------
    - Returns are independent from one period to the next, so variance grows linearly with
      time and volatility with its square root. Real returns cluster (calm and wild
      periods), so this is an average, not a forecast.
    - Sample standard deviation (divides by n - 1).

    """
    if len(returns) < 2 or returns.isna().any():
        raise ValueError("need at least two returns and no missing values")
    return float(returns.std(ddof=1)) * math.sqrt(periods_per_year)


def drawdown(value: pd.Series) -> pd.Series:
    """Fall from the highest value seen so far, at every date.

    ``drawdown_t = V_t / max(V_0..V_t) - 1``; 0 at a new high, -0.25 when 25% below the peak.

    Parameters
    ----------
    value : pd.Series
        Positive values (portfolio or price), in date order, no missing values.

    Returns
    -------
    pd.Series
        Drawdown as decimals (zero or negative), same index.

    Raises
    ------
    ValueError
        If a value is missing, zero or negative.

    Assumptions
    -----------
    - The peak is the running maximum up to each date, so only past values are used.

    """
    if value.isna().any() or (value <= 0).any():
        raise ValueError("values must be positive and not missing")
    return value / value.cummax() - 1


def max_drawdown(value: pd.Series) -> float:
    """Largest peak-to-trough fall of a value series, as a negative decimal (0 if none).

    See :func:`drawdown` for the definition and requirements.
    """
    return float(drawdown(value).min())


def historical_var_es(returns: pd.Series, level: float = 0.95) -> tuple[float, float]:
    """Historical Value at Risk and Expected Shortfall, both as positive loss fractions.

    VaR: the loss that was not exceeded on ``level`` of the days. With 95%, the loss of the
    worst day out of every 20. ES: the average loss on the days at or beyond VaR, i.e. how
    bad the bad days were.

    Parameters
    ----------
    returns : pd.Series
        Periodic simple returns as decimals, no missing values.
    level : float, default 0.95
        Confidence level, between 0 and 1.

    Returns
    -------
    tuple[float, float]
        ``(var, es)``; 0.03 means a 3% loss. Negative if even the tail days were gains.

    Raises
    ------
    ValueError
        If ``level`` is outside (0, 1), a return is missing, or there are too few returns
        for the tail to contain at least one observation (``1 / (1 - level)``).

    Assumptions
    -----------
    - The past sample is a fair picture of the next period: no model, but also nothing worse
      than what the sample contains. A calm sample understates risk.
    - Empirical quantile with the "lower" rule: VaR is an observed return, not interpolated.

    """
    if not 0 < level < 1:
        raise ValueError("level must be between 0 and 1")
    minimum = math.ceil(round(1 / (1 - level), 9))
    if len(returns) < minimum:
        raise ValueError(f"need at least {minimum} returns for level {level}")
    if returns.isna().any():
        raise ValueError("returns must not contain missing values")
    cutoff = float(returns.quantile(1 - level, interpolation="lower"))
    tail = returns[returns <= cutoff]
    return -cutoff, -float(tail.mean())


def risk_contributions(returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Share of portfolio variance that comes from each asset (sums to 1).

    ``contribution_i = w_i * (S w)_i / (w' S w)``, with ``S`` the covariance matrix of the
    asset returns. An asset can contribute more risk than its weight (volatile, or moving
    with the rest) or less, even negative (it tends to move against the rest).

    Parameters
    ----------
    returns : pd.DataFrame
        Periodic returns, one column per asset, no missing values.
    weights : pd.Series
        Portfolio weight of each asset, same names as the columns.

    Returns
    -------
    pd.Series
        Contribution of each asset as a fraction of total variance, indexed like ``weights``.

    Raises
    ------
    ValueError
        If weights and columns do not match, a return is missing, or portfolio variance is 0.

    Assumptions
    -----------
    - Risk means variance (or volatility) of the portfolio; covariances are estimated from
      the sample and are noisy for short samples.
    - Weights are held constant over the sample.

    """
    if set(weights.index) != set(returns.columns):
        raise ValueError("weights must cover exactly the return columns")
    if returns.isna().to_numpy().any():
        raise ValueError("returns must not contain missing values")
    w = weights.astype(float)
    cov = returns[w.index].cov()
    marginal = cov.to_numpy() @ w.to_numpy()
    variance = float(w.to_numpy() @ marginal)
    if variance <= 0:
        raise ValueError("portfolio variance is zero")
    return pd.Series(w.to_numpy() * marginal / variance, index=w.index)


def effective_number_of_positions(weights: pd.Series) -> float:
    """Inverse Herfindahl index of the weights: ``1 / sum(w_i^2)`` after normalising.

    Equal weights in n assets give n; one asset with everything gives 1. It reads as "this
    portfolio is as diversified as N equal positions" (by weight, not by risk).

    Parameters
    ----------
    weights : pd.Series
        Non-negative weights or position values; normalised to sum to 1.

    Returns
    -------
    float
        Between 1 and the number of positions.

    Raises
    ------
    ValueError
        If a weight is negative or missing, or all are zero.

    """
    if weights.isna().any() or (weights < 0).any() or not (weights > 0).any():
        raise ValueError("weights must be non-negative, not missing, and not all zero")
    w = weights / weights.sum()
    return float(1 / (w**2).sum())
