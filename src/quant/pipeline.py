"""From a portfolio to a finished report: download, compute, render. Shared by the CLI and app."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from quant.data.http import fetch_bytes, fetch_json
from quant.data.market import (
    Fetch,
    MarketData,
    Series,
    SeriesStatus,
    fetch_series,
    update_market_data,
)
from quant.data.news import Headline, google_news_url, news_query, parse_google_news
from quant.data.rates import RatesData, fetch_rates
from quant.ledger import check_against_holdings
from quant.overview import overview_symbols
from quant.report import build_report
from quant.sentiment import SYMBOLS as SENTIMENT_SYMBOLS
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


FetchText = Callable[[str], bytes]
OVERVIEW_DAYS = 420  # a year of history plus room for the typical-move estimate
SENTIMENT_DAYS = 1250  # two years for the percentile plus a year of gauge history
RATES_WAIT = 20.0  # seconds; past this the report uses the rates saved last time
NO_NEWS_KINDS = {"ETF", "MUTUALFUND"}  # funds rarely make news of their own


def fetch_news(
    holdings: pd.DataFrame, market: MarketData, fetch_text: FetchText, workers: int = 4
) -> dict[str, list[Headline] | None]:
    """Headlines for each stock and crypto held; None where the feed could not be read.

    Funds and cash are skipped. One failed feed never stops the others.
    """
    jobs: dict[str, str] = {}
    for asset, row in holdings.iterrows():
        name = str(asset)
        detail = market.details.get(name)
        if row["source"] == "cash" or detail is None or detail.kind in NO_NEWS_KINDS:
            continue
        query = news_query(str(row["symbol"]), detail.name or name)
        if query is not None:
            jobs[name] = google_news_url(*query)

    def one(url: str) -> list[Headline] | None:
        try:
            return parse_google_news(fetch_text(url))
        except (ConnectionError, ValueError):
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(zip(jobs, pool.map(one, jobs.values()), strict=True))
    return results


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
    fetch_text: FetchText = fetch_bytes,
    demo_url: str | None = None,
    transactions: pd.DataFrame | None = None,
    rates_wait: float = RATES_WAIT,
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
    if transactions is not None:
        problems = check_against_holdings(transactions, holdings)
        if problems:
            raise ValueError("transaction log does not match the holdings: " + "; ".join(problems))
    cache = cache_dir
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    start = (now - pd.Timedelta(days=round(years * 365.25))).tz_convert(None).normalize()
    long_start = min(start, HISTORY_START)
    # The indices download while the holdings do; news starts as soon as names are known.
    # Rates come from slow official files (Tesouro Direto's is 15 MB): they download on their own
    # thread, and if they are not in by the time the rest is, the cached copies are used and the
    # download finishes in the background for next time.
    rates_pool = ThreadPoolExecutor(max_workers=1)
    rates_job = rates_pool.submit(fetch_rates, cache, fetch=fetch_text, now=now, offline=offline)
    rates_pool.shutdown(wait=False)
    with ThreadPoolExecutor(max_workers=4) as pool:
        sentiment_job = pool.submit(
            fetch_series,
            list(SENTIMENT_SYMBOLS),
            (now - pd.Timedelta(days=SENTIMENT_DAYS)).tz_convert(None).normalize(),
            cache,
            fetch=fetch,
            now=now,
            offline=offline,
            pause=pause,
            adjusted=True,
            prefix="sentiment",
        )
        overview_job = pool.submit(
            fetch_series,
            overview_symbols(),
            (now - pd.Timedelta(days=OVERVIEW_DAYS)).tz_convert(None).normalize(),
            cache,
            fetch=fetch,
            now=now,
            offline=offline,
            pause=pause,
        )
        index_job = pool.submit(
            update_market_data,
            proxy_holdings(),
            HISTORY_START,
            cache,
            fetch=fetch,
            now=now,
            offline=offline,
            pause=pause,
        )
        market = update_market_data(
            holdings, long_start, cache, fetch=fetch, now=now, offline=offline, pause=pause
        )
        news_job = pool.submit(fetch_news, holdings, market, fetch_text) if not offline else None
        proxy_prices: pd.DataFrame | None = None
        fx = market.fx
        try:
            indices = index_job.result()
            proxy_prices = indices.prices
            fx = fx.combine_first(indices.fx) if not fx.empty else indices.fx
        except (ConnectionError, ValueError):
            proxy_prices = None
        news = news_job.result() if news_job is not None else {}
        market_series: dict[str, Series] | None
        try:
            market_series = overview_job.result()
        except (ConnectionError, ValueError, OSError):
            market_series = None  # the overview is optional; the portfolio report still builds
        sentiment_series: dict[str, Series] | None
        try:
            sentiment_series = sentiment_job.result()
        except (ConnectionError, ValueError, OSError):
            sentiment_series = None
    rates: RatesData | None
    try:
        rates = rates_job.result(timeout=rates_wait)
    except FutureTimeout:
        rates = fetch_rates(cache, now=now, offline=True)
    except (ConnectionError, ValueError, OSError):
        rates = None

    # Cash is worth 1 every business day up to today; the report must end on the last day
    # a real asset has a price, or the latest move would show as a 0% "phantom" day.
    traded = [str(a) for a, src in holdings["source"].items() if src != "cash"]
    priced = market.prices[traded].dropna(how="all") if traded else market.prices
    calendar = pd.bdate_range(start, pd.Timestamp(priced.index.max()))
    page = build_report(
        holdings,
        market.prices,
        fx,
        calendar,
        title=title,
        status=market.status,
        edit_url=edit_url,
        proxy_prices=proxy_prices,
        details=market.details,
        news=news,
        demo_url=demo_url,
        transactions=transactions,
        market=market_series,
        sentiment=sentiment_series,
        bonds=rates,
    )
    return Analysis(page, market.status)
