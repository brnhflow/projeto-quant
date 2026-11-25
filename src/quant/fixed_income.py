"""Fixed income around the world: yield curves, policy rates and Brazil's Tesouro Direto.

For each country the curve is shown today, a month ago and a year ago (the last observation on
or before each date), with three numbers people watch:

- the 2- and 10-year yields, interpolated linearly on the curve when the source has no exact
  point;
- the change in the 10-year yield, in percentage points;
- the slope, 10-year minus 2-year. Negative (an inverted curve) has preceded most US recessions
  since the 1970s (Estrella and Mishkin, 1998), though with long and variable lags.

Brazil's curve comes from the bonds the Treasury sells to individuals: the fixed-rate
(Prefixado) bonds give the nominal curve and the inflation-linked (IPCA+) bonds the real one.
Their gap at the same maturity is the inflation the market prices in (the breakeven):
(1 + nominal) / (1 + real) - 1. It also carries an inflation risk premium, so it is an upper
estimate of expected inflation rather than a forecast.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from quant.data.rates import RatesData

NOMINAL = ("Tesouro Prefixado", "Tesouro Prefixado com Juros Semestrais")
REAL = ("Tesouro IPCA+", "Tesouro IPCA+ com Juros Semestrais")
ORDER = ("BR", "US", "EA", "UK", "JP")
Points = list[tuple[float, float]]


def _num(x: float | None, digits: int = 4) -> float | None:
    return None if x is None or not math.isfinite(x) else round(x, digits)


def at_or_before(
    index: pd.DatetimeIndex, when: pd.Timestamp, tolerance_days: int = 10
) -> int | None:
    """Position of the last date on or before ``when``, or None if none is close enough."""
    k = int(index.searchsorted(when, side="right")) - 1
    if k < 0 or (when - pd.Timestamp(index[k])).days > tolerance_days:
        return None
    return k


def interpolate(points: Points, years: float) -> float | None:
    """Yield at ``years`` by linear interpolation; None outside the curve."""
    if not points:
        return None
    xs = [p[0] for p in points]
    if not xs[0] - 1e-9 <= years <= xs[-1] + 1e-9:
        return None
    return float(np.interp(years, xs, [p[1] for p in points]))


def _row_points(row: pd.Series) -> Points:
    clean = row.dropna()
    return sorted((float(str(m)), float(v)) for m, v in clean.items())


def _tesouro_points(rows: pd.DataFrame, kinds: tuple[str, ...], min_years: float = 0.25) -> Points:
    chosen = rows[rows["kind"].isin(kinds)]
    years = (chosen["maturity"] - chosen["date"]).dt.days / 365.25
    pairs: dict[float, list[float]] = {}
    for y, r in zip(years, chosen["rate"], strict=True):
        if y > min_years:  # a bond about to mature quotes an erratic rate
            pairs.setdefault(round(float(y), 2), []).append(float(r))
    return [(y, sum(v) / len(v)) for y, v in sorted(pairs.items())]


def _bracket_gap(points: Points, years: float) -> float:
    """Distance between the two curve points around ``years`` (0 on an exact point)."""
    xs = [p[0] for p in points]
    if any(abs(x - years) < 1e-9 for x in xs):
        return 0.0
    below = max((x for x in xs if x < years), default=-math.inf)
    above = min((x for x in xs if x > years), default=math.inf)
    return above - below


def breakeven(
    rows: pd.DataFrame,
    years: float,
    *,
    min_years: float = 0.25,
    max_gap: float = math.inf,
) -> float | None:
    """Inflation priced in at ``years`` (% a year) from one day's Tesouro Direto rows.

    The Prefixado and IPCA+ curves are each interpolated linearly at ``years``, and the
    breakeven is (1 + nominal) / (1 + real) - 1. Bonds with ``min_years`` or less to maturity
    are left out, and a curve whose two points around ``years`` are more than ``max_gap`` years
    apart counts as not reaching it. None when either curve does not reach ``years``.
    """
    curves = [_tesouro_points(rows, kinds, min_years) for kinds in (NOMINAL, REAL)]
    values = [interpolate(points, years) for points in curves]
    nominal, real = values
    if nominal is None or real is None:
        return None
    if any(_bracket_gap(points, years) > max_gap for points in curves):
        return None
    return ((1 + nominal / 100) / (1 + real / 100) - 1) * 100


def _snapshot(date: pd.Timestamp, points: Points) -> dict[str, Any]:
    return {"date": f"{date:%Y-%m-%d}", "points": [[_num(m, 3), _num(v)] for m, v in points]}


def _country(
    snapshots: dict[str, tuple[pd.Timestamp, Points] | None],
    policy: pd.Series | None,
    today: pd.Timestamp,
) -> dict[str, Any] | None:
    now = snapshots.get("today")
    if now is None or len(now[1]) < 2:
        return None
    pts = now[1]
    y2, y10 = interpolate(pts, 2), interpolate(pts, 10)

    def ten(key: str) -> float | None:
        snap = snapshots.get(key)
        before = interpolate(snap[1], 10) if snap else None
        return None if before is None or y10 is None else y10 - before

    rate = None
    if policy is not None and not policy.dropna().empty:
        series = policy.dropna()
        k_year = at_or_before(pd.DatetimeIndex(series.index), today - pd.DateOffset(years=1), 40)
        rate = {
            "value": _num(float(series.iloc[-1])),
            "date": f"{pd.Timestamp(series.index[-1]):%Y-%m-%d}",
            "year": None if k_year is None else _num(float(series.iloc[k_year])),
        }
    return {
        "curve": {k: (None if v is None else _snapshot(v[0], v[1])) for k, v in snapshots.items()},
        "policy": rate,
        "y2": _num(y2),
        "y10": _num(y10),
        "d10Month": _num(ten("month")),
        "d10Year": _num(ten("year")),
        "slope": _num(y10 - y2) if y10 is not None and y2 is not None else None,
    }


def _anchors(last: pd.Timestamp) -> dict[str, pd.Timestamp]:
    return {
        "today": last,
        "month": last - pd.DateOffset(months=1),
        "year": last - pd.DateOffset(years=1),
    }


def _brazil(rates: RatesData) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Brazil's curve from the Prefixado bonds, and the Tesouro Direto table."""
    table = rates.tesouro
    if table is None or table.empty:
        return None, None
    dates = pd.DatetimeIndex(sorted(table["date"].unique()))
    last = pd.Timestamp(dates[-1])
    snaps: dict[str, tuple[pd.Timestamp, Points] | None] = {}
    rows_at: dict[str, pd.DataFrame] = {}
    for key, when in _anchors(last).items():
        k = at_or_before(dates, when)
        if k is None:
            snaps[key] = None
            continue
        day = pd.Timestamp(dates[k])
        rows_at[key] = table[table["date"] == day]
        points = _tesouro_points(rows_at[key], NOMINAL)
        snaps[key] = (day, points) if len(points) >= 2 else None
    country = _country(snaps, rates.policy.get("BR"), last)
    if country is not None:
        cdi = rates.policy.get("BR_CDI")
        country["cdi"] = None if cdi is None or cdi.empty else _num(float(cdi.iloc[-1]))
        country["curveName"] = "prefixado"

    today_rows = rows_at.get("today", table.iloc[0:0])

    def previous(key: str, kind: str, maturity: pd.Timestamp) -> float | None:
        old = rows_at.get(key)
        if old is None:
            return None
        match = old[(old["kind"] == kind) & (old["maturity"] == maturity)]
        return None if match.empty else _num(float(match["rate"].iloc[0]))

    bonds = [
        {
            "kind": str(kind),
            "maturity": f"{pd.Timestamp(maturity):%Y-%m-%d}",
            "rate": _num(float(rate)),
            "month": previous("month", str(kind), pd.Timestamp(maturity)),
            "year": previous("year", str(kind), pd.Timestamp(maturity)),
        }
        for kind, maturity, rate in zip(
            today_rows["kind"], today_rows["maturity"], today_rows["rate"], strict=True
        )
    ]
    nominal = _tesouro_points(today_rows, NOMINAL)
    breakeven: list[dict[str, Any]] = []
    for years, real in _tesouro_points(today_rows, REAL):
        n = interpolate(nominal, years)
        if n is None:
            continue
        implied = ((1 + n / 100) / (1 + real / 100) - 1) * 100
        breakeven.append(
            {
                "years": _num(years, 2),
                "nominal": _num(n),
                "real": _num(real),
                "implied": _num(implied),
            }
        )
    tesouro = {"date": f"{last:%Y-%m-%d}", "bonds": bonds, "breakeven": breakeven}
    return country, tesouro


def fixed_income(rates: RatesData | None) -> dict[str, Any] | None:
    """JSON-ready data for the fixed income tab, or None when no source answered."""
    if rates is None:
        return None
    countries: dict[str, dict[str, Any]] = {}
    brazil, tesouro = _brazil(rates)
    if brazil is not None:
        countries["BR"] = brazil
    for key, curve in rates.curves.items():
        frame = curve.dropna(how="all")
        if frame.empty:
            continue
        index = pd.DatetimeIndex(frame.index)
        last = pd.Timestamp(index[-1])
        snaps: dict[str, tuple[pd.Timestamp, Points] | None] = {}
        for name, when in _anchors(last).items():
            k = at_or_before(index, when)
            snaps[name] = (
                None if k is None else (pd.Timestamp(index[k]), _row_points(frame.iloc[k]))
            )
        country = _country(snaps, rates.policy.get(key), last)
        if country is not None:
            countries[key] = country
    if not countries and tesouro is None:
        return None
    return {
        "countries": [{"key": k, **countries[k]} for k in ORDER if k in countries],
        "tesouro": tesouro,
        "failed": rates.failed,
    }
