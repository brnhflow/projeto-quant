"""Where a portfolio's return came from: each asset, split into price and currency."""

import numpy as np
import pandas as pd


def return_attribution(
    local_prices: pd.DataFrame,
    base_prices: pd.DataFrame,
    quantities: pd.Series,
) -> pd.DataFrame:
    """Split the portfolio return between assets, and each asset's part into price and FX.

    Over the period from the first to the last row, with ``V0`` the starting portfolio value
    in the base currency and ``x`` the FX rate (base units per local unit, ``base / local``):

    - ``total_i = q_i * (P_base_end - P_base_start) / V0``
    - ``price_i = q_i * x_start * (P_local_end - P_local_start) / V0``
      (the price move, valued at the starting exchange rate)
    - ``fx_i = q_i * P_local_end * (x_end - x_start) / V0``
      (what the exchange rate added or removed on the final holding)

    ``price_i + fx_i = total_i`` exactly, and the totals add up to the portfolio return.

    Parameters
    ----------
    local_prices : pd.DataFrame
        Prices in each asset's own currency, one column per asset.
    base_prices : pd.DataFrame
        The same prices converted to the base currency (same dates and columns).
    quantities : pd.Series
        Units held of each asset.

    Returns
    -------
    pd.DataFrame
        Indexed by asset, columns ``price``, ``fx``, ``total``: contributions to the
        portfolio return as decimals (0.03 means 3 percentage points of the total).

    Raises
    ------
    ValueError
        If the two price tables have different dates, or a held asset has no price on the
        first or last date.

    Assumptions
    -----------
    - Buy-and-hold over the whole period (no trades or cash flows), as in
      :func:`quant.returns.portfolio_returns`.
    - The split assigns the cross term (price move times FX move) to FX. Another common
      convention gives it to price; the total is the same either way.

    """
    if not local_prices.index.equals(base_prices.index):
        raise ValueError("local and base prices must have the same dates")
    if len(local_prices) < 2:
        raise ValueError("need at least two dates")
    if not np.isfinite(quantities).all() or (quantities < 0).any() or not (quantities > 0).any():
        raise ValueError("quantities must be finite, non-negative, with at least one position")
    assets = quantities.index
    for table in (local_prices, base_prices):
        absent = assets.difference(table.columns)
        if len(absent) > 0:
            raise ValueError(f"no prices for held assets: {list(absent)}")
    for table in (local_prices, base_prices):
        if table[assets].iloc[[0, -1]].isna().to_numpy().any():
            raise ValueError("every held asset needs a price on the first and last dates")

    q = quantities.astype(float)
    local_start, local_end = local_prices[assets].iloc[0], local_prices[assets].iloc[-1]
    base_start, base_end = base_prices[assets].iloc[0], base_prices[assets].iloc[-1]
    v0 = float((q * base_start).sum())
    rate_start, rate_end = base_start / local_start, base_end / local_end

    total = q * (base_end - base_start) / v0
    price = q * rate_start * (local_end - local_start) / v0
    fx = q * local_end * (rate_end - rate_start) / v0
    result = pd.DataFrame({"price": price, "fx": fx, "total": total})
    result.index.name = "asset"
    return result
