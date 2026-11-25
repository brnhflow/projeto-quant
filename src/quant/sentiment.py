"""A fear and greed gauge for the US stock market, built from public prices with a stated method.

The best-known gauge (CNN's) has no public data feed, so this one is rebuilt from the same kind
of evidence, each part from a series anyone can download:

| Part | Measure | Greed when |
|---|---|---|
| Momentum | S&P 500 over its 125-day average, minus 1 | above |
| Strength | S&P 500 against its 52-week high | close to the high |
| Volatility | VIX over its 50-day average, minus 1 | low |
| Safe haven | 20-day return of stocks minus 7-10 year Treasuries (IEF) | stocks ahead |
| Junk bonds | 20-day return of high-yield (HYG) minus Treasuries (IEF) | junk ahead |

Each part is scored 0-100 as the percentile of today's value among the previous two years of
that same measure (inverted for volatility), so a score of 80 means "greedier than 80% of the
last two years". The gauge is the average of the parts available. Being a rank, it says where
sentiment stands against recent history, not whether the market will rise or fall: at extremes
it has been read as a contrarian signal, but that is a hypothesis, not something tested here.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from quant.data.market import Series

SYMBOLS = ("^GSPC", "^VIX", "HYG", "IEF")
LOOKBACK = 504  # two years of trading days for the percentile
HISTORY = 260  # days of gauge history to show
BANDS = ((25, "extreme_fear"), (45, "fear"), (55, "neutral"), (75, "greed"), (101, "extreme_greed"))


def label(score: float) -> str:
    """Band of a 0-100 score: extreme_fear, fear, neutral, greed or extreme_greed."""
    return next(name for top, name in BANDS if score < top)


def _rank(series: pd.Series) -> pd.Series:
    """Percentile (0-100) of each value among the previous :data:`LOOKBACK` values and itself."""
    return series.rolling(LOOKBACK, min_periods=LOOKBACK // 2).rank(pct=True) * 100


def components(prices: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """Each part's raw daily measure, as described in the module docstring."""
    out: dict[str, pd.Series] = {}
    spx = prices.get("^GSPC")
    vix = prices.get("^VIX")
    ief = prices.get("IEF")
    hyg = prices.get("HYG")
    if spx is not None:
        out["momentum"] = spx / spx.rolling(125).mean() - 1
        out["strength"] = spx / spx.rolling(252, min_periods=126).max() - 1
    if vix is not None:
        out["volatility"] = vix / vix.rolling(50).mean() - 1
    if spx is not None and ief is not None:
        joined = pd.concat([spx, ief], axis=1, join="inner")
        out["safe_haven"] = joined.iloc[:, 0].pct_change(20) - joined.iloc[:, 1].pct_change(20)
    if hyg is not None and ief is not None:
        joined = pd.concat([hyg, ief], axis=1, join="inner")
        out["junk"] = joined.iloc[:, 0].pct_change(20) - joined.iloc[:, 1].pct_change(20)
    return {k: v.dropna() for k, v in out.items() if not v.dropna().empty}


def _num(x: float, digits: int = 2) -> float | None:
    return round(x, digits) if math.isfinite(x) else None


def fear_greed(series: dict[str, Series]) -> dict[str, Any] | None:
    """Gauge today, its parts, and its daily history; None without enough data."""
    prices = {s: v.prices.dropna().astype(float) for s, v in series.items() if s in SYMBOLS}
    raw = components(prices)
    scores = {
        k: (100 - _rank(v) if k == "volatility" else _rank(v)).dropna() for k, v in raw.items()
    }
    scores = {k: v for k, v in scores.items() if not v.empty}
    if len(scores) < 3:
        return None
    table = pd.concat(scores, axis=1, sort=True).ffill(limit=3)
    gauge = table.mean(axis=1, skipna=True)[table.count(axis=1) >= 3].dropna()
    if gauge.empty:
        return None
    last = pd.Timestamp(gauge.index[-1])

    def ago(offset: pd.DateOffset) -> float | None:
        k = int(gauge.index.searchsorted(last - offset, side="right")) - 1
        return None if k < 0 else _num(float(gauge.iloc[k]), 1)

    history = gauge.iloc[-HISTORY:]
    first = pd.Timestamp(history.index[0])
    score = float(gauge.iloc[-1])
    return {
        "date": f"{last:%Y-%m-%d}",
        "score": _num(score, 1),
        "label": label(score),
        "week": ago(pd.DateOffset(weeks=1)),
        "month": ago(pd.DateOffset(months=1)),
        "year": ago(pd.DateOffset(years=1)),
        "parts": [
            {
                "key": k,
                "score": _num(float(table[k].iloc[-1]), 1) if k in table else None,
                "value": _num(float(raw[k].iloc[-1]), 4),
            }
            for k in ("momentum", "strength", "volatility", "safe_haven", "junk")
            if k in raw
        ],
        "history": {
            "start": f"{first:%Y-%m-%d}",
            "t": [int((pd.Timestamp(d) - first).days) for d in history.index],
            "v": [round(float(v), 1) for v in history],
        },
    }


def crypto_fear(series: pd.Series | None) -> dict[str, Any] | None:
    """Summarise the crypto index: today, a week, a month and a year ago, and its history."""
    if series is None or series.dropna().empty:
        return None
    values = series.dropna()
    last = pd.Timestamp(values.index[-1])

    def ago(offset: pd.DateOffset) -> float | None:
        k = int(values.index.searchsorted(last - offset, side="right")) - 1
        return (
            None
            if k < 0 or (last - offset - pd.Timestamp(values.index[k])).days > 3
            else float(values.iloc[k])
        )

    history = values[values.index >= last - pd.Timedelta(days=HISTORY * 7 // 5)]
    first = pd.Timestamp(history.index[0])
    score = float(values.iloc[-1])
    return {
        "date": f"{last:%Y-%m-%d}",
        "score": score,
        "label": label(score),
        "week": ago(pd.DateOffset(weeks=1)),
        "month": ago(pd.DateOffset(months=1)),
        "year": ago(pd.DateOffset(years=1)),
        "history": {
            "start": f"{first:%Y-%m-%d}",
            "t": [int((pd.Timestamp(d) - first).days) for d in history.index],
            "v": [float(v) for v in history],
        },
    }
