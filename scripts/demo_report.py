"""Build the portfolio report for a small portfolio on synthetic market data (offline).

Run: uv run python scripts/demo_report.py  ->  reports/demo.html

Prices and FX rates are seeded random walks, so the numbers describe no real market; the
point is to run the real pipeline end to end and see the report.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd

from quant.report import build_report

ROOT = Path(__file__).parents[1]
OUT = ROOT / "reports" / "demo.html"


def synthetic_market(seed: int = 14) -> tuple[pd.DataFrame, pd.DataFrame, pd.DatetimeIndex]:
    """Correlated prices on each market's own calendar, ECB-like FX days, and the calendar.

    Daily log-returns follow a small factor model, so assets move together the way real ones
    do: a global equity factor, a Brazil factor (stocks and the real), and a crypto factor.
    Stocks and FX do not move on weekends; bitcoin does.
    """
    rng = np.random.default_rng(seed)
    days = pd.date_range("2024-11-22", "2026-11-20", freq="D")
    weekday = (days.day_of_week < 5).astype(float)
    n = len(days)

    def noise(vol: float) -> npt.NDArray[np.float64]:
        return rng.normal(0.0, vol, n)

    world = (0.0003 + noise(0.008)) * weekday
    brazil = noise(0.010) * weekday
    crypto = 0.0002 + noise(0.026)
    log_returns = {
        "PETR4": 0.9 * world + 1.0 * brazil + noise(0.012) * weekday,
        "VALE3": 1.0 * world + 0.8 * brazil + noise(0.011) * weekday,
        "ASML": 1.3 * world + noise(0.015) * weekday,
        "IWDA": 1.0 * world + noise(0.002) * weekday,
        "BTC": 0.6 * world + crypto,
        "BRL": 0.35 * brazil + noise(0.004) * weekday,  # euros per real: falls with Brazil
        "USD": noise(0.004) * weekday,
    }
    start = {"PETR4": 36.0, "VALE3": 58.0, "ASML": 640.0, "IWDA": 88.0, "BTC": 85_000.0}
    start_fx = {"BRL": 0.165, "USD": 0.93}
    levels = pd.DataFrame(
        {k: (start | start_fx)[k] * np.exp(r.cumsum()) for k, r in log_returns.items()},
        index=days,
    )

    weekdays = days[days.day_of_week < 5]
    carnival = pd.to_datetime(["2025-03-03", "2025-03-04", "2026-02-16", "2026-02-17"])
    b3_days = weekdays.difference(carnival)
    prices = pd.concat(
        {
            "PETR4": levels["PETR4"].reindex(b3_days),
            "VALE3": levels["VALE3"].reindex(b3_days),
            "ASML": levels["ASML"].reindex(weekdays),
            "IWDA": levels["IWDA"].reindex(weekdays),
            "BTC": levels["BTC"],
        },
        axis="columns",
        sort=True,
    )
    fx = levels[["BRL", "USD"]].reindex(weekdays)
    return prices, fx, pd.DatetimeIndex(weekdays)


if __name__ == "__main__":
    holdings = pd.DataFrame(
        {
            "quantity": [200.0, 150.0, 4.0, 60.0, 0.05],
            "currency": ["BRL", "BRL", "EUR", "EUR", "USD"],
            "source": "yahoo",
            "symbol": ["PETR4.SA", "VALE3.SA", "ASML.AS", "IWDA.AS", "BTC-USD"],
        },
        index=pd.Index(["PETR4", "VALE3", "ASML", "IWDA", "BTC"], name="asset"),
    )
    prices, fx, calendar = synthetic_market()
    page = build_report(holdings, prices, fx, calendar, title="Carteira de exemplo", synthetic=True)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT}")
