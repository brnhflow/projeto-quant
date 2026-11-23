"""Download prices and FX for the holdings, keep a local cache, fall back to it on failure."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from quant.data.http import fetch_json
from quant.data.sources import (
    CASH,
    KRAKEN,
    YAHOO,
    frankfurter_url,
    kraken_url,
    parse_frankfurter,
    parse_kraken_ohlc,
    parse_yahoo_chart,
    yahoo_url,
)

Fetch = Callable[[str], Any]


class DataConfigError(ValueError):
    """The holdings file and the data source disagree; a retry or the cache cannot fix it."""


@dataclass(frozen=True)
class SeriesStatus:
    """What happened to one series during an update."""

    name: str
    source: str
    symbol: str
    last_date: str | None
    in_progress: bool = False
    from_cache: bool = False
    error: str | None = None


@dataclass
class MarketData:
    """Prices (each in its own currency), FX rates and the status of every series."""

    prices: pd.DataFrame
    fx: pd.DataFrame
    status: list[SeriesStatus] = field(default_factory=lambda: [])

    @property
    def problems(self) -> list[SeriesStatus]:
        """Series that could not be refreshed."""
        return [s for s in self.status if s.error]


def _cache_file(cache_dir: Path, source: str, symbol: str) -> Path:
    return cache_dir / f"{source}_{re.sub(r'[^A-Za-z0-9.-]', '_', symbol)}.csv"


def _save(path: Path, table: pd.DataFrame | pd.Series) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index_label="date", lineterminator="\n")


def _save_series(path: Path, series: pd.Series, currency: str, start: pd.Timestamp) -> None:
    """Cache a price series with what it is: its currency and the start that was requested."""
    _save(path, series.rename("price"))
    meta = {"currency": currency, "start": f"{start:%Y-%m-%d}"}
    path.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")


def _load_series(path: Path, currency: str) -> pd.Series | None:
    """Return cached prices, or None when absent or quoted in another currency."""
    table = _load(path)
    if table is None or table.empty:
        return None
    meta_path = path.with_suffix(".json")
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("currency") != currency:
            return None
    return table["price"]


def _load(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, index_col="date", parse_dates=["date"])


def update_market_data(
    holdings: pd.DataFrame,
    start: pd.Timestamp,
    cache_dir: Path,
    *,
    base: str = "EUR",
    fetch: Fetch = fetch_json,
    now: pd.Timestamp | None = None,
    offline: bool = False,
    pause: float = 0.5,
) -> MarketData:
    """Refresh every held asset and the FX rates it needs.

    For each series the whole history from ``start`` is downloaded again (adjusted prices
    change after dividends, so appending would mix old and new adjustments), written to
    ``cache_dir``, and used. If the download fails, the cached copy is used and the
    failure is recorded in the status; if there is no cache either, the error is raised.

    Parameters
    ----------
    holdings : pd.DataFrame
        From :func:`quant.holdings.load_holdings`, with ``source`` and ``symbol`` columns.
    start : pd.Timestamp
        First date of history to request.
    cache_dir : Path
        Folder for the cached CSV files (git-ignored).
    base : str, default "EUR"
        Base currency; FX is requested for every other holding currency.
    fetch : callable, default :func:`quant.data.http.fetch_json`
        URL to decoded JSON; injected in tests.
    now : pd.Timestamp, optional
        Current UTC time; defaults to the clock.
    offline : bool, default False
        Use only the cache, without network access.
    pause : float, default 0.5
        Seconds between requests, to stay polite with free APIs.

    Returns
    -------
    MarketData
        Prices per asset (columns named like the holdings), FX per currency, statuses.

    Raises
    ------
    DataConfigError
        If a source is unknown or reports a different currency than the holdings file.
    ConnectionError
        If a series can neither be downloaded nor read from the cache.

    """
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    statuses: list[SeriesStatus] = []
    columns: dict[str, pd.Series] = {}

    for asset, row in holdings.iterrows():
        name, source, symbol = str(asset), str(row["source"]), str(row["symbol"])
        currency = str(row["currency"])
        if source == CASH:
            # One unit of a currency is worth 1 in that currency on every business day;
            # its risk in euro comes only from the exchange rate.
            today = now.tz_convert(None).normalize()
            columns[name] = pd.Series(1.0, index=pd.bdate_range(start.normalize(), today))
            statuses.append(
                SeriesStatus(name, source, symbol, f"{columns[name].index[-1]:%Y-%m-%d}")
            )
            continue
        path = _cache_file(cache_dir, source, symbol)
        try:
            if offline:
                raise ConnectionError("offline mode")
            if source == YAHOO:
                quote = parse_yahoo_chart(fetch(yahoo_url(symbol, start)), now)
            elif source == KRAKEN:
                quote = parse_kraken_ohlc(fetch(kraken_url(symbol)), currency, now)
            else:
                raise DataConfigError(f"unknown source {source!r} for {name}")
            if quote.currency != currency:
                raise DataConfigError(
                    f"{name}: {source} quotes {symbol} in {quote.currency}, "
                    f"but the holdings file says {currency}"
                )
            series = quote.prices[quote.prices.index >= start.normalize()]
            if series.empty:
                raise ValueError(f"no prices since {start:%Y-%m-%d}")
            _save_series(path, series, currency, start)
            columns[name] = series
            statuses.append(
                SeriesStatus(
                    name, source, symbol, f"{series.index[-1]:%Y-%m-%d}", quote.in_progress
                )
            )
            time.sleep(0 if offline else pause)
        except DataConfigError:
            raise
        except (ConnectionError, ValueError) as error:
            cached = _load_series(path, currency)
            if cached is None:
                raise ConnectionError(
                    f"{name}: no data ({error}) and no cached copy in {currency}"
                ) from error
            series = cached[cached.index >= start.normalize()]
            if series.empty:
                raise ConnectionError(
                    f"{name}: no data ({error}) and the cached copy is too old"
                ) from error
            columns[name] = series
            statuses.append(
                SeriesStatus(
                    name,
                    source,
                    symbol,
                    f"{series.index[-1]:%Y-%m-%d}",
                    from_cache=True,
                    error=None if offline else str(error),
                )
            )

    needed = sorted(set(holdings["currency"].astype(str)) - {base})
    fx = pd.DataFrame(index=pd.DatetimeIndex([]))
    if needed:
        path = cache_dir / f"fx_{base}.csv"
        try:
            if offline:
                raise ConnectionError("offline mode")
            fx = parse_frankfurter(
                fetch(frankfurter_url(start, now.tz_convert(None), needed, base))
            )
            # Keep currencies cached by earlier runs, so a later fallback with another
            # currency mix still finds them.
            previous = _load(path)
            _save(path, fx if previous is None else fx.combine_first(previous))
            statuses.append(SeriesStatus("FX", "ecb", ",".join(needed), f"{fx.index[-1]:%Y-%m-%d}"))
        except (ConnectionError, ValueError) as error:
            cached = _load(path)
            if cached is None or not set(needed) <= set(cached.columns):
                raise ConnectionError(f"FX: no data ({error}) and no cached copy") from error
            fx = cached.loc[cached.index >= start.normalize(), needed]
            statuses.append(
                SeriesStatus(
                    "FX",
                    "ecb",
                    ",".join(needed),
                    f"{fx.index[-1]:%Y-%m-%d}",
                    from_cache=True,
                    error=None if offline else str(error),
                )
            )

    prices = pd.concat(columns, axis="columns", sort=True)
    return MarketData(prices=prices, fx=fx, status=statuses)
