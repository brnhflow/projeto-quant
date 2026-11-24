"""Compute everything the portfolio report shows, for each selectable period.

All numbers come from the tested functions in :mod:`quant`; the HTML page only draws them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import pandas as pd

from quant.align import align_to_dates
from quant.attribution import return_attribution
from quant.benchmark import compare
from quant.brinson import brinson_fachler, style_r2, style_weights
from quant.data.market import SeriesStatus
from quant.data.news import Headline
from quant.data.sources import Quote
from quant.factors import factor_exposure
from quant.fx import to_base_currency
from quant.income import outlook
from quant.ledger import analyse_ledger
from quant.performance import xirr
from quant.returns import portfolio_value, simple_returns
from quant.risk import (
    annualized_volatility,
    drawdown,
    effective_number_of_positions,
    historical_var_es,
    ledoit_wolf,
    risk_adjusted_ratios,
    risk_contributions,
)
from quant.signals import (
    CONCENTRATION_RISK,
    CONCENTRATION_WEIGHT,
    FAR_FROM_HIGH,
    MIN_VOL_GAIN,
    YIELD_PREMIUM,
    diversification_gain,
    gap_from_high,
    yield_vs_history,
)
from quant.simulation import calibrate, drawdown_probability, quantile_table, simulate_growth
from quant.stress import (
    PROXIES,
    SCENARIOS,
    ProxyFit,
    fit_proxy,
    run_scenario,
    weekly_returns,
    window_return,
)
from quant.tearsheet import (
    ROLLING_WINDOW,
    annual_returns,
    drawdown_periods,
    monthly_returns,
    return_histogram,
    rolling_sharpe,
    rolling_volatility,
    summary,
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
    Period("1M", "1M", 1),
    Period("3M", "3M", 3),
    Period("6M", "6M", 6),
    Period("YTD", "YTD", None),
    Period("12M", "12M", 12),
    Period("ALL", "All", 0),
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
    contributions: pd.Series | None = None
    if len(asset_returns) >= MIN_DAYS_COVARIANCE:
        try:
            contributions = risk_contributions(asset_returns, weights_now)
        except ValueError:  # no variance at all, e.g. only euro cash
            contributions = None
    if contributions is not None:
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
        "ratios": {
            k: None if v is None else _num(v, 3) for k, v in risk_adjusted_ratios(v).items()
        },
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
_NO_QUOTE = Quote(pd.Series(dtype=float), "", False, pd.Timestamp(0, tz="UTC"))


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
    shrunk, shrinkage = ledoit_wolf(returns)
    matrix = (shrunk * 252).to_numpy(dtype=float)
    return {
        "assets": order,
        "days": len(returns),
        "shrinkage": _num(shrinkage, 4),
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
    proxy_weekly = {str(p): weekly_returns(proxies_eur[p]) for p in proxies_eur.columns}
    fits: dict[str, ProxyFit] = {}
    positions: list[dict[str, Any]] = []
    for asset in holdings.index:
        name = str(asset)
        is_cash = source_of[name] == "cash"
        symbol = symbol_of[name]
        fit = fit_proxy(assets_eur[name], proxies_eur, symbol, str(currencies[asset]), proxy_weekly)
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
    "USD": "US dollar",
    "BRL": "Brazilian real",
    "GBP": "British pound",
    "CHF": "Swiss franc",
    "JPY": "Japanese yen",
    "CAD": "Canadian dollar",
    "AUD": "Australian dollar",
    "SEK": "Swedish krona",
    "NOK": "Norwegian krone",
    "DKK": "Danish krone",
    "HKD": "Hong Kong dollar",
    "CNY": "Chinese yuan",
    "PLN": "Polish zloty",
    "MXN": "Mexican peso",
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
    # Global stocks are largely the US and Europe: with either regional index already a
    # factor, ACWI only adds collinearity (unstable, meaningless betas), so it is left out.
    if "ACWI" in markets and {"^GSPC", "^STOXX50E", "^FTSE", "^SSMI"} & set(markets):
        markets.remove("ACWI")
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


def income_plan(
    details: dict[str, Quote],
    quantities: pd.Series,
    rates: pd.Series,
    position_value: pd.Series,
    currencies: pd.Series,
    last: pd.Timestamp,
    base: str,
) -> dict[str, Any] | None:
    """Project income for the next 12 months per asset, in base currency, with its growth."""
    months: list[pd.Timestamp] = []
    rows: list[dict[str, Any]] = []
    for asset in quantities.index:
        quote = details.get(str(asset))
        if quote is None or quote.dividends is None:
            continue
        view = outlook(quote.dividends, last)
        months = view.months
        currency = str(currencies[asset])
        rate = 1.0 if currency == base else float(rates.get(currency, float("nan")))
        if not math.isfinite(rate):
            continue
        if float(position_value[asset]) <= 0:
            continue
        per_month = [v * float(quantities[asset]) * rate for v in view.per_unit]
        annual = sum(per_month)
        if annual <= 0 and view.last is None:
            continue
        rows.append(
            {
                "asset": str(asset),
                "months": [_num(v, 2) for v in per_month],
                "annual": _num(annual, 2),
                "yield": _num(annual / float(position_value[asset])),
                "growth": None if view.growth is None else _num(view.growth, 4),
                "paidYears": view.paid_years,
                "last": None if view.last is None else _iso(view.last),
            }
        )
    if not rows:
        return None
    total = sum(float(r["annual"]) for r in rows)
    return {
        "months": [f"{m:%Y-%m}" for m in months],
        "assets": sorted(rows, key=lambda r: -float(r["annual"])),
        "annual": _num(total, 2),
        "value": _num(float(position_value.sum()), 2),
        "yield": _num(total / float(position_value.sum())),
        "growthYears": 5,
    }


def _opportunities(
    holdings: pd.DataFrame,
    local_prices: pd.DataFrame,
    base_prices: pd.DataFrame,
    value: pd.Series,
    weights_now: pd.Series,
    fx_rates: pd.DataFrame,
    proxy_prices: pd.DataFrame | None,
    details: dict[str, Quote] | None,
    base: str,
) -> dict[str, Any]:
    """Rule-based signals of :mod:`quant.signals`, for the "opportunities" page."""
    cash = (
        {str(a) for a, src in holdings["source"].items() if src == "cash"}
        if "source" in holdings
        else set[str]()
    )
    far: list[dict[str, Any]] = []
    rich: list[dict[str, Any]] = []
    for asset in holdings.index:
        name = str(asset)
        if name in cash or name not in local_prices.columns:
            continue
        gap = gap_from_high(local_prices[name])
        if gap is not None and gap.gap <= FAR_FROM_HIGH:
            far.append(
                {
                    "asset": name,
                    "gap": _num(gap.gap),
                    "high": _num(gap.high, 4),
                    "highDate": _iso(gap.high_date),
                    "last": _num(gap.last, 4),
                    "currency": str(holdings.loc[asset, "currency"]),
                }
            )
        quote = (details or {}).get(name)
        if quote is not None and quote.dividends is not None and not quote.dividends.empty:
            # Adjusted prices are lowered by later dividends, which would overstate past
            # yields: the ratio needs the prices actually quoted at the time.
            raw = quote.close if quote.close is not None else None
            check = None if raw is None else yield_vs_history(raw, quote.dividends)
            if (
                check is not None
                and check.median > 0
                and check.current >= YIELD_PREMIUM * check.median
            ):
                rich.append(
                    {"asset": name, "current": _num(check.current), "median": _num(check.median)}
                )

    diversifiers: list[dict[str, Any]] = []
    if proxy_prices is not None:
        calendar = pd.DatetimeIndex(value.index)
        available = [p for p in PROXIES if p in proxy_prices.columns]
        currencies = pd.Series({p: PROXIES[p][1] for p in available})
        if available and set(currencies) - {base} <= set(fx_rates.columns):
            indices = to_base_currency(
                align_to_dates(proxy_prices[available], calendar),
                currencies,
                align_to_dates(fx_rates, calendar),
                base=base,
            )
            for p in available:
                result = diversification_gain(value, indices[p])
                if result is None:
                    continue
                now, after, corr = result
                if now - after >= MIN_VOL_GAIN:
                    diversifiers.append(
                        {
                            "symbol": p,
                            "name": PROXIES[p][0],
                            "volNow": _num(now),
                            "volWith": _num(after),
                            "corr": _num(corr, 3),
                        }
                    )
    diversifiers.sort(key=lambda d: float(d["volWith"]))

    concentrated: list[dict[str, Any]] = []
    returns = simple_returns(base_prices).iloc[-COVARIANCE_DAYS:]
    shares: pd.Series | None = None
    if len(returns) >= MIN_DAYS_COVARIANCE:
        try:
            shares = risk_contributions(returns, weights_now)
        except ValueError:
            shares = None
    for asset in holdings.index:
        if str(asset) in cash:
            continue
        weight = float(weights_now[asset])
        risk = float(shares[asset]) if shares is not None else float("nan")
        if weight > CONCENTRATION_WEIGHT or (math.isfinite(risk) and risk > CONCENTRATION_RISK):
            concentrated.append({"asset": str(asset), "weight": _num(weight), "risk": _num(risk)})
    return {
        "farFromHigh": sorted(far, key=lambda r: float(r["gap"])),
        "yieldHigh": sorted(rich, key=lambda r: -float(r["current"]) / float(r["median"])),
        "diversifiers": diversifiers[:3],
        "concentration": concentrated,
        "rules": {
            "farFromHigh": FAR_FROM_HIGH,
            "yieldPremium": YIELD_PREMIUM,
            "concentrationWeight": CONCENTRATION_WEIGHT,
            "concentrationRisk": CONCENTRATION_RISK,
        },
    }


BENCHMARKS = (
    ("ACWI", True),  # (symbol, includes dividends)
    ("^GSPC", False),
    ("^STOXX50E", False),
    ("^BVSP", False),
)


def _benchmark_series(
    value: pd.Series, proxy_prices: pd.DataFrame | None, fx_rates: pd.DataFrame, base: str
) -> list[tuple[str, bool, pd.Series, pd.Series]]:
    """Each available benchmark in the base currency on the report's dates.

    Returns ``(symbol, includes dividends, series, exact)``: ``series`` carries holidays
    forward for drawing; ``exact`` is NaN on days the index did not trade, for statistics
    (a holiday carried forward would be a 0% day and bias beta, correlation and capture
    towards zero).
    """
    if proxy_prices is None:
        return []
    calendar = pd.DatetimeIndex(value.index)
    chosen = [(b, total) for b, total in BENCHMARKS if b in proxy_prices.columns]
    currencies = pd.Series({b: PROXIES[b][1] for b, _ in chosen})
    if not chosen or not set(currencies) - {base} <= set(fx_rates.columns):
        return []
    indices = to_base_currency(
        align_to_dates(proxy_prices[[b for b, _ in chosen]], calendar),
        currencies,
        align_to_dates(fx_rates, calendar),
        base=base,
    )
    out: list[tuple[str, bool, pd.Series, pd.Series]] = []
    for b, total in chosen:
        series = indices[b]
        traded = proxy_prices[b].dropna().index
        out.append((b, total, series, series.where(series.index.isin(traded))))
    return out


def _benchmarks(
    value: pd.Series, proxy_prices: pd.DataFrame | None, fx_rates: pd.DataFrame, base: str
) -> dict[str, Any] | None:
    """Benchmark series on the report's dates and, per period, how the portfolio compares."""
    calendar = pd.DatetimeIndex(value.index)
    items: list[dict[str, Any]] = []
    for b, total, series, exact in _benchmark_series(value, proxy_prices, fx_rates, base):
        stats: dict[str, Any] = {}
        for period in PERIODS:
            start = period_start(calendar, period)
            if start is None:
                continue
            try:
                s = compare(value.iloc[start:], exact.iloc[start:])
            except ValueError:
                continue
            stats[period.key] = {
                "portfolio": _num(s.portfolio_return),
                "benchmark": _num(s.benchmark_return),
                "beta": _num(s.beta, 4),
                "alpha": _num(s.alpha),
                "correlation": _num(s.correlation, 4),
                "trackingError": _num(s.tracking_error),
                "informationRatio": None
                if s.information_ratio is None
                else _num(s.information_ratio, 3),
                "upCapture": None if s.up_capture is None else _num(s.up_capture, 3),
                "downCapture": None if s.down_capture is None else _num(s.down_capture, 3),
            }
        if stats:
            items.append(
                {
                    "key": b,
                    "name": PROXIES[b][0],
                    "dividends": total,
                    "values": [None if math.isnan(float(x)) else _num(float(x), 4) for x in series],
                    "periods": stats,
                }
            )
    return {"items": items} if items else None


