"""Compute everything the portfolio report shows, for each selectable period.

All numbers come from the tested functions in :mod:`quant`; the HTML page only draws them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from quant.align import align_to_dates
from quant.attribution import return_attribution
from quant.data.market import SeriesStatus
from quant.fx import to_base_currency
from quant.returns import portfolio_value, simple_returns
from quant.risk import (
    annualized_volatility,
    drawdown,
    effective_number_of_positions,
    historical_var_es,
    risk_contributions,
)

MIN_DAYS_VAR = 100
MIN_DAYS_COVARIANCE = 20
VAR_LEVEL = 0.95


@dataclass(frozen=True)
class Period:
    """A selectable look-back window ending on the last date."""

    key: str
    label: str
    months: int | None  # None: year to date; 0: whole history


PERIODS = (
    Period("1M", "1 mês", 1),
    Period("3M", "3 meses", 3),
    Period("6M", "6 meses", 6),
    Period("YTD", "No ano", None),
    Period("12M", "12 meses", 12),
    Period("ALL", "Tudo", 0),
)


def period_start(dates: pd.DatetimeIndex, period: Period) -> int | None:
    """Position of the period's base date in ``dates``, or None if history is too short.

    The base is the last date at or before the period's starting point, so a 3-month return
    on 20 Nov is measured from the close of 20 Aug (or the trading day before it). Year to
    date starts from the last close of the previous year.

    Parameters
    ----------
    dates : pd.DatetimeIndex
        Strictly increasing dates of the value series.
    period : Period
        The window to measure.

    Returns
    -------
    int or None
        Index into ``dates``; None when the history does not reach back far enough.

    """
    end = dates[-1]
    if period.months == 0:
        return 0
    if period.months is None:
        target = pd.Timestamp(end.year - 1, 12, 31)
    else:
        target = end - pd.DateOffset(months=period.months)
    position = int(dates.searchsorted(target, side="right")) - 1
    if position < 0 or position >= len(dates) - 1:
        return None
    return position


def _num(x: float, digits: int = 6) -> float | None:
    return None if math.isnan(x) or math.isinf(x) else round(x, digits)


def _iso(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%d")


def _period_data(
    period: Period,
    start: int,
    local: pd.DataFrame,
    base_prices: pd.DataFrame,
    value: pd.Series,
    quantities: pd.Series,
    weights_now: pd.Series,
) -> dict[str, Any]:
    v = value.iloc[start:]
    returns = simple_returns(v.to_frame())["value"]
    dd = drawdown(v)
    dates = pd.DatetimeIndex(v.index)
    trough_pos = int(dd.to_numpy().argmin())
    trough = dates[trough_pos]
    worst = float(dd.min())
    peak = dates[int(v.iloc[: trough_pos + 1].to_numpy().argmax())]

    var_block: dict[str, Any] | None = None
    if len(returns) >= MIN_DAYS_VAR:
        var, es = historical_var_es(returns, level=VAR_LEVEL)
        var_block = {"var": _num(var), "es": _num(es), "level": VAR_LEVEL, "n": len(returns)}

    attribution = return_attribution(local.iloc[start:], base_prices.iloc[start:], quantities)
    asset_returns = simple_returns(base_prices.iloc[start:])
    first_local, last_local = local.iloc[start], local.iloc[-1]
    first_base, last_base = base_prices.iloc[start], base_prices.iloc[-1]

    risk_block: dict[str, Any] | None = None
    if len(asset_returns) >= MIN_DAYS_COVARIANCE:
        contributions = risk_contributions(asset_returns, weights_now)
        corr = asset_returns.corr()
        matrix = corr.to_numpy(dtype=float)
        names = [str(c) for c in corr.columns]
        risk_block = {
            "contributions": {str(k): _num(float(c)) for k, c in contributions.items()},
            "corr": {
                "assets": names,
                "matrix": [
                    [_num(float(matrix[i, j]), 4) for j in range(len(names))]
                    for i in range(len(names))
                ],
            },
        }

    return {
        "key": period.key,
        "label": period.label,
        "available": True,
        "start": start,
        "startDate": _iso(v.index[0]),
        "endDate": _iso(v.index[-1]),
        "days": len(returns),
        "totalReturn": _num(float(v.iloc[-1] / v.iloc[0] - 1)),
        "pnl": _num(float(v.iloc[-1] - v.iloc[0]), 2),
        "volatility": _num(annualized_volatility(returns)) if len(returns) >= 2 else None,
        "maxDrawdown": {
            "value": _num(worst),
            "peak": _iso(peak) if worst < 0 else None,
            "trough": _iso(trough) if worst < 0 else None,
        },
        "drawdown": [_num(float(x)) for x in dd],
        "var": var_block,
        "attribution": [
            {
                "asset": str(asset),
                "price": _num(float(row["price"])),
                "fx": _num(float(row["fx"])),
                "total": _num(float(row["total"])),
            }
            for asset, row in attribution.iterrows()
        ],
        "assetReturns": {
            str(a): {
                "base": _num(float(last_base[a] / first_base[a] - 1)),
                "local": _num(float(last_local[a] / first_local[a] - 1)),
            }
            for a in quantities.index
        },
        "risk": risk_block,
    }


def build_report_data(
    holdings: pd.DataFrame,
    local_prices: pd.DataFrame,
    fx_rates: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    *,
    title: str,
    base: str = "EUR",
    synthetic: bool = False,
    generated: date | None = None,
    status: list[SeriesStatus] | None = None,
) -> dict[str, Any]:
    """Assemble the report content as plain JSON-ready data.

    Parameters
    ----------
    holdings : pd.DataFrame
        As returned by :func:`quant.holdings.load_holdings`.
    local_prices : pd.DataFrame
        Prices in each asset's own currency, on each market's own dates (NaN or absent
        rows on closed days). Must contain every held asset.
    fx_rates : pd.DataFrame
        Base units per one unit of each currency, on the rate source's own dates.
    calendar : pd.DatetimeIndex
        Dates the report is built on (e.g. business days of the base market).
    title : str
        Report title.
    base : str, default "EUR"
        Base currency code.
    synthetic : bool, default False
        Marks the report as built on simulated data.
    generated : date, optional
        Generation date shown in the report; today if omitted.
    status : list of SeriesStatus, optional
        Where each series came from and whether its update failed, shown in the report.

    Returns
    -------
    dict
        Static content (positions, allocation) and one entry per period in :data:`PERIODS`.

    Raises
    ------
    ValueError
        If fewer than two dates have prices for every held asset.

    Assumptions
    -----------
    - Quantities are the current holdings and are treated as held for the whole history
      (no trades), so the past shows how today's portfolio would have behaved.
    - Dates where any held asset has no price, even after carrying the last close forward
      for up to five days, are left out; their count is reported.
    - Risk contributions use today's weights for every period.

    """
    quantities = holdings["quantity"].astype(float)
    currencies = holdings["currency"]
    local = align_to_dates(local_prices[quantities.index], calendar)
    rates = align_to_dates(fx_rates, calendar)
    base_prices = to_base_currency(local, currencies, rates, base=base)
    complete = local.notna().all(axis="columns") & base_prices.notna().all(axis="columns")
    local, base_prices = local[complete], base_prices[complete]
    if len(local) < 2:
        raise ValueError("need at least two dates with a price for every held asset")

    value = portfolio_value(base_prices, quantities)
    position_value = base_prices.iloc[-1] * quantities
    weights_now = position_value / position_value.sum()
    by_currency = position_value.groupby(currencies).sum().sort_values(ascending=False)

    order: list[str] = [str(x) for x in position_value.sort_values(ascending=False).index]
    periods: list[dict[str, Any]] = []
    for period in PERIODS:
        start = period_start(pd.DatetimeIndex(value.index), period)
        if start is None:
            periods.append({"key": period.key, "label": period.label, "available": False})
            continue
        periods.append(
            _period_data(period, start, local, base_prices, value, quantities, weights_now)
        )

    preferred = ("12M", "ALL")
    default = next(p["key"] for k in preferred for p in periods if p["key"] == k and p["available"])

    return {
        "title": title,
        "base": base,
        "synthetic": synthetic,
        "generated": (generated or date.today()).isoformat(),
        "asOf": _iso(value.index[-1]),
        "droppedDates": int((~complete).sum()),
        "dates": [_iso(d) for d in value.index],
        "value": [_num(float(x), 2) for x in value],
        "positions": [
            {
                "asset": str(a),
                "currency": str(currencies[a]),
                "quantity": float(quantities[a]),
                "priceLocal": _num(float(local[a].iloc[-1]), 4),
                "priceBase": _num(float(base_prices[a].iloc[-1]), 4),
                "value": _num(float(position_value[a]), 2),
                "weight": _num(float(weights_now[a])),
            }
            for a in order
        ],
        "currencies": [
            {
                "code": str(c),
                "value": _num(float(v), 2),
                "weight": _num(float(v) / float(value.iloc[-1])),
            }
            for c, v in by_currency.items()
        ],
        "effectivePositions": _num(effective_number_of_positions(position_value), 3),
        "minDaysVar": MIN_DAYS_VAR,
        "minDaysCovariance": MIN_DAYS_COVARIANCE,
        "defaultPeriod": default,
        "periods": periods,
        "sources": [
            {
                "name": s.name,
                "source": s.source,
                "symbol": s.symbol,
                "lastDate": s.last_date,
                "inProgress": s.in_progress,
                "fromCache": s.from_cache,
                "error": s.error,
            }
            for s in (status or [])
        ],
    }
