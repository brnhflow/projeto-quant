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
from quant.data.news import Headline
from quant.data.sources import Quote
from quant.factors import factor_exposure
from quant.fx import to_base_currency
from quant.returns import portfolio_value, simple_returns
from quant.risk import (
    annualized_volatility,
    drawdown,
    effective_number_of_positions,
    historical_var_es,
    risk_contributions,
)
from quant.stress import (
    PROXIES,
    SCENARIOS,
    ProxyFit,
    fit_proxy,
    run_scenario,
    window_return,
)
from quant.validation import (
    annualized_return,
    annualized_vol,
    backtest_var,
    bootstrap_interval,
    sharpe_ratio,
    var_95,
)

MIN_DAYS_VAR = 100
MIN_DAYS_COVARIANCE = 20
VAR_LEVEL = 0.95
BACKTEST_WINDOW = 250  # one year of days to estimate each day's VaR
MIN_TESTED_DAYS = 125  # below half a year of tested days the tests mean little
MIN_DAYS_INTERVALS = 60


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


COVARIANCE_DAYS = 252


def _kind(holdings: pd.DataFrame, asset: Any) -> str:
    """How a position trades: ``cash``, ``crypto`` (fractional) or ``security`` (whole units)."""
    source = str(holdings.loc[asset, "source"]) if "source" in holdings.columns else "yahoo"
    symbol = str(holdings.loc[asset, "symbol"]) if "symbol" in holdings.columns else str(asset)
    if source == "cash":
        return "cash"
    if source == "kraken" or symbol.endswith(("-USD", "-EUR", "-BRL", "-GBP")):
        return "crypto"
    return "security"


def _covariance(base_prices: pd.DataFrame, order: list[str]) -> dict[str, Any] | None:
    """Annualized covariance of daily euro returns over the last year, for what-if weights."""
    returns = simple_returns(base_prices[order]).iloc[-COVARIANCE_DAYS:]
    if len(returns) < MIN_DAYS_COVARIANCE:
        return None
    matrix = (returns.cov() * 252).to_numpy(dtype=float)
    return {
        "assets": order,
        "days": len(returns),
        "matrix": [
            [_num(float(matrix[i, j]), 10) for j in range(len(order))] for i in range(len(order))
        ],
    }


def backtest_window(n: int) -> int | None:
    """Days of history behind each VaR forecast, or None if the sample is too short.

    A year (250 days) when at least a year is left to test; otherwise half the sample,
    as long as both halves have at least :data:`MIN_TESTED_DAYS` days.
    """
    if n >= BACKTEST_WINDOW + MIN_TESTED_DAYS:
        return BACKTEST_WINDOW if n - BACKTEST_WINDOW >= BACKTEST_WINDOW else n // 2
    return None


def _validation(value: pd.Series) -> dict[str, Any]:
    """How far to trust the risk numbers: VaR backtest and bootstrap intervals."""
    returns = simple_returns(value.to_frame())["value"]
    n = len(returns)
    out: dict[str, Any] = {
        "days": n,
        "start": _iso(value.index[0]),
        "end": _iso(value.index[-1]),
        "backtest": None,
        "intervals": None,
    }

    window = backtest_window(n)
    if window is not None:
        bt = backtest_var(returns, level=VAR_LEVEL, window=window)
        table = bt.table
        out["backtest"] = {
            "level": bt.level,
            "window": bt.window,
            "days": bt.days,
            "breaches": bt.breaches,
            "expected": _num(bt.expected, 2),
            "kupiecP": _num(bt.kupiec.p_value, 4),
            "independenceP": _num(bt.independence.p_value, 4),
            "conditionalP": _num(bt.conditional_p_value, 4),
            "zone": bt.zone,
            "dates": [_iso(d) for d in table.index],
            "returns": [_num(float(x)) for x in table["return"]],
            "var": [_num(float(x)) for x in table["var"]],
            "breachDates": [_iso(d) for d in table.index[table["breach"].to_numpy()]],
        }

    if n >= MIN_DAYS_INTERVALS:
        stats = {
            "annualReturn": annualized_return,
            "volatility": annualized_vol,
            "sharpe": sharpe_ratio,
            "var": var_95,
        }
        intervals: dict[str, Any] = {}
        for key, fn in stats.items():
            interval = bootstrap_interval(returns, fn, level=0.90, seed=7)
            intervals[key] = {
                "estimate": _num(interval.estimate),
                "low": _num(interval.low),
                "high": _num(interval.high),
            }
        out["intervals"] = {"level": 0.90, "values": intervals, "start": _iso(value.index[0])}
    return out


