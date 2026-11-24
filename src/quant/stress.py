"""Stress tests: what past crises would do to today's portfolio.

Each scenario is a window of a real crisis (for example 12 Sep 2008 to 9 Mar 2009). For
every position, the loss is taken from history when the asset already traded then, in
euro, so its exchange rate counts too. When it did not (an ETF launched in 2009, a 2023
IPO), the loss is estimated from the market index it moves most like: the index's fall
times the asset's beta to that index, measured on weekly returns over the history they
share. This is how risk systems such as MSCI RiskMetrics fill in missing history.

The same betas drive a scenario the user builds ("Ibovespa -30%, S&P 500 -15%").
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Scenario:
    """A crisis window: prices at the close of ``start`` against the close of ``end``."""

    key: str
    name: str
    start: pd.Timestamp
    end: pd.Timestamp
    description: str


SCENARIOS = (
    Scenario(
        "gfc2008",
        "2008 financial crisis",
        pd.Timestamp("2008-09-12"),
        pd.Timestamp("2009-03-09"),
        "From the eve of the Lehman Brothers collapse to the market bottom.",
    ),
    Scenario(
        "euro2011",
        "European debt crisis",
        pd.Timestamp("2011-07-01"),
        pd.Timestamp("2011-09-22"),
        "Fear of a Greek and Italian default; the US loses its AAA rating.",
    ),
    Scenario(
        "brasil2015",
        "Brazil's 2015 recession",
        pd.Timestamp("2015-05-05"),
        pd.Timestamp("2016-01-26"),
        "Recession, the Car Wash probe and the loss of investment grade; the real falls.",
    ),
    Scenario(
        "brexit2016",
        "Brexit referendum",
        pd.Timestamp("2016-06-23"),
        pd.Timestamp("2016-06-27"),
        "The UK votes to leave the European Union; the pound plunges.",
    ),
    Scenario(
        "joesley2017",
        "Joesley Day",
        pd.Timestamp("2017-05-17"),
        pd.Timestamp("2017-05-18"),
        "A recording implicating the president: one day of panic on B3.",
    ),
    Scenario(
        "covid2020",
        "Covid-19",
        pd.Timestamp("2020-02-19"),
        pd.Timestamp("2020-03-23"),
        "From the market peak to the bottom in five weeks.",
    ),
    Scenario(
        "juros2022",
        "2022 rate hikes",
        pd.Timestamp("2022-01-03"),
        pd.Timestamp("2022-10-12"),
        "High inflation; central banks raise rates at the fastest pace in decades.",
    ),
    Scenario(
        "ftx2022",
        "FTX collapse",
        pd.Timestamp("2022-11-04"),
        pd.Timestamp("2022-11-21"),
        "One of the largest crypto exchanges fails within days.",
    ),
)

# Market indices used as proxies: Yahoo symbol, display name, quote currency.
PROXIES = {
    "^BVSP": ("Ibovespa", "BRL"),
    "^GSPC": ("S&P 500", "USD"),
    "^STOXX50E": ("Euro Stoxx 50", "EUR"),
    "^FTSE": ("FTSE 100", "GBP"),
    "^SSMI": ("SMI (Switzerland)", "CHF"),
    "BTC-USD": ("Bitcoin", "USD"),
    # Global stocks through the iShares MSCI ACWI ETF (since March 2008): with dividends
    # reinvested, so it is also the fairest benchmark for a diversified portfolio.
    "ACWI": ("Global stocks (MSCI ACWI)", "USD"),
}
HISTORY_START = pd.Timestamp("2007-06-01")
MIN_WEEKS = 52
# Vasicek (1973) prior for betas: across stocks they centre on 1 with a spread of about 0.5.
BETA_PRIOR_MEAN = 1.0
BETA_PRIOR_SD = 0.5
TOLERANCE = pd.Timedelta(days=5)


def default_proxy(symbol: str, currency: str) -> str:
    """Proxy by where the asset is listed, used when there is too little history to fit."""
    if symbol.endswith("-USD") or symbol.endswith("-EUR"):
        return "BTC-USD"
    if symbol.endswith(".SA") or currency == "BRL":
        return "^BVSP"
    if symbol.endswith(".L") or currency == "GBP":
        return "^FTSE"
    if symbol.endswith(".SW") or currency == "CHF":
        return "^SSMI"
    if currency == "EUR":
        return "^STOXX50E"
    return "^GSPC"


def price_at(series: pd.Series, date: pd.Timestamp) -> float | None:
    """Last price at or before ``date``, if no older than :data:`TOLERANCE`."""
    known = series.dropna()
    known = known[known.index <= date]
    if known.empty or date - known.index[-1] > TOLERANCE:
        return None
    return float(known.iloc[-1])


def window_return(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    """Return from the close at ``start`` to the close at ``end``, or None without prices."""
    first, last = price_at(series, start), price_at(series, end)
    if first is None or last is None or first <= 0:
        return None
    return last / first - 1


def weekly_returns(prices: pd.Series) -> pd.Series:
    """Friday-to-Friday returns; weekly data hides time-zone gaps between markets."""
    weekly = prices.dropna().resample("W-FRI").last().dropna()
    return weekly.pct_change().dropna()


@dataclass(frozen=True)
class ProxyFit:
    """How an asset moves with an index: ``asset ~ beta * index`` (weekly, in euro).

    ``beta`` is shrunk towards 1 (:func:`vasicek_beta`); ``raw_beta`` is the plain
    regression slope.
    """

    proxy: str
    beta: float
    r2: float
    weeks: int
    fitted: bool  # False: too little history, beta 1 on the listing's index is assumed
    raw_beta: float = 1.0


def vasicek_beta(beta: float, standard_error: float) -> float:
    """Shrink a noisy beta towards the prior mean, more so the less precise it is.

    ``w = prior_var / (prior_var + se^2)``, ``beta_adj = w * beta + (1 - w) * 1``. A beta
    from 20 years of data barely moves; one from a year of a volatile stock moves a lot.
    This keeps a short, noisy estimate from producing impossible crisis losses.
    """
    prior_var = BETA_PRIOR_SD**2
    weight = prior_var / (prior_var + standard_error**2)
    return weight * beta + (1 - weight) * BETA_PRIOR_MEAN


def fit_proxy(
    asset: pd.Series,
    proxies: pd.DataFrame,
    symbol: str,
    currency: str,
    proxy_weekly: dict[str, pd.Series] | None = None,
) -> ProxyFit:
    """Pick the index that explains the asset best (highest R²) and its beta.

    Parameters
    ----------
    asset : pd.Series
        Asset prices in euro.
    proxies : pd.DataFrame
        Index prices in euro, one column per symbol of :data:`PROXIES`.
    symbol, currency : str
        Used only for the fallback when history is too short.

    Returns
    -------
    ProxyFit
        Slope ``cov(asset, index) / var(index)`` on weekly returns, shrunk by
        :func:`vasicek_beta`; with fewer than :data:`MIN_WEEKS` shared weeks for every
        index, beta 1 on :func:`default_proxy`.

    """
    a = weekly_returns(asset)
    best: ProxyFit | None = None
    for proxy in proxies.columns:
        p = proxy_weekly[str(proxy)] if proxy_weekly else weekly_returns(proxies[proxy])
        joined = pd.concat([a, p], axis="columns", keys=["a", "p"], join="inner").dropna()
        if len(joined) < MIN_WEEKS:
            continue
        x = joined["p"].to_numpy(dtype=float)
        y = joined["a"].to_numpy(dtype=float)
        var = float(np.var(x, ddof=1))
        if var <= 0:
            continue
        cov = float(((x - x.mean()) * (y - y.mean())).sum() / (len(x) - 1))
        var_y = float(np.var(y, ddof=1))
        corr = cov / float(np.sqrt(var * var_y)) if var_y > 0 else 0.0
        raw = cov / var
        r2 = float(corr**2)
        n = len(joined)
        # Standard error of the slope: beta * sqrt((1 - R2) / (R2 * (n - 2))).
        unexplained = max(0.0, 1 - r2)  # r2 can round to 1.0000000000000002
        se = abs(raw) * math.sqrt(unexplained / (r2 * (n - 2))) if r2 > 0 else math.inf
        adjusted = vasicek_beta(raw, se) if math.isfinite(se) else BETA_PRIOR_MEAN
        fit = ProxyFit(str(proxy), adjusted, r2, n, True, raw)
        if best is None or fit.r2 > best.r2:
            best = fit
    if best is None:
        return ProxyFit(default_proxy(symbol, currency), 1.0, 0.0, len(a), False)
    return best


@dataclass(frozen=True)
class PositionShock:
    """One position in one scenario."""

    asset: str
    value: float
    change: float | None  # return in euro over the window; None: no data at all
    method: str  # "history", "proxy" or "missing"


def run_scenario(
    scenario: Scenario,
    asset_prices: pd.DataFrame,
    proxies: pd.DataFrame,
    values: pd.Series,
    fits: dict[str, ProxyFit],
) -> list[PositionShock]:
    """Shock every position: its own history if it existed, else its proxy times beta.

    Parameters
    ----------
    asset_prices : pd.DataFrame
        Prices in euro, one column per asset, as long a history as available.
    proxies : pd.DataFrame
        Index prices in euro.
    values : pd.Series
        Value of each position today, in euro.
    fits : dict
        Proxy fit for each asset.

    """
    shocks: list[PositionShock] = []
    for asset, value in values.items():
        name = str(asset)
        own = window_return(asset_prices[name], scenario.start, scenario.end)
        if own is not None:
            shocks.append(PositionShock(name, float(value), own, "history"))
            continue
        fit = fits[name]
        index = (
            window_return(proxies[fit.proxy], scenario.start, scenario.end)
            if fit.proxy in proxies.columns
            else None
        )
        if index is None:
            shocks.append(PositionShock(name, float(value), None, "missing"))
            continue
        # A loss can never exceed the whole position, whatever the beta.
        shocks.append(PositionShock(name, float(value), max(-1.0, fit.beta * index), "proxy"))
    return shocks