def _tearsheet(
    value: pd.Series, proxy_prices: pd.DataFrame | None, fx_rates: pd.DataFrame, base: str
) -> dict[str, Any] | None:
    """Build the tearsheet tab's data: whole history, against the first benchmark."""
    if len(value) < 40:
        return None

    def stats(series: pd.Series) -> dict[str, Any]:
        return {
            k: (v if isinstance(v, int) or v is None else _num(float(v), 6))
            for k, v in summary(series).items()
        }

    def rolling(series: pd.Series, dates: pd.DatetimeIndex) -> dict[str, list[float | None]]:
        sharpe = rolling_sharpe(series).reindex(dates)
        vol = rolling_volatility(series).reindex(dates)
        return {
            "sharpe": [None if math.isnan(float(x)) else _num(float(x), 4) for x in sharpe],
            "volatility": [None if math.isnan(float(x)) else _num(float(x), 5) for x in vol],
        }

    bench: dict[str, Any] | None = None
    bench_months: pd.Series | None = None
    bench_years: pd.Series | None = None
    calendar = pd.DatetimeIndex(value.index)
    first = next(iter(_benchmark_series(value, proxy_prices, fx_rates, base)), None)
    if first is not None:
        b, total, _, exact = first
        traded = exact.dropna()
        if len(traded) >= 40:
            bench_months = monthly_returns(traded)
            bench_years = annual_returns(traded)
            bench = {
                "key": b,
                "name": PROXIES[b][0],
                "dividends": total,
                "stats": stats(traded),
                "rolling": rolling(traded, calendar),
            }

    months = monthly_returns(value)
    years = annual_returns(value)
    table: list[dict[str, Any]] = []
    month_dates = pd.DatetimeIndex(months.index)
    for year in sorted(set(month_dates.year.tolist())):
        row: list[float | None] = [None] * 12
        for d, r in zip(month_dates, months.to_numpy(dtype=float), strict=True):
            if d.year == year:
                row[d.month - 1] = _num(float(r))
        table.append(
            {
                "year": int(year),
                "months": row,
                "total": _num(float(years[year])),
                "benchmark": None
                if bench_years is None or year not in bench_years.index
                else _num(float(bench_years[year])),
            }
        )
    hist = return_histogram(value)
    return {
        "start": _iso(value.index[0]),
        "end": _iso(value.index[-1]),
        "window": ROLLING_WINDOW,
        "stats": stats(value),
        "benchmark": bench,
        "monthly": table,
        "benchmarkMonths": None
        if bench_months is None
        else {
            d.strftime("%Y-%m"): _num(float(r))
            for d, r in zip(
                pd.DatetimeIndex(bench_months.index),
                bench_months.to_numpy(dtype=float),
                strict=True,
            )
        },
        "dates": [_iso(d) for d in calendar],
        "rolling": rolling(value, calendar),
        "drawdowns": [
            {
                "peak": _iso(p.peak),
                "trough": _iso(p.trough),
                "recovery": None if p.recovery is None else _iso(p.recovery),
                "depth": _num(p.depth),
                "daysDown": p.days_down,
                "daysToRecover": p.days_to_recover,
            }
            for p in drawdown_periods(value)
        ],
        "histogram": {
            "edges": [_num(e, 6) for e in hist.edges],
            "counts": hist.counts,
            "normal": [_num(x, 3) for x in hist.normal],
        },
    }