def _stress(
    holdings: pd.DataFrame,
    local_prices: pd.DataFrame,
    fx_rates: pd.DataFrame,
    proxy_prices: pd.DataFrame,
    position_value: pd.Series,
    last: pd.Timestamp,
    base: str,
) -> dict[str, Any] | None:
    """Historical crises replayed on today's positions, and the betas for custom shocks."""
    first = min(pd.Timestamp(local_prices.index.min()), pd.Timestamp(proxy_prices.index.min()))
    calendar = pd.bdate_range(first, last)
    currencies = holdings["currency"]
    assets_eur = to_base_currency(
        align_to_dates(local_prices[holdings.index], calendar),
        currencies,
        align_to_dates(fx_rates, calendar),
        base=base,
    )
    available = [p for p in PROXIES if p in proxy_prices.columns]
    if not available:
        return None
    proxy_currencies = pd.Series({p: PROXIES[p][1] for p in available})
    needed = set(proxy_currencies) - {base}
    if not needed <= set(fx_rates.columns):
        return None
    proxies_eur = to_base_currency(
        align_to_dates(proxy_prices[available], calendar),
        proxy_currencies,
        align_to_dates(fx_rates, calendar),
        base=base,
    )

    names = [str(a) for a in holdings.index]
    column = {
        c: [str(v) for v in holdings[c].tolist()] for c in ("source", "symbol") if c in holdings
    }
    source_of = dict(zip(names, column.get("source", [""] * len(names)), strict=True))
    symbol_of = dict(zip(names, column.get("symbol", names), strict=True))
    fits: dict[str, ProxyFit] = {}
    positions: list[dict[str, Any]] = []
    for asset in holdings.index:
        name = str(asset)
        is_cash = source_of[name] == "cash"
        symbol = symbol_of[name]
        fit = fit_proxy(assets_eur[name], proxies_eur, symbol, str(currencies[asset]))
        fits[name] = fit
        positions.append(
            {
                "asset": name,
                "value": _num(float(position_value[asset]), 2),
                "cash": is_cash,
                "currency": str(currencies[asset]),
                "proxy": None if is_cash else fit.proxy,
                "beta": None if is_cash else _num(fit.beta, 4),
                "r2": None if is_cash else _num(fit.r2, 4),
                "fitted": fit.fitted,
            }
        )

    total = float(position_value.sum())
    scenarios: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        shocks = run_scenario(scenario, assets_eur, proxies_eur, position_value, fits)
        known = [s for s in shocks if s.change is not None]
        pnl = sum(s.value * float(s.change or 0) for s in known)
        scenarios.append(
            {
                "key": scenario.key,
                "name": scenario.name,
                "description": scenario.description,
                "start": _iso(scenario.start),
                "end": _iso(scenario.end),
                "pnl": _num(pnl, 2),
                "change": _num(pnl / total),
                "coverage": {
                    method: _num(sum(s.value for s in shocks if s.method == method) / total)
                    for method in ("history", "proxy", "missing")
                },
                "positions": [
                    {
                        "asset": s.asset,
                        "change": None if s.change is None else _num(s.change),
                        "pnl": None if s.change is None else _num(s.value * s.change, 2),
                        "method": s.method,
                    }
                    for s in shocks
                ],
                "currencies": {
                    c: _num(r)
                    for c in sorted(set(currencies.astype(str)) - {base})
                    if c in fx_rates.columns
                    and (r := window_return(fx_rates[c], scenario.start, scenario.end)) is not None
                },
                "indices": {
                    p: _num(r)
                    for p in available
                    if (r := window_return(proxies_eur[p], scenario.start, scenario.end))
                    is not None
                },
            }
        )
    return {
        "total": _num(total, 2),
        "scenarios": scenarios,
        "positions": positions,
        "proxies": [{"symbol": p, "name": PROXIES[p][0]} for p in available],
        "indicesUntil": _iso(pd.Timestamp(proxy_prices.dropna(how="all").index.max())),
    }


