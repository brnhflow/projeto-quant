"""From a portfolio to a finished report: download, compute, render. Shared by the CLI and app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from quant.data.http import fetch_json
from quant.data.market import Fetch, SeriesStatus, update_market_data
from quant.report import build_report
from quant.stress import HISTORY_START, PROXIES


@dataclass(frozen=True)
class Analysis:
    """A rendered report and what happened to each series while building it."""

    page: str
    status: list[SeriesStatus]

    @property
    def problems(self) -> list[SeriesStatus]:
        """Series that could not be refreshed and came from the cache."""
        return [s for s in self.status if s.error]


def proxy_holdings() -> pd.DataFrame:
    """List the market indices behind the stress tests, in the holdings format."""
    return pd.DataFrame(
        {
            "quantity": 1.0,
            "currency": [currency for _, currency in PROXIES.values()],
            "source": "yahoo",
            "symbol": list(PROXIES),
        },
        index=pd.Index(list(PROXIES), name="asset"),
    )


def analyse_portfolio(
    holdings: pd.DataFrame,
    years: int,
    cache_dir: Path,
    *,
    title: str,
    fetch: Fetch = fetch_json,
    now: pd.Timestamp | None = None,
    offline: bool = False,
    pause: float = 0.2,
    edit_url: str | None = None,
) -> Analysis:
    """Download fresh data for ``holdings`` and build the report over ``years`` of history.

    Prices are requested from 2007 even for a short report, so the stress tests can
    replay the 2008 crisis. The market indices behind the stress tests are optional: if
    they cannot be downloaded nor read from the cache, the report is built without them.

    Raises
    ------
    DataConfigError, ConnectionError, ValueError
        As :func:`quant.data.update_market_data` and :func:`quant.report.build_report`.

    """
    cache = cache_dir
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    start = (now - pd.Timedelta(days=round(years * 365.25))).tz_convert(None).normalize()
    long_start = min(start, HISTORY_START)
    market = update_market_data(
        holdings, long_start, cache, fetch=fetch, now=now, offline=offline, pause=pause
    )
    proxy_prices: pd.DataFrame | None = None
    fx = market.fx
    try:
        indices = update_market_data(
            proxy_holdings(),
            HISTORY_START,
            cache,
            fetch=fetch,
            now=now,
            offline=offline,
            pause=pause,
        )
        proxy_prices = indices.prices
        fx = fx.combine_first(indices.fx) if not fx.empty else indices.fx
    except (ConnectionError, ValueError):
        proxy_prices = None

    calendar = pd.bdate_range(start, pd.Timestamp(market.prices.index.max()))
    page = build_report(
        holdings,
        market.prices,
        fx,
        calendar,
        title=title,
        status=market.status,
        edit_url=edit_url,
        proxy_prices=proxy_prices,
    )
    return Analysis(page, market.status)
