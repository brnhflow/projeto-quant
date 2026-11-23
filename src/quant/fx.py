"""Currency conversion of price series."""

import pandas as pd


def to_base_currency(
    prices: pd.DataFrame,
    currencies: pd.Series,
    fx_to_base: pd.DataFrame,
    base: str = "EUR",
) -> pd.DataFrame:
    """Convert each asset's prices into the base currency with the rate of the same date.

    ``price_base_t = price_t * rate_t``, where ``rate_t`` is how many units of the base
    currency one unit of the asset's currency is worth on date t.

    Parameters
    ----------
    prices : pd.DataFrame
        One row per date, one column per asset, each in its own quote currency.
    currencies : pd.Series
        Quote currency code of each asset (e.g. ``"BRL"``), indexed by asset name.
    fx_to_base : pd.DataFrame
        One row per date, one column per currency code; values are base units per one unit
        of that currency (with base EUR, ``BRL = 0.16`` means 1 real is worth 0.16 euro).
        The base currency itself needs no column.
    base : str, default "EUR"
        Code of the base currency.

    Returns
    -------
    pd.DataFrame
        Prices in the base currency, same shape and labels as ``prices``.

    Raises
    ------
    ValueError
        If an asset has no currency, a currency other than the base has no rate column, or a
        rate is zero or negative.

    Assumptions
    -----------
    - Price and rate are taken on the same calendar date. Markets close at different
      times (B3 in the evening in Europe, crypto never), so this mixes slightly different
      moments; with daily data the error is small and does not use future information.
    - A date with no rate is not filled in: the converted price is NaN for the assets in
      that currency. Weekend crypto prices, for example, have no official rate.

    """
    missing = prices.columns.difference(currencies.index)
    if len(missing) > 0:
        raise ValueError(f"no currency for assets: {list(missing)}")
    asset_currencies = currencies[prices.columns]
    needed = set(asset_currencies) - {base}
    no_rates = sorted(needed - set(fx_to_base.columns))
    if no_rates:
        raise ValueError(f"no FX rates for currencies: {no_rates}")
    if (fx_to_base <= 0).to_numpy().any():
        raise ValueError("FX rates must be positive")

    # reindex on the exact price dates: a rate is used only on its own date, never moved
    # forward or backward in time.
    rates = fx_to_base.reindex(prices.index)
    rates[base] = 1.0
    per_asset = rates[asset_currencies.tolist()]
    per_asset.columns = prices.columns
    return prices * per_asset