def _result(
    holdings: pd.DataFrame,
    local: pd.DataFrame,
    fx_rates: pd.DataFrame,
    position_value: pd.Series,
    base: str,
    last: pd.Timestamp,
) -> dict[str, Any] | None:
    """Gain on the money invested, from each position's average cost and purchase date.

    The cost is converted at the exchange rate of the purchase date (the last rate at or
    before it); without a date, at today's rate, and the position is flagged. The annual
    money-weighted return (XIRR) needs a date for every position with a cost.
    """
    if "cost" not in holdings.columns:
        return None
    since = holdings["since"] if "since" in holdings.columns else pd.Series(pd.NaT, holdings.index)
    rows: list[dict[str, Any]] = []
    flows: list[tuple[pd.Timestamp, float]] = []
    dated = True
    names = [str(a) for a in holdings.index]
    costs = dict(zip(names, holdings["cost"].astype(float).tolist(), strict=True))
    units = dict(zip(names, holdings["quantity"].astype(float).tolist(), strict=True))
    money = dict(zip(names, holdings["currency"].astype(str).tolist(), strict=True))
    kinds = dict(zip(names, holdings["source"].astype(str).tolist(), strict=True))
    for asset in holdings.index:
        name = str(asset)
        cost = costs[name]
        if not math.isfinite(cost) or kinds[name] == "cash":
            continue
        currency = money[name]
        bought = since[asset]
        has_date = isinstance(bought, pd.Timestamp) and not pd.isna(bought)
        rate = 1.0
        if currency != base:
            history = fx_rates[currency].dropna() if currency in fx_rates.columns else pd.Series()
            if history.empty:
                continue
            before = history[history.index <= bought] if has_date else history
            # A purchase older than the rate history uses its first rate.
            rate = float(before.iloc[-1]) if not before.empty else float(history.iloc[0])
        quantity = units[name]
        invested = cost * quantity * rate
        value = float(position_value[asset])
        price_now = float(local[name].iloc[-1])
        rows.append(
            {
                "asset": str(asset),
                "cost": _num(cost, 4),
                "since": _iso(bought) if has_date else None,
                "invested": _num(invested, 2),
                "value": _num(value, 2),
                "gainLocal": _num(price_now / cost - 1),
                "gainBase": _num(value / invested - 1),
            }
        )
        if has_date:
            flows.append((pd.Timestamp(bought), -invested))
        else:
            dated = False
    if not rows:
        return None
    invested = sum(float(r["invested"]) for r in rows)
    value = sum(float(r["value"]) for r in rows)
    rate = xirr([*flows, (last, value)]) if dated and flows else None
    return {
        "positions": rows,
        "invested": _num(invested, 2),
        "value": _num(value, 2),
        "gain": _num(value - invested, 2),
        "gainPct": _num(value / invested - 1),
        "xirr": None if rate is None else _num(rate),
        "first": min((r["since"] for r in rows if r["since"]), default=None),
        "covered": _num(value / float(position_value.sum())),
    }


