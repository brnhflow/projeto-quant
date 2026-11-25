"""Market overview: what moved, by how much, and how unusual the move was.

A fixed list of the series people check first (stock indices, currencies, interest rates,
commodities, crypto, and the largest stocks in Brazil, the US and Europe) is downloaded with
each report. For every series and look-back window this module computes:

- the change: price return, or the change in percentage points for an interest rate;
- how unusual it is: the change divided by the series' own typical move over that many
  trading days (daily standard deviation over the previous year times the square root of the
  number of days). A z of 2.5 on a day happens about 1% of days under a normal model; fat
  tails make it a little more common, which is why the threshold is a reading aid, not a test;
- how closely the portfolio follows it: correlation of weekly returns over the last year
  (weekly, because markets on different continents close at different hours and daily returns
  would understate their link).

Ranking moves by their z, not by their size, is what puts a 3% move in a bond yield above a
6% move in a cryptocurrency that moves 4% on an ordinary day.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from quant.data.market import Series

UNUSUAL_Z = 2.0
VOL_DAYS = 250  # one year of trading days for the typical move
STALE_DAYS = 10  # a series this far behind the newest one is left out (delisted, broken feed)
SPARK_DAYS = 400


@dataclass(frozen=True)
class Instrument:
    """One series in the overview."""

    symbol: str
    group: str  # indices, fx, rates, commodities, crypto, stocks
    pt: str
    en: str
    short: str = ""
    region: str = ""  # BR, US, EU for stocks
    rate: bool = False  # quoted as a yield in percent: changes in points, not returns


def _stock(symbol: str, short: str, region: str, name: str) -> Instrument:
    return Instrument(symbol, "stocks", name, name, short, region)


UNIVERSE: tuple[Instrument, ...] = (
    Instrument("^BVSP", "indices", "Ibovespa", "Ibovespa", "IBOV", "BR"),
    Instrument("^GSPC", "indices", "S&P 500", "S&P 500", "SPX", "US"),
    Instrument("^IXIC", "indices", "Nasdaq", "Nasdaq", "NDQ", "US"),
    Instrument("^STOXX50E", "indices", "Euro Stoxx 50", "Euro Stoxx 50", "SX5E", "EU"),
    Instrument("^GDAXI", "indices", "DAX (Alemanha)", "DAX (Germany)", "DAX", "EU"),
    Instrument("^FTSE", "indices", "FTSE 100 (Reino Unido)", "FTSE 100 (UK)", "UKX", "EU"),
    Instrument("^N225", "indices", "Nikkei 225 (Japão)", "Nikkei 225 (Japan)", "NKY"),
    Instrument("^HSI", "indices", "Hang Seng (Hong Kong)", "Hang Seng (Hong Kong)", "HSI"),
    Instrument("BRL=X", "fx", "Dólar em reais", "US dollar in reais", "USD/BRL"),
    Instrument("EURBRL=X", "fx", "Euro em reais", "Euro in reais", "EUR/BRL"),
    Instrument("EURUSD=X", "fx", "Euro em dólares", "Euro in dollars", "EUR/USD"),
    Instrument("DX-Y.NYB", "fx", "Índice do dólar (DXY)", "US dollar index (DXY)", "DXY"),
    Instrument("JPY=X", "fx", "Dólar em ienes", "US dollar in yen", "USD/JPY"),
    Instrument(
        "^TNX",
        "rates",
        "Tesouro dos EUA, 10 anos",
        "US 10-year Treasury",
        "US10Y",
        rate=True,
    ),
    Instrument(
        "^IRX",
        "rates",
        "Tesouro dos EUA, 3 meses",
        "US 3-month Treasury",
        "US3M",
        rate=True,
    ),
    Instrument("BZ=F", "commodities", "Petróleo Brent", "Brent crude oil", "Brent"),
    Instrument("GC=F", "commodities", "Ouro", "Gold", "Gold"),
    Instrument("SI=F", "commodities", "Prata", "Silver", "Silver"),
    Instrument("HG=F", "commodities", "Cobre", "Copper", "Copper"),
    Instrument("NG=F", "commodities", "Gás natural", "Natural gas", "NatGas"),
    Instrument("ZS=F", "commodities", "Soja", "Soybeans", "Soy"),
    Instrument("BTC-USD", "crypto", "Bitcoin", "Bitcoin", "BTC"),
    Instrument("ETH-USD", "crypto", "Ethereum", "Ethereum", "ETH"),
    Instrument("SOL-USD", "crypto", "Solana", "Solana", "SOL"),
    _stock("PETR4.SA", "PETR4", "BR", "Petrobras"),
    _stock("VALE3.SA", "VALE3", "BR", "Vale"),
    _stock("ITUB4.SA", "ITUB4", "BR", "Itaú Unibanco"),
    _stock("BBDC4.SA", "BBDC4", "BR", "Bradesco"),
    _stock("BBAS3.SA", "BBAS3", "BR", "Banco do Brasil"),
    _stock("ABEV3.SA", "ABEV3", "BR", "Ambev"),
    _stock("WEGE3.SA", "WEGE3", "BR", "WEG"),
    _stock("B3SA3.SA", "B3SA3", "BR", "B3"),
    _stock("SUZB3.SA", "SUZB3", "BR", "Suzano"),
    _stock("PRIO3.SA", "PRIO3", "BR", "PRIO"),
    _stock("RENT3.SA", "RENT3", "BR", "Localiza"),
    _stock("MGLU3.SA", "MGLU3", "BR", "Magazine Luiza"),
    _stock("BPAC11.SA", "BPAC11", "BR", "BTG Pactual"),
    _stock("AAPL", "AAPL", "US", "Apple"),
    _stock("MSFT", "MSFT", "US", "Microsoft"),
    _stock("NVDA", "NVDA", "US", "NVIDIA"),
    _stock("AMZN", "AMZN", "US", "Amazon"),
    _stock("GOOGL", "GOOGL", "US", "Alphabet"),
    _stock("META", "META", "US", "Meta"),
    _stock("TSLA", "TSLA", "US", "Tesla"),
    _stock("BRK-B", "BRK.B", "US", "Berkshire Hathaway"),
    _stock("JPM", "JPM", "US", "JPMorgan"),
    _stock("AVGO", "AVGO", "US", "Broadcom"),
    _stock("LLY", "LLY", "US", "Eli Lilly"),
    _stock("XOM", "XOM", "US", "ExxonMobil"),
    _stock("V", "V", "US", "Visa"),
    _stock("NFLX", "NFLX", "US", "Netflix"),
    _stock("ASML.AS", "ASML", "EU", "ASML"),
    _stock("SAP.DE", "SAP", "EU", "SAP"),
    _stock("MC.PA", "MC", "EU", "LVMH"),
    _stock("NOVO-B.CO", "NOVO B", "EU", "Novo Nordisk"),
    _stock("NESN.SW", "NESN", "EU", "Nestlé"),
    _stock("SIE.DE", "SIE", "EU", "Siemens"),
    _stock("AIR.PA", "AIR", "EU", "Airbus"),
    _stock("TTE.PA", "TTE", "EU", "TotalEnergies"),
    _stock("SAN.MC", "SAN", "EU", "Banco Santander"),
    _stock("SHEL.L", "SHEL", "EU", "Shell"),
    _stock("AZN.L", "AZN", "EU", "AstraZeneca"),
    _stock("RMS.PA", "RMS", "EU", "Hermès"),
)
PERIODS = ("1D", "1W", "1M", "YTD", "12M")


def overview_symbols() -> list[str]:
    """Every symbol to download."""
    return [i.symbol for i in UNIVERSE]


def _num(x: float, digits: int = 6) -> float | None:
    return round(x, digits) if math.isfinite(x) else None


def _sig(x: float, digits: int = 6) -> float:
    """Round to ``digits`` significant figures (keeps the JSON small)."""
    if x == 0 or not math.isfinite(x):
        return 0.0
    return round(x, digits - 1 - math.floor(math.log10(abs(x))))


def base_position(dates: pd.DatetimeIndex, period: str) -> int | None:
    """Position of the price each period's change is measured from, or None if too short.

    1D is the previous observation; the others are the last observation on or before the same
    calendar day a week, a month or a year ago, or the last one of the previous year (YTD).
    Calendar dates work for every market, including crypto, which trades at weekends.
    """
    n = len(dates)
    if n < 2:
        return None
    last = pd.Timestamp(dates[-1])
    if period == "1D":
        return n - 2
    if period == "YTD":
        anchor = pd.Timestamp(year=last.year - 1, month=12, day=31)
    else:
        offsets = {
            "1W": pd.DateOffset(weeks=1),
            "1M": pd.DateOffset(months=1),
            "12M": pd.DateOffset(years=1),
        }
        anchor = last - offsets[period]
    k = int(dates.searchsorted(anchor, side="right")) - 1
    if k < 0 or k >= n - 1:
        return None
    # A gap of more than a week before the anchor means the history does not reach it.
    if (anchor - pd.Timestamp(dates[k])).days > 7:
        return None
    return k


def _steps(prices: pd.Series, rate: bool) -> pd.Series:
    """Daily changes: returns for prices, point changes (as fractions) for rates."""
    if rate:
        return (prices.diff() / 100).dropna()
    return prices.pct_change().dropna()


def _weekly(prices: pd.Series, rate: bool) -> pd.Series:
    week = prices.resample("W-FRI").last().dropna()
    return _steps(week, rate)


def market_overview(
    series: dict[str, Series], portfolio_value: pd.Series | None = None
) -> dict[str, Any] | None:
    """Measure the change, unusualness and link to the portfolio of every downloaded series.

    Parameters
    ----------
    series : dict
        Symbol to downloaded :class:`quant.data.market.Series`, as
        :func:`quant.data.market.fetch_series` returns.
    portfolio_value : pd.Series, optional
        Daily portfolio value in the base currency, for the correlation column.

    Returns
    -------
    dict or None
        JSON-ready data for the report's market tab, or None when nothing usable came back.

    """
    usable = {
        s: v.prices.dropna().astype(float)
        for s, v in series.items()
        if len(v.prices.dropna()) >= 30
    }
    if not usable:
        return None
    newest = max(pd.Timestamp(p.index[-1]) for p in usable.values())
    portfolio_weekly = (
        _weekly(portfolio_value.dropna(), False).iloc[-52:]
        if portfolio_value is not None and len(portfolio_value.dropna()) > 60
        else None
    )
    items: list[dict[str, Any]] = []
    for inst in UNIVERSE:
        prices = usable.get(inst.symbol)
        if prices is None or (newest - pd.Timestamp(prices.index[-1])).days > STALE_DAYS:
            continue
        dates = pd.DatetimeIndex(prices.index)
        steps = _steps(prices, inst.rate)
        history = steps.iloc[-VOL_DAYS - 5 : -5]
        sd = float(history.std()) if len(history) >= 60 else math.nan
        last = float(prices.iloc[-1])
        change: dict[str, float | None] = {}
        z: dict[str, float | None] = {}
        for period in PERIODS:
            k = base_position(dates, period)
            if k is None:
                change[period] = z[period] = None
                continue
            base = float(prices.iloc[k])
            move = (last - base) / 100 if inst.rate else last / base - 1
            days = len(prices) - 1 - k
            change[period] = _num(move)
            z[period] = _num(move / (sd * math.sqrt(days)), 2) if sd > 0 else None
        corr = None
        if portfolio_weekly is not None:
            joined = pd.concat(
                [portfolio_weekly, _weekly(prices, inst.rate)], axis=1, join="inner"
            ).dropna()
            if len(joined) >= 26 and float(joined.iloc[:, 1].std()) > 0:
                corr = _num(float(np.corrcoef(joined.iloc[:, 0], joined.iloc[:, 1])[0, 1]), 3)
        spark = prices[prices.index >= newest - pd.Timedelta(days=SPARK_DAYS)]
        # Daily for the last three months, weekly before: enough for a small line.
        recent = spark.index >= newest - pd.Timedelta(days=95)
        older = spark[~recent]
        spark = pd.concat([older.iloc[::5], spark[recent]]) if len(older) else spark
        first = pd.Timestamp(spark.index[0])
        name = series[inst.symbol].name
        items.append(
            {
                "symbol": inst.symbol,
                "short": inst.short or inst.symbol,
                "group": inst.group,
                "region": inst.region,
                "rate": inst.rate,
                "pt": inst.pt or name or inst.short,
                "en": inst.en or name or inst.short,
                "currency": series[inst.symbol].currency,
                "last": _sig(last),
                "lastDate": f"{dates[-1]:%Y-%m-%d}",
                "fromCache": series[inst.symbol].from_cache,
                "change": change,
                "z": z,
                "vol": _num(sd * math.sqrt(252), 4) if sd > 0 else None,
                "corr": corr,
                "spark": {
                    "start": f"{first:%Y-%m-%d}",
                    "t": [int((pd.Timestamp(d) - first).days) for d in spark.index],
                    "v": [_sig(float(v), 5) for v in spark],
                },
            }
        )
    if not items:
        return None
    return {
        "asOf": f"{newest:%Y-%m-%d}",
        "periods": list(PERIODS),
        "unusualZ": UNUSUAL_Z,
        "items": items,
    }
