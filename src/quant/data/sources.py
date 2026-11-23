"""Turn public market-data API responses into price and FX series.

Sources (checked working on 2026-11-23):

- Yahoo Finance chart API (``/v8/finance/chart``): stocks and ETFs on B3 (``PETR4.SA``),
  European exchanges (``ASML.AS``, ``VOD.L``) and crypto (``BTC-USD``). Unofficial: no
  published terms or limits, may block bursts of requests or change without notice.
- Kraken public OHLC API: crypto, official, no key. Returns at most the last 720 days.
- Frankfurter: daily euro reference rates published by the European Central Bank.

Parsing is separated from downloading so it can be tested on saved responses.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar
from urllib.parse import quote, urlencode

import pandas as pd

YAHOO = "yahoo"
KRAKEN = "kraken"
SOURCES = (YAHOO, KRAKEN)

# Quotes in minor units: price / divisor gives the major currency.
MINOR_UNITS = {
    "GBp": ("GBP", 100.0),
    "GBX": ("GBP", 100.0),
    "ZAc": ("ZAR", 100.0),
    "ILA": ("ILS", 100.0),
}


@dataclass(frozen=True)
class Quote:
    """A daily price history from one source.

    Attributes
    ----------
    prices : pd.Series
        Daily prices in ``currency``, indexed by naive dates (the exchange's local date).
    currency : str
        ISO code of the prices (minor units such as pence already converted).
    in_progress : bool
        True when the last price is from a session that has not closed yet (live price).
    last_update : pd.Timestamp
        UTC time of the last price.

    """

    prices: pd.Series
    currency: str
    in_progress: bool
    last_update: pd.Timestamp


P = ParamSpec("P")
R = TypeVar("R")


def _tolerant(parse: Callable[P, R]) -> Callable[P, R]:
    """Turn a malformed response (missing key, wrong type) into ValueError.

    Callers treat ValueError as "this source failed" and fall back to the cache; a raw
    KeyError would instead abort the whole analysis.
    """

    @functools.wraps(parse)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return parse(*args, **kwargs)
        except (KeyError, TypeError, AttributeError, IndexError) as error:
            raise ValueError(
                f"unexpected response format ({type(error).__name__}: {error})"
            ) from error

    return wrapper


def _field(node: Any, *path: str | int) -> Any:
    """Walk nested JSON; None as soon as a key or index is missing."""
    for step in path:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError):
            return None
    return node


# ---------------------------------------------------------------- Yahoo


def yahoo_url(symbol: str, start: pd.Timestamp) -> str:
    """Chart API URL for daily bars of ``symbol`` from ``start`` to now."""
    query = urlencode(
        {
            "period1": int(start.timestamp()),
            "period2": 9_999_999_999,
            "interval": "1d",
            "events": "div,splits",
        }
    )
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?{query}"


@_tolerant
def parse_yahoo_chart(payload: dict[str, Any], now: pd.Timestamp) -> Quote:
    """Read adjusted daily closes from a Yahoo chart response.

    Parameters
    ----------
    payload : dict
        Decoded JSON of the chart API.
    now : pd.Timestamp
        Current UTC time, used to tell whether today's session is still open.

    Returns
    -------
    Quote
        Adjusted closes (splits and dividends), in the listing currency.

    Raises
    ------
    ValueError
        If the response reports an error or contains no prices.

    Assumptions
    -----------
    - ``adjclose`` is used, so a dividend does not look like a price drop; Yahoo
      recomputes past adjusted prices after each dividend, which is why callers should
      download the whole history on every update rather than append.
    - During a session the last bar holds the latest trade, not a close.

    """
    chart: Any = payload.get("chart") or {}
    if chart.get("error"):
        raise ValueError(f"Yahoo error: {chart['error']}")
    results: Any = chart.get("result") or []
    if not results or not results[0].get("timestamp"):
        raise ValueError("Yahoo returned no prices")
    result: Any = results[0]
    meta: Any = result["meta"]
    zone = str(meta["exchangeTimezoneName"])
    stamps = [int(t) for t in result["timestamp"]]
    dates = (
        pd.DatetimeIndex(pd.to_datetime(stamps, unit="s", utc=True))
        .tz_convert(zone)
        .normalize()
        .tz_localize(None)
    )
    raw: list[Any] = _field(result, "indicators", "adjclose", 0, "adjclose") or _field(
        result, "indicators", "quote", 0, "close"
    )
    values = [float("nan") if v is None else float(v) for v in raw]
    prices = pd.Series(values, index=dates, dtype=float).dropna()
    prices = prices[~prices.index.duplicated(keep="last")].sort_index()
    if prices.empty:
        raise ValueError("Yahoo returned no prices")

    currency = str(meta["currency"])
    if currency in MINOR_UNITS:
        currency, divisor = MINOR_UNITS[currency]
        prices = prices / divisor

    start_s = int(_field(meta, "currentTradingPeriod", "regular", "start") or 0)
    end_s = int(_field(meta, "currentTradingPeriod", "regular", "end") or 0)
    session_start = pd.Timestamp(start_s, unit="s", tz="UTC")
    session_end = pd.Timestamp(end_s, unit="s", tz="UTC")
    session_date = session_start.tz_convert(zone).normalize().tz_localize(None)
    in_progress = bool(prices.index[-1] == session_date and session_start <= now < session_end)
    last_update = pd.Timestamp(int(meta.get("regularMarketTime", stamps[-1])), unit="s", tz="UTC")
    return Quote(prices.rename(str(meta.get("symbol", ""))), currency, in_progress, last_update)


# Instrument types that make sense to hold; futures and options expire, indices are not
# investable directly.
HOLDABLE_TYPES = {"EQUITY", "ETF", "MUTUALFUND", "CRYPTOCURRENCY"}
# Yahoo's internal codes for venues that are not exchanges.
EXCHANGE_NAMES = {"CCC": "Cripto", "CCY": "Câmbio"}


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


@dataclass(frozen=True)
class SearchHit:
    """One instrument found by name or ticker."""

    symbol: str
    name: str
    exchange: str
    kind: str
    detail: str = ""  # the exchange's short name, e.g. "PETROBRAS PN N2" (share class)


def yahoo_search_url(text: str, count: int = 10) -> str:
    """Search API URL for instruments matching ``text`` (name or ticker)."""
    query = urlencode({"q": text, "quotesCount": count, "newsCount": 0, "listsCount": 0})
    return f"https://query1.finance.yahoo.com/v1/finance/search?{query}"


@_tolerant
def parse_yahoo_search(payload: dict[str, Any]) -> list[SearchHit]:
    """Instruments from a search response, keeping only holdable types.

    Parameters
    ----------
    payload : dict
        Decoded JSON of the search API.

    Returns
    -------
    list of SearchHit
        In the order the source ranks them.

    """
    hits: list[SearchHit] = []
    quotes: list[Any] = _field(payload, "quotes") or []
    for item in quotes:
        kind = str(_field(item, "quoteType") or "")
        symbol = _field(item, "symbol")
        if kind not in HOLDABLE_TYPES or not symbol:
            continue
        long_name, short_name = _clean(_field(item, "longname")), _clean(_field(item, "shortname"))
        name = long_name or short_name or str(symbol)
        detail = short_name if long_name and short_name and short_name != long_name else ""
        exchange = _clean(_field(item, "exchDisp") or _field(item, "exchange"))
        hits.append(
            SearchHit(str(symbol), name, EXCHANGE_NAMES.get(exchange, exchange), kind, detail)
        )
    return hits


@dataclass(frozen=True)
class Snapshot:
    """Current facts about one instrument, to show while the user builds a portfolio."""

    symbol: str
    name: str
    exchange: str
    currency: str
    price: float
    in_progress: bool


def yahoo_snapshot_url(symbol: str) -> str:
    """Chart API URL for the last few days only (fast, used to validate a ticker)."""
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?range=5d&interval=1d"


@_tolerant
def parse_yahoo_snapshot(payload: dict[str, Any], now: pd.Timestamp) -> Snapshot:
    """Name, exchange, currency and latest price from a short chart response.

    The price is the last adjusted close (or the live price during a session), in the
    major currency unit, the same series the report uses.

    Raises
    ------
    ValueError
        If the response reports an error or contains no prices.

    """
    series = parse_yahoo_chart(payload, now)
    meta: Any = _field(payload, "chart", "result", 0, "meta") or {}
    name = meta.get("longName") or meta.get("shortName") or meta.get("symbol") or ""
    return Snapshot(
        symbol=str(meta.get("symbol") or series.prices.name or ""),
        name=" ".join(str(name).split()),
        exchange=EXCHANGE_NAMES.get(
            _clean(meta.get("fullExchangeName") or meta.get("exchangeName")),
            _clean(meta.get("fullExchangeName") or meta.get("exchangeName")),
        ),
        currency=series.currency,
        price=float(series.prices.iloc[-1]),
        in_progress=series.in_progress,
    )


# ---------------------------------------------------------------- Kraken


def kraken_url(pair: str) -> str:
    """OHLC API URL for daily candles of a Kraken pair such as ``XBTUSD``."""
    return f"https://api.kraken.com/0/public/OHLC?{urlencode({'pair': pair, 'interval': 1440})}"


@_tolerant
def parse_kraken_ohlc(payload: dict[str, Any], currency: str, now: pd.Timestamp) -> Quote:
    """Read daily closes from a Kraken OHLC response.

    Parameters
    ----------
    payload : dict
        Decoded JSON of the OHLC API.
    currency : str
        Quote currency of the pair (``USD`` for ``XBTUSD``).
    now : pd.Timestamp
        Current UTC time; today's candle is still open until 00:00 UTC.

    Returns
    -------
    Quote
        Closes by UTC date.

    Raises
    ------
    ValueError
        If the response reports an error or contains no candles.

    Assumptions
    -----------
    - Candles are UTC days. A European business day therefore takes the bitcoin price at
      00:00 UTC of the next day, about 1 a.m. in Europe, close to the stock closes.

    """
    if payload.get("error"):
        raise ValueError(f"Kraken error: {payload['error']}")
    result: Any = payload.get("result") or {}
    keys = [str(k) for k in result if k != "last"]
    if not keys or not result[keys[0]]:
        raise ValueError("Kraken returned no candles")
    candles: Any = result[keys[0]]
    dates = pd.to_datetime([int(c[0]) for c in candles], unit="s").normalize()
    prices = pd.Series([float(c[4]) for c in candles], index=dates, dtype=float).sort_index()
    today = now.tz_convert("UTC").normalize().tz_localize(None)
    in_progress = bool(prices.index[-1] == today)
    last_update = (
        now if in_progress else pd.Timestamp(prices.index[-1], tz="UTC") + pd.Timedelta(days=1)
    )
    return Quote(prices, currency, in_progress, last_update)


# ---------------------------------------------------------------- FX (ECB via Frankfurter)


def frankfurter_url(
    start: pd.Timestamp, end: pd.Timestamp, currencies: list[str], base: str
) -> str:
    """URL for daily ECB reference rates of ``currencies`` against ``base``."""
    symbols = ",".join(sorted(currencies))
    return (
        f"https://api.frankfurter.dev/v1/{start:%Y-%m-%d}..{end:%Y-%m-%d}"
        f"?{urlencode({'base': base, 'symbols': symbols})}"
    )


@_tolerant
def parse_frankfurter(payload: dict[str, Any]) -> pd.DataFrame:
    """Read ECB reference rates and express them as base units per one foreign unit.

    The API quotes "1 EUR = 6.28 BRL"; :func:`quant.fx.to_base_currency` needs "1 BRL =
    0.159 EUR", so each rate is inverted.

    Parameters
    ----------
    payload : dict
        Decoded JSON of a Frankfurter time-series request.

    Returns
    -------
    pd.DataFrame
        One row per ECB publication date, one column per currency.

    Raises
    ------
    ValueError
        If the response has no rates.

    Assumptions
    -----------
    - ECB reference rates are set around 16:00 CET on TARGET business days; there is no
      rate on weekends and TARGET holidays.

    """
    rates: Any = payload.get("rates") or {}
    if not rates:
        raise ValueError("FX source returned no rates")
    table = pd.DataFrame.from_dict(rates, orient="index").astype(float)
    table.index = pd.to_datetime(table.index)
    return (1.0 / table).sort_index()