def _ledger(
    transactions: pd.DataFrame | None,
    holdings: pd.DataFrame,
    base_prices: pd.DataFrame,
    fx_rates: pd.DataFrame,
    base: str,
) -> dict[str, Any] | None:
    """Time- and money-weighted returns and gains from the transaction log, if there is one."""
    if transactions is None or transactions.empty:
        return None
    r = analyse_ledger(transactions, holdings, base_prices, fx_rates, base)
    dates = pd.DatetimeIndex(cast(pd.DatetimeIndex, r["dates"]))
    value = cast(pd.Series, r["value"])
    invested = cast(pd.Series, r["invested"])
    twr = cast(pd.Series, r["twr"]).fillna(0.0)
    growth = (1 + twr).cumprod()
    positions = cast(dict[str, Any], r["positions"])
    end_values = cast(dict[str, float], r["endValues"])
    mwr = r["mwr"]
    twr_annual = r["twrAnnual"]
    return {
        "dates": [_iso(d) for d in dates],
        "value": [_num(float(x), 2) for x in value],
        "invested": [_num(float(x), 2) for x in invested],
        "twrIndex": [1.0] + [_num(float(x), 6) for x in growth],
        "twrTotal": _num(cast(float, r["twrTotal"])),
        "twrAnnual": None if twr_annual is None else _num(cast(float, twr_annual)),
        "mwr": None if mwr is None else _num(cast(float, mwr)),
        "netInvested": _num(cast(float, r["netInvested"]), 2),
        "end": _num(cast(float, r["end"]), 2),
        "realised": _num(cast(float, r["realised"]), 2),
        "unrealised": _num(cast(float, r["unrealised"]), 2),
        "first": _iso(cast(pd.Timestamp, r["first"])),
        "trades": r["trades"],
        "beforeHistory": r["beforeHistory"],
        "positions": [
            {
                "asset": a,
                "units": _num(p.units, 8),
                "costBasis": _num(p.cost_basis, 2),
                "averageCost": None if p.units <= 0 else _num(p.cost_basis / p.units, 4),
                "value": _num(end_values.get(a, 0.0), 2),
                "unrealised": _num(end_values.get(a, 0.0) - p.cost_basis, 2),
                "realised": _num(p.realised, 2),
                "bought": _num(p.bought, 2),
                "sold": _num(p.sold, 2),
            }
            for a, p in sorted(positions.items(), key=lambda kv: -end_values.get(kv[0], 0.0))
        ],
    }