CURRENCY_NAMES = {
    "USD": "Dólar",
    "BRL": "Real",
    "GBP": "Libra",
    "CHF": "Franco suíço",
    "JPY": "Iene",
    "CAD": "Dólar canadense",
    "AUD": "Dólar australiano",
    "SEK": "Coroa sueca",
    "NOK": "Coroa norueguesa",
    "DKK": "Coroa dinamarquesa",
    "HKD": "Dólar de Hong Kong",
    "CNY": "Yuan",
    "PLN": "Zloty",
    "MXN": "Peso mexicano",
}


def _factors(
    value: pd.Series,
    proxy_prices: pd.DataFrame,
    fx_rates: pd.DataFrame,
    stress: dict[str, Any] | None,
    currencies: list[str],
    base: str,
) -> dict[str, Any] | None:
    """Exposure of the portfolio to the markets its assets follow and to its currencies."""
    if stress is None:
        return None
    markets = sorted({str(p["proxy"]) for p in stress["positions"] if p["proxy"]})
    markets = [m for m in markets if m in proxy_prices.columns]
    foreign = sorted({c for c in currencies if c != base and c in fx_rates.columns})
    start, end = pd.Timestamp(value.index[0]), pd.Timestamp(value.index[-1])
    window = slice(start - pd.Timedelta(days=10), end)
    prices = pd.concat(
        [proxy_prices.loc[window, markets], fx_rates.loc[window, foreign]],
        axis="columns",
        sort=True,
    )
    if prices.empty or prices.shape[1] == 0:
        return None
    try:
        exposure = factor_exposure(value, prices)
    except ValueError:
        return None
    fit = exposure.fit
    t_stats = fit.t_stats
    items: list[dict[str, Any]] = []
    for key in fit.betas.index:
        k = str(key)
        is_currency = k in foreign
        items.append(
            {
                "key": k,
                "name": f"{CURRENCY_NAMES.get(k, k)} ({k})" if is_currency else PROXIES[k][0],
                "kind": "currency" if is_currency else "market",
                "beta": _num(float(fit.betas[key]), 4),
                "se": _num(float(fit.standard_errors[key]), 4),
                "t": _num(float(t_stats[key]), 2),
                "share": _num(float(exposure.shares[key]), 4),
            }
        )
    return {
        "weeks": exposure.weeks,
        "start": _iso(start),
        "r2": _num(fit.r2, 4),
        "oosR2": None if exposure.oos_r2 is None else _num(exposure.oos_r2, 4),
        "alphaAnnual": _num(exposure.alpha_annual, 4),
        "alphaT": _num(fit.alpha / fit.alpha_se, 2) if fit.alpha_se > 0 else None,
        "residualShare": _num(float(exposure.shares["residual"]), 4),
        "items": items,
    }


UNUSUAL_Z = 2.5  # a move this many standard deviations from zero happens ~1% of days
MOVE_HISTORY = 250


