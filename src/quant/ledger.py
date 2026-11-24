"""Transaction log: what the portfolio returned, and what your money returned.

The rest of the report holds today's quantities over the whole history, which describes
the portfolio as it is. With a log of every buy and sell the questions change:

- Time-weighted return (TWR): the return of the holdings actually held each day, chained
  across days. Each trade is valued at that day's close, so ``r_t`` is the return of the
  previous day's holdings: deposits and withdrawals do not move it. This is the figure fund
  managers report (GIPS), because it judges the investments, not the timing of the money.
- Money-weighted return (MWR): the XIRR of the actual cash paid and received, with today's
  value as the final flow. It rewards or punishes the timing of contributions.
- Realised and unrealised gains, by the average-cost method: a sale realises the
  difference between its proceeds and the average cost of the units sold.

All amounts are converted to the base currency at the rate of the trade date. Fees are part
of the cost of a purchase and are deducted from the proceeds of a sale.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from quant.performance import xirr

SIDES = ("buy", "sell")
COLUMNS = ("date", "symbol", "side", "quantity", "price")
TOLERANCE = 1e-6  # relative difference allowed between the log's units and the holdings


def parse_transactions(raw: pd.DataFrame) -> pd.DataFrame:
    """Validate a transaction table and return it sorted by date.

    Parameters
    ----------
    raw : pd.DataFrame
        Columns ``date`` (YYYY-MM-DD), ``symbol`` (the ticker, as in the holdings),
        ``side`` (``buy`` or ``sell``), ``quantity`` and ``price`` (per unit, in the asset's
        currency), and optionally ``fee`` (in the asset's currency). Values may be strings.

    Returns
    -------
    pd.DataFrame
        ``date`` (Timestamp), ``symbol``, ``side``, ``quantity``, ``price``, ``fee``
        (floats), sorted by date; trades on the same day keep their order in the file.

    Raises
    ------
    ValueError
        If a column is missing, there are no rows, or a value is invalid.

    """
    missing = [c for c in COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    if raw.empty:
        raise ValueError("no transactions in the log")
    text = pd.DataFrame({c: raw[c].astype(str).str.strip() for c in raw.columns})
    dates = pd.to_datetime(text["date"], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any():
        raise ValueError("every date must be YYYY-MM-DD")
    side = text["side"].str.lower()
    if not side.isin(SIDES).all():
        raise ValueError("side must be buy or sell")
    symbol = text["symbol"]
    if (symbol == "").any() or (symbol == "nan").any():
        raise ValueError("every row needs a symbol")
    numbers: dict[str, pd.Series] = {}
    for column in ("quantity", "price", "fee"):
        values = text[column] if column in text.columns else pd.Series("0", index=text.index)
        values = values.replace({"": "0", "nan": "0"}) if column == "fee" else values
        parsed = pd.to_numeric(values, errors="coerce")
        if parsed.isna().any() or not np.isfinite(parsed.to_numpy(dtype=float)).all():
            raise ValueError(f"every {column} must be a number")
        numbers[column] = parsed.astype(float)
    if (numbers["quantity"] <= 0).any() or (numbers["price"] <= 0).any():
        raise ValueError("quantity and price must be above zero")
    if (numbers["fee"] < 0).any():
        raise ValueError("a fee cannot be negative")
    out = pd.DataFrame(
        {
            "date": dates,
            "symbol": symbol,
            "side": side,
            "quantity": numbers["quantity"],
            "price": numbers["price"],
            "fee": numbers["fee"],
        }
    )
    return out.sort_values("date", kind="stable").reset_index(drop=True)


def load_transactions(path: str | Path) -> pd.DataFrame:
    """Read and validate a transaction CSV; see :func:`parse_transactions`."""
    return parse_transactions(pd.read_csv(path, dtype=str, keep_default_na=False))


def net_units(trades: pd.DataFrame) -> dict[str, float]:
    """Units held at the end of the log, by symbol.

    Raises
    ------
    ValueError
        If a sale would take a position below zero at any point.

    """
    held: dict[str, float] = {}
    for symbol, side, quantity in zip(
        trades["symbol"], trades["side"], trades["quantity"], strict=True
    ):
        units = held.get(str(symbol), 0.0) + (float(quantity) if side == "buy" else -quantity)
        if units < -TOLERANCE * max(1.0, float(quantity)):
            raise ValueError(f"{symbol}: sells more units than were bought")
        held[str(symbol)] = max(units, 0.0)
    return held


def check_against_holdings(trades: pd.DataFrame, holdings: pd.DataFrame) -> list[str]:
    """Differences between the log's final units and the holdings, one line per asset.

    Every non-cash holding must be in the log with the same units, and the log may only
    hold assets that are in the portfolio. An empty list means they agree.
    """
    held = net_units(trades)
    instruments = holdings[holdings["source"] != "cash"]
    problems: list[str] = []
    for symbol, quantity in zip(instruments["symbol"], instruments["quantity"], strict=True):
        logged = held.pop(str(symbol), 0.0)
        if abs(logged - float(quantity)) > TOLERANCE * max(1.0, float(quantity)):
            problems.append(f"{symbol}: log {logged:g}, portfolio {float(quantity):g}")
    problems.extend(f"{s}: log {u:g}, portfolio 0" for s, u in held.items() if u > TOLERANCE)
    return problems


@dataclass(frozen=True)
class AssetLedger:
    """One asset's position by the average-cost method, in the base currency."""

    asset: str
    units: float
    cost_basis: float  # what the units still held cost, fees included
    realised: float  # gains already taken by selling
    bought: float  # cash paid for all purchases
    sold: float  # cash received from all sales


def average_cost(trades: pd.DataFrame) -> dict[str, AssetLedger]:
    """Average-cost positions from trades with base-currency ``amount`` and ``fee_base``.

    Each purchase adds its cost plus fee to the basis; each sale takes out the average cost
    of the units sold and realises proceeds minus fee minus that cost.
    """
    state: dict[str, list[float]] = {}  # asset -> [units, basis, realised, bought, sold]
    for asset, side, quantity, amount, fee in zip(
        trades["asset"],
        trades["side"],
        trades["quantity"],
        trades["amount"],
        trades["fee_base"],
        strict=True,
    ):
        s = state.setdefault(str(asset), [0.0, 0.0, 0.0, 0.0, 0.0])
        q, cash, cost = float(quantity), float(amount), float(fee)
        if side == "buy":
            s[0] += q
            s[1] += cash + cost
            s[3] += cash + cost
        else:
            average = s[1] / s[0] if s[0] > 0 else 0.0
            taken = average * min(q, s[0])
            s[2] += cash - cost - taken
            s[1] -= taken
            s[0] = max(0.0, s[0] - q)
            s[4] += cash - cost
    return {
        a: AssetLedger(a, s[0], s[1] if s[0] > 0 else 0.0, s[2], s[3], s[4])
        for a, s in state.items()
    }


def units_over_time(trades: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Units of each asset held at each date's close (trades count from their own date)."""
    signed = trades.assign(
        units=trades["quantity"].where(trades["side"] == "buy", -trades["quantity"])
    )
    daily = signed.pivot_table(index="date", columns="asset", values="units", aggfunc="sum")
    # Trades before the first date are part of the opening position.
    opening = daily[daily.index < dates[0]].sum()
    within = daily[daily.index >= dates[0]]
    # A trade on a non-business day counts from the next date in the calendar.
    position = dates.searchsorted(pd.DatetimeIndex(within.index))
    keep = position < len(dates)
    moved = within[keep].groupby(dates[position[keep]]).sum()
    changes = moved.reindex(dates, fill_value=0.0)
    changes.iloc[0] += opening.reindex(changes.columns, fill_value=0.0)
    return changes.cumsum().clip(lower=0.0)


def time_weighted_returns(prices: pd.DataFrame, units: pd.DataFrame) -> pd.Series:
    """Daily time-weighted returns: the return of the previous close's holdings.

    ``r_t = sum_a u_{t-1,a} (P_{t,a} - P_{t-1,a}) / sum_a u_{t-1,a} P_{t-1,a}``. Trades are
    valued at the day's close, so money moving in or out never shows as a return. A day
    after holding nothing has no return (NaN).
    """
    held = units.shift(1).fillna(0.0)
    before = (held * prices.shift(1)).sum(axis=1)
    gain = (held * (prices - prices.shift(1))).sum(axis=1)
    return (gain / before.where(before > 0)).iloc[1:]


def analyse_ledger(
    trades: pd.DataFrame,
    holdings: pd.DataFrame,
    base_prices: pd.DataFrame,
    fx_rates: pd.DataFrame,
    base: str = "EUR",
) -> dict[str, object]:
    """Compute the returns and gains of the logged trades against today's value.

    Parameters
    ----------
    trades : pd.DataFrame
        Output of :func:`parse_transactions`; units must match ``holdings``
        (see :func:`check_against_holdings`).
    holdings : pd.DataFrame
        The portfolio (index = asset label; ``symbol``, ``currency``, ``source``).
    base_prices : pd.DataFrame
        Daily prices in the base currency, one column per asset label.
    fx_rates : pd.DataFrame
        Base-currency value of one unit of each currency, by date.
    base : str
        Base currency code.

    Returns
    -------
    dict
        ``dates``, ``value`` and ``invested`` (cumulative net cash in) series, ``twr`` (daily
        returns), totals and the per-asset average-cost positions.

    """
    instruments = holdings[holdings["source"] != "cash"]
    label = {str(s): str(a) for a, s in zip(instruments.index, instruments["symbol"], strict=True)}
    currency = {
        str(a): str(c) for a, c in zip(instruments.index, instruments["currency"], strict=True)
    }
    t = trades[trades["symbol"].isin(label)].copy()
    t["asset"] = t["symbol"].map(label)

    def rate(asset: str, when: pd.Timestamp) -> float:
        ccy = currency[asset]
        if ccy == base:
            return 1.0
        history = fx_rates[ccy].dropna()
        before = history[history.index <= when]
        # Older than the rate history: its first rate (the report flags the log's start).
        return float(before.iloc[-1]) if not before.empty else float(history.iloc[0])

    rates = [rate(a, d) for a, d in zip(t["asset"], t["date"], strict=True)]
    t["amount"] = t["quantity"] * t["price"] * rates
    t["fee_base"] = t["fee"] * rates
    dates = pd.DatetimeIndex(base_prices.index)
    assets = sorted(set(t["asset"]))
    prices = base_prices[assets]
    units = units_over_time(t, dates).reindex(columns=assets, fill_value=0.0)
    value = (units * prices).sum(axis=1)
    cash_in = (t["amount"] + t["fee_base"]).where(
        t["side"] == "buy", -(t["amount"] - t["fee_base"])
    )
    flows = pd.Series(cash_in.to_numpy(dtype=float), index=pd.DatetimeIndex(t["date"]))
    flows = flows.groupby(level=0).sum()
    invested = flows.cumsum().reindex(dates, method="ffill").fillna(0.0)
    twr = time_weighted_returns(prices, units)
    chain = (1 + twr.fillna(0.0)).cumprod()
    started = value[value > 0].index
    years = (dates[-1] - started[0]).days / 365.25 if len(started) else 0.0
    total = float(chain.iloc[-1] - 1) if len(chain) else 0.0
    end = float(value.iloc[-1])
    dated = [
        (pd.Timestamp(d), -float(c))
        for d, c in zip(pd.DatetimeIndex(flows.index), flows.to_numpy(dtype=float), strict=True)
    ]
    mwr = xirr([*dated, (pd.Timestamp(dates[-1]), end)]) if dated else None
    positions = average_cost(t)
    realised = sum(p.realised for p in positions.values())
    basis = sum(p.cost_basis for p in positions.values())
    return {
        "dates": dates,
        "value": value,
        "invested": invested,
        "twr": twr,
        "twrTotal": total,
        "twrAnnual": (1 + total) ** (1 / years) - 1 if years >= 1 and total > -1 else None,
        "mwr": mwr,
        "netInvested": float(flows.sum()),
        "end": end,
        "realised": realised,
        "unrealised": end - basis,
        "first": pd.Timestamp(t["date"].min()),
        "trades": len(t),
        "beforeHistory": bool(t["date"].min() < dates[0]),
        "positions": positions,
        "endValues": {str(a): float(v) for a, v in (units.iloc[-1] * prices.iloc[-1]).items()},
        "years": years,
    }