STYLE_WEEKS = 104  # two years of weekly returns for the benchmark's regional mix
GLOBAL = "ACWI"


def _brinson(
    holdings: pd.DataFrame,
    local_prices: pd.DataFrame,
    fx_rates: pd.DataFrame,
    proxy_prices: pd.DataFrame | None,
    held: pd.DataFrame,
    base: str,
) -> dict[str, Any] | None:
    """Brinson attribution against MSCI ACWI, with markets as segments.

    Each asset belongs to the regional index that explains it best (global stocks excluded,
    so a world ETF is split no further than its best region). The benchmark's weights on
    those regions come from returns-based style analysis of ACWI over the last two years.
    ``held`` is the value of each position in the base currency on the report's dates.
    """
    if proxy_prices is None or GLOBAL not in proxy_prices.columns:
        return None
    regions = [p for p in PROXIES if p != GLOBAL and p in proxy_prices.columns]
    symbols = [*regions, GLOBAL]
    index_currency = pd.Series({p: PROXIES[p][1] for p in symbols})
    if not regions or not set(index_currency) - {base} <= set(fx_rates.columns):
        return None
    last = pd.Timestamp(held.index[-1])
    first = min(pd.Timestamp(local_prices.index.min()), pd.Timestamp(proxy_prices.index.min()))
    long = pd.bdate_range(first, last)
    indices = to_base_currency(
        align_to_dates(proxy_prices[symbols], long),
        index_currency,
        align_to_dates(fx_rates, long),
        base=base,
    )
    weekly = {p: weekly_returns(indices[p]) for p in symbols}
    style = pd.DataFrame(weekly).dropna().tail(STYLE_WEEKS)
    if len(style) < 26:
        return None
    wb_all = style_weights(style[GLOBAL], style[regions])
    r2 = style_r2(style[GLOBAL], style[regions], wb_all)
    # Weights under 1% are noise of the fit, not a real allocation of the index.
    wb_all = wb_all.where(wb_all >= 0.01, 0.0)
    wb_all = wb_all / float(wb_all.sum())

    assets_eur = to_base_currency(
        align_to_dates(local_prices[holdings.index], long),
        holdings["currency"],
        align_to_dates(fx_rates, long),
        base=base,
    )
    names = [str(a) for a in holdings.index]
    sources = holdings["source"] if "source" in holdings else pd.Series("yahoo", holdings.index)
    tickers = holdings["symbol"] if "symbol" in holdings else pd.Series(names, holdings.index)
    segment: dict[str, str] = {}
    for asset, source, symbol, currency in zip(
        holdings.index, sources, tickers, holdings["currency"], strict=True
    ):
        if source == "cash":
            segment[str(asset)] = "cash"
            continue
        prices = cast(pd.Series, assets_eur[asset])
        fit = fit_proxy(prices, indices[regions], str(symbol), str(currency), weekly)
        segment[str(asset)] = fit.proxy if fit.proxy in regions else "^GSPC"

    calendar = pd.DatetimeIndex(held.index)
    on_dates = align_to_dates(indices[regions], calendar)
    global_on_dates = align_to_dates(indices[[GLOBAL]], calendar)[GLOBAL]
    periods: dict[str, Any] = {}
    for period in PERIODS:
        start = period_start(calendar, period)
        if start is None:
            continue
        v0, v1 = held.iloc[start], held.iloc[-1]
        keys = sorted({*segment.values(), *[p for p in regions if wb_all[p] > 0.005]})
        wp = pd.Series(0.0, index=keys)
        rp = pd.Series(0.0, index=keys)
        rb = pd.Series(0.0, index=keys)
        for key in keys:
            members = [a for a, s in segment.items() if s == key]
            start_value = float(v0[members].sum()) if members else 0.0
            wp[key] = start_value / float(v0.sum())
            if key != "cash":
                a, b = on_dates[key].iloc[start], on_dates[key].iloc[-1]
                rb[key] = float(b / a - 1) if a > 0 and not math.isnan(float(a)) else 0.0
            rp[key] = float(v1[members].sum()) / start_value - 1 if start_value > 0 else rb[key]
        # Not held: no selection effect. Cash: its whole effect is allocation.
        rb["cash"] = rp["cash"] if "cash" in keys else 0.0
        wb = wb_all.reindex(keys, fill_value=0.0)
        wb = wb / wb.sum()
        effects = cast(
            dict[str, dict[str, float]], brinson_fachler(wp, rp, wb, rb).to_dict(orient="index")
        )
        g0, g1 = global_on_dates.iloc[start], global_on_dates.iloc[-1]
        periods[period.key] = {
            "portfolio": _num(float((wp * rp).sum())),
            "benchmark": _num(float((wb * rb).sum())),
            "global": _num(float(g1 / g0 - 1)) if g0 > 0 else None,
            "segments": [
                {
                    "key": k,
                    "name": "Cash" if k == "cash" else PROXIES[k][0],
                    "wp": _num(float(wp[k])),
                    "wb": _num(float(wb[k])),
                    "rp": _num(float(rp[k])),
                    "rb": _num(float(rb[k])),
                    "allocation": _num(effects[k]["allocation"]),
                    "selection": _num(effects[k]["selection"]),
                    "interaction": _num(effects[k]["interaction"]),
                }
                for k in keys
            ],
        }
    return {
        "r2": _num(r2, 4),
        "weeks": len(style),
        "weights": {p: _num(float(w)) for p, w in wb_all.items() if w > 0.0005},
        "segmentOf": segment,
        "periods": periods,
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


SIM_PATHS = 2000
SIM_YEARS = 5
SIM_MIN_DAYS = 120
FAN = (0.05, 0.25, 0.5, 0.75, 0.95)


def _simulation(value: pd.Series) -> dict[str, Any] | None:
    """Fan of possible values for the next 5 years, with and without the past trend."""
    returns = simple_returns(value.to_frame())["value"]
    if len(returns) < SIM_MIN_DAYS:
        return None
    days = SIM_YEARS * 252
    now = float(value.iloc[-1])
    months = list(range(21, days + 1, 21))
    out: dict[str, Any] = {
        "days": len(returns),
        "start": _iso(pd.Timestamp(value.index[0])),
        "value": _num(now, 2),
        "paths": SIM_PATHS,
        "months": len(months),
        "quantiles": list(FAN),
    }
    for key, demean in (("neutral", True), ("trend", False)):
        growth = simulate_growth(returns.to_numpy(dtype=float), days, SIM_PATHS, demean=demean)
        table = quantile_table(growth, FAN)
        out[key] = {
            "fan": [
                [_num(now * float(table[q, m - 1]), 2) for m in months] for q in range(len(FAN))
            ],
            "drawdown": {
                str(int(x * 100)): _num(drawdown_probability(growth[:, :252], x), 4)
                for x in (0.1, 0.2, 0.3)
            },
            "loss": _num(float((growth[:, 251] < 1).mean()), 4),
        }
    try:
        cal = calibrate(returns)
        out["calibration"] = {
            "checks": cal.checks,
            "inside": cal.inside,
            "level": cal.level,
            "pValue": _num(cal.p_value, 4),
        }
    except ValueError:
        out["calibration"] = None
    return out


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
    demo_url: str | None = None,
    transactions: pd.DataFrame | None = None,
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
    demo_url : str, optional
        Marks a public demo built on made-up holdings, linking to the source code.
    transactions : pd.DataFrame, optional
        Every buy and sell (:func:`quant.ledger.parse_transactions`), matching the holdings;
        adds the time- and money-weighted returns and realised gains.

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
                # What the source says about it, for the asset-type icon in the page.
                "symbol": str(holdings.loc[a, "symbol"]) if "symbol" in holdings.columns else a,
                "srcKind": (details or {}).get(a, _NO_QUOTE).kind,
                "detail": (details or {}).get(a, _NO_QUOTE).detail,
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
        "benchmarks": _benchmarks(value, proxy_prices, fx_rates, base),
        "tearsheet": _tearsheet(value, proxy_prices, fx_rates, base),
        "ledger": _ledger(transactions, holdings, base_prices, fx_rates, base),
        "brinson": _brinson(
            holdings,
            local_prices,
            fx_rates,
            proxy_prices,
            base_prices * quantities,
            base,
        ),
        "moves": unusual_moves(local),
        "result": _result(
            holdings, local, fx_rates, position_value, base, pd.Timestamp(value.index[-1])
        ),
        "simulation": _simulation(value),
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
        "incomePlan": None
        if not details
        else income_plan(
            details,
            quantities,
            rates.iloc[-1] if not rates.empty else pd.Series(dtype=float),
            position_value,
            currencies,
            pd.Timestamp(value.index[-1]),
            base,
        ),
        "opportunities": _opportunities(
            holdings,
            local_prices,
            base_prices,
            value,
            weights_now,
            fx_rates,
            proxy_prices,
            details,
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
        "demo": demo_url,
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