def unusual_moves(local: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Last day's and last week's move of each asset against its own usual size.

    The usual size is the standard deviation of daily returns over the year before the
    move (the move itself excluded); a week scales it by sqrt(5). ``unusual`` is True when
    either move is beyond :data:`UNUSUAL_Z` standard deviations.
    """
    out: dict[str, dict[str, Any]] = {}
    for asset in local.columns:
        prices = local[asset].dropna()
        if len(prices) < 60:
            continue
        returns = prices.pct_change().dropna()
        history = returns.iloc[-MOVE_HISTORY - 5 : -5]
        sd = float(history.std())
        if not sd > 0:
            continue
        day = float(prices.iloc[-1] / prices.iloc[-2] - 1)
        week = float(prices.iloc[-1] / prices.iloc[-6] - 1)
        z_day, z_week = day / sd, week / (sd * math.sqrt(5))
        out[str(asset)] = {
            "date": _iso(pd.Timestamp(prices.index[-1])),
            "day": _num(day),
            "week": _num(week),
            "zDay": _num(z_day, 2),
            "zWeek": _num(z_week, 2),
            "unusual": abs(z_day) >= UNUSUAL_Z or abs(z_week) >= UNUSUAL_Z,
        }
    return out


def dividend_income(
    details: dict[str, Quote],
    quantities: pd.Series,
    rates: pd.Series,
    position_value: pd.Series,
    currencies: pd.Series,
    last: pd.Timestamp,
    base: str,
) -> dict[str, Any] | None:
    """Dividends paid in the last 12 months on today's quantities, in base currency."""
    since = last - pd.DateOffset(years=1)
    rows: list[dict[str, Any]] = []
    for asset in quantities.index:
        quote = details.get(str(asset))
        if quote is None or quote.dividends is None or quote.dividends.empty:
            continue
        paid = quote.dividends[(quote.dividends.index > since) & (quote.dividends.index <= last)]
        if paid.empty:
            continue
        currency = str(currencies[asset])
        rate = 1.0 if currency == base else float(rates.get(currency, float("nan")))
        if not math.isfinite(rate):
            continue
        amount = float(paid.sum()) * float(quantities[asset]) * rate
        rows.append(
            {
                "asset": str(asset),
                "payments": len(paid),
                "perUnit": _num(float(paid.sum()), 6),
                "currency": currency,
                "amount": _num(amount, 2),
                "yield": _num(amount / float(position_value[asset])),
                "last": _iso(pd.Timestamp(paid.index[-1])),
            }
        )
    if not rows:
        return None
    total = sum(float(r["amount"]) for r in rows)
    return {
        "since": _iso(since),
        "total": _num(total, 2),
        "yield": _num(total / float(position_value.sum())),
        "rows": sorted(rows, key=lambda r: -float(r["amount"])),
    }


def _news(news: dict[str, list[Headline] | None]) -> dict[str, Any]:
    return {
        asset: None
        if items is None
        else [
            {
                "title": h.title,
                "source": h.source,
                "url": h.url,
                "published": h.published.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            for h in items
        ]
        for asset, items in news.items()
    }


def _history_limit(
    calendar: pd.DatetimeIndex,
    used: pd.DatetimeIndex,
    first_seen: dict[str, Any],
) -> dict[str, Any] | None:
    """Explain a history shorter than requested by naming the series that starts last."""
    requested, actual = calendar[0], used[0]
    if actual - requested <= pd.Timedelta(days=7):
        return None
    known = {k: pd.Timestamp(v) for k, v in first_seen.items() if v is not None}
    limiting = max(known, key=lambda k: known[k]) if known else None
    return {"requested": _iso(requested), "actual": _iso(actual), "asset": limiting}


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
    edit_url: str | None = None,
    proxy_prices: pd.DataFrame | None = None,
    details: dict[str, Quote] | None = None,
    news: dict[str, list[Headline] | None] | None = None,
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
    edit_url : str, optional
        Link back to the page where the portfolio is edited (set by the local app).
    proxy_prices : pd.DataFrame, optional
        Market indices of :data:`quant.stress.PROXIES` in their own currencies, for the
        stress tests; ``local_prices`` and ``fx_rates`` should then reach back to 2007.
        Without it the report has no stress section.
    details : dict, optional
        Live downloads by asset (name, instrument type, dividends), for income.
    news : dict, optional
        Headlines by asset (None where the feed failed).

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
    # Which series starts last: it decides where the common history begins.
    first_seen = {str(c): base_prices[c].first_valid_index() for c in base_prices.columns}
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

    stress = (
        None
        if proxy_prices is None
        else _stress(
            holdings,
            local_prices,
            fx_rates,
            proxy_prices,
            position_value,
            pd.Timestamp(value.index[-1]),
            base,
        )
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
        "historyLimit": _history_limit(calendar, pd.DatetimeIndex(local.index), first_seen),
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
                "kind": _kind(holdings, a),
            }
            for a in order
        ],
        "covariance": _covariance(base_prices, order),
        "currencies": [
            {
                "code": str(c),
                "value": _num(float(v), 2),
                "weight": _num(float(v) / float(value.iloc[-1])),
            }
            for c, v in by_currency.items()
        ],
        "validation": _validation(value),
        "stress": stress,
        "moves": unusual_moves(local),
        "income": None
        if not details
        else dividend_income(
            details,
            quantities,
            rates.iloc[-1] if not rates.empty else pd.Series(dtype=float),
            position_value,
            currencies,
            pd.Timestamp(value.index[-1]),
            base,
        ),
        "news": None if news is None else _news(news),
        "names": {a: q.name for a, q in (details or {}).items() if q.name},
        "factors": None
        if proxy_prices is None
        else _factors(
            value,
            proxy_prices,
            fx_rates,
            stress,
            [str(c) for c in currencies],
            base,
        ),
        "effectivePositions": _num(effective_number_of_positions(position_value), 3),
        "minDaysVar": MIN_DAYS_VAR,
        "minDaysCovariance": MIN_DAYS_COVARIANCE,
        "defaultPeriod": default,
        "periods": periods,
        "editUrl": edit_url,
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
