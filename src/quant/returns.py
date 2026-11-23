"""Returns computed from price series."""

import pandas as pd


def _check_prices(prices: pd.DataFrame) -> None:
    if not prices.index.is_monotonic_increasing or not prices.index.is_unique:
        raise ValueError("prices index must be strictly increasing (sorted, no duplicate dates)")
    if (prices <= 0).to_numpy().any():
        raise ValueError("prices must be positive")


def simple_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Compute period-over-period simple returns from a table of prices.

    For each asset, ``r_t = P_t / P_{t-1} - 1``.

    Parameters
    ----------
    prices : pd.DataFrame
        One row per date (strictly increasing index), one column per asset. Prices must be
        positive; missing prices are allowed as NaN.

    Returns
    -------
    pd.DataFrame
        Returns as decimals (0.10 means +10%), same columns, dates from the second row on.
        The return at date t belongs to the period that ends at t.

    Raises
    ------
    ValueError
        If the dates are not strictly increasing or a price is zero or negative.

    Assumptions
    -----------
    - Prices are already adjusted for splits and dividends; otherwise a split shows up as a
      fake crash.
    - A missing price is not filled in: the return of that date and of the next one are NaN.
      Deciding how to treat gaps is left to the caller, where it is visible.
    - Rows are trading dates; the function does not know about calendars or time between
      rows, so a return over a long weekend counts as one period like any other.

    """
    _check_prices(prices)
    # shift(1) moves each price one row down, so row t sees P_{t-1}: only past data is used.
    returns = prices / prices.shift(1) - 1
    return returns.iloc[1:]


def portfolio_value(prices: pd.DataFrame, quantities: pd.Series) -> pd.Series:
    """Compute the value of fixed quantities of each asset on every date.

    ``V_t = sum_i q_i * P_{i,t}``.

    Parameters
    ----------
    prices : pd.DataFrame
        One row per date (strictly increasing index), one column per asset, positive prices,
        all in the same currency. Columns not held are ignored.
    quantities : pd.Series
        Units held of each asset, indexed by the same names as the price columns.

    Returns
    -------
    pd.Series
        Portfolio value in the currency of ``prices``, named ``"value"``.

    Raises
    ------
    ValueError
        If a held asset has no price column, a quantity is negative or NaN, all quantities
        are zero, or the prices fail the checks of :func:`simple_returns`.

    Assumptions
    -----------
    - If any held asset has no price on a date, the value of that date is unknown (NaN)
      rather than silently smaller.

    """
    missing = quantities.index.difference(prices.columns)
    if len(missing) > 0:
        raise ValueError(f"no prices for held assets: {list(missing)}")
    if quantities.isna().any() or (quantities < 0).any() or not (quantities > 0).any():
        raise ValueError("quantities must be non-negative with at least one position")
    held = prices[quantities.index]
    _check_prices(held)
    # skipna=False: a missing price makes the total unknown instead of silently smaller.
    value = held.mul(quantities, axis="columns").sum(axis="columns", skipna=False)
    return value.rename("value")


def portfolio_returns(prices: pd.DataFrame, quantities: pd.Series) -> pd.Series:
    """Compute the simple returns of a portfolio that holds fixed quantities of each asset.

    The return is ``V_t / V_{t-1} - 1`` with ``V`` from :func:`portfolio_value`. Because
    quantities stay fixed, the weights drift with prices, as they do in a real account where
    nobody rebalances every day.

    Parameters
    ----------
    prices : pd.DataFrame
        As in :func:`portfolio_value`.
    quantities : pd.Series
        As in :func:`portfolio_value`.

    Returns
    -------
    pd.Series
        Portfolio returns as decimals, named ``"portfolio"``, dates from the second row on.

    Raises
    ------
    ValueError
        Same conditions as :func:`portfolio_value`.

    Assumptions
    -----------
    - Long-only, buy-and-hold: no trades, deposits or withdrawals inside the period.
      Cash flows would show up as fake returns.
    - Prices are adjusted for splits and dividends and are in one currency.
    - A date with an unknown value makes the returns that use it NaN.

    """
    value = portfolio_value(prices, quantities)
    returns = value / value.shift(1) - 1
    return returns.iloc[1:].rename("portfolio")
