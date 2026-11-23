"""Put series from markets with different trading calendars on one set of dates."""

import pandas as pd


def align_to_dates(
    prices: pd.DataFrame,
    dates: pd.DatetimeIndex,
    max_staleness: pd.Timedelta = pd.Timedelta(days=5),  # noqa: B008 (immutable value)
) -> pd.DataFrame:
    """Sample each column on the target dates using its last known value at or before each date.

    This is how a portfolio is valued on a day when one of its markets is closed: the asset is
    worth its most recent close. Values are only carried forward in time, never backward.

    Parameters
    ----------
    prices : pd.DataFrame
        One column per series (asset prices or FX rates), indexed by the dates on which each
        was observed. NaN means "no observation that day" (e.g. market holiday).
    dates : pd.DatetimeIndex
        Target calendar, strictly increasing (e.g. European business days).
    max_staleness : pd.Timedelta, default 5 days
        Oldest observation that may be carried to a date. Older than that, the value is NaN.

    Returns
    -------
    pd.DataFrame
        Same columns, indexed by ``dates``.

    Raises
    ------
    ValueError
        If ``dates`` or the index of ``prices`` is not strictly increasing.

    Assumptions
    -----------
    - On a date when a market is closed, its last close is the fair value of the asset.
      True for valuation; it understates risk a little, because the price "doesn't move"
      on those days and catches up on the next trading day.
    - Observations on days outside the target calendar (crypto weekends) are skipped; the
      next target date picks up the latest one, so no price change is lost, only regrouped.
    - Five days covers long holidays (Carnival, Easter); a longer gap suggests a suspended or
      delisted asset, which should show up as missing, not as a flat price.

    """
    for label, index in (("dates", dates), ("prices index", prices.index)):
        if not index.is_monotonic_increasing or not index.is_unique:
            raise ValueError(f"{label} must be strictly increasing (sorted, no duplicates)")

    aligned: dict[str, pd.Series] = {}
    for name in prices.columns:
        observed = prices[name].dropna()
        if observed.empty:
            aligned[str(name)] = pd.Series(float("nan"), index=dates)
            continue
        # method="ffill": each date takes the latest observation at or BEFORE it.
        aligned[str(name)] = observed.reindex(dates, method="ffill", tolerance=max_staleness)
    return pd.DataFrame(aligned, index=dates, columns=prices.columns)
