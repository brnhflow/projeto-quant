"""Research note: how three one-day VaR models hold up on real markets, 2008 to today.

Run: uv run python research/var_backtest.py
Writes docs/research/var-backtest-results.csv and docs/research/var-covid.svg, and prints the
tables used in docs/research/var-backtest.md. Prices come from the same sources and cache as
the report (Yahoo Finance index levels in local currency, so no exchange rate enters).

Design:
- 7 series: Ibovespa, S&P 500, Euro Stoxx 50, FTSE 100, SMI, MSCI ACWI (ETF) and Bitcoin.
- Daily simple returns on each market's own trading days.
- Every model forecasts day t from returns before t only; all three are tested on the same
  days (the first 280 returns are used to start the models).
- 95% and 99% VaR, 250-day window, tested with Kupiec (coverage), Christoffersen
  (independence) and, at 99%, the Basel zone of every rolling 250-day year.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from quant.data.market import update_market_data
from quant.pipeline import proxy_holdings
from quant.stress import HISTORY_START, PROXIES
from quant.validation import binomial_cdf, evaluate_var
from quant.var_models import ewma_var, filtered_historical_var, historical_var

ROOT = Path(__file__).parents[1]
OUT = ROOT / "docs" / "research"
WINDOW = 250
LEVELS = (0.95, 0.99)
MODELS = {"HS": historical_var, "EWMA": ewma_var, "FHS": filtered_historical_var}
NAMES = {
    "^BVSP": "Ibovespa",
    "^GSPC": "S&P 500",
    "^STOXX50E": "Euro Stoxx 50",
    "^FTSE": "FTSE 100",
    "^SSMI": "SMI",
    "ACWI": "MSCI ACWI",
    "BTC-USD": "Bitcoin",
}


def basel_years(breach: pd.Series, level: float) -> dict[str, float]:
    """Share of rolling 250-day years in each Basel zone (the regulator's view)."""
    counts = breach.astype(int).rolling(WINDOW).sum().dropna().astype(int)
    p = 1 - level
    zone = counts.map(
        lambda x: (
            "green"
            if binomial_cdf(int(x), WINDOW, p) < 0.95
            else ("yellow" if binomial_cdf(int(x), WINDOW, p) < 0.9999 else "red")
        )
    )
    return {z: float((zone == z).mean()) for z in ("green", "yellow", "red")}


def run(prices: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict[str, pd.DataFrame]]]:
    """Backtest every model on every series and level; keep the S&P 500 99% tables."""
    rows: list[dict[str, object]] = []
    kept: dict[str, dict[str, pd.DataFrame]] = {}
    for symbol in NAMES:
        if symbol not in prices.columns:
            continue
        r = prices[symbol].dropna().pct_change().dropna()
        for level in LEVELS:
            tables = {m: f(r, WINDOW, level) for m, f in MODELS.items()}
            common = tables["HS"].index
            for t in tables.values():
                common = common.intersection(t.index)
            for model, table in tables.items():
                t = table.loc[common]
                b = evaluate_var(t, level, WINDOW)
                years = basel_years(t["breach"], level)
                losses = -t.loc[t["breach"], "return"]
                rows.append(
                    {
                        "series": NAMES[symbol],
                        "level": level,
                        "model": model,
                        "start": f"{common[0]:%Y-%m-%d}",
                        "end": f"{common[-1]:%Y-%m-%d}",
                        "days": b.days,
                        "breaches": b.breaches,
                        "rate": b.breaches / b.days,
                        "kupiec_p": b.kupiec.p_value,
                        "independence_p": b.independence.p_value,
                        "conditional_p": b.conditional_p_value,
                        # How far past the VaR the breaches went, on average.
                        "excess": float((losses / t.loc[t["breach"], "var"]).mean()),
                        "red_years": years["red"],
                        "yellow_years": years["yellow"],
                    }
                )
                if symbol == "^GSPC" and level == 0.99:
                    kept.setdefault(symbol, {})[model] = t
    return pd.DataFrame(rows), kept


def summary(results: pd.DataFrame) -> pd.DataFrame:
    """Per model and level: how many of the series pass each test at 5%."""
    g = results.groupby(["level", "model"], sort=False)
    return pd.DataFrame(
        {
            "series": g.size(),
            "mean_rate": g["rate"].mean(),
            "kupiec_pass": g["kupiec_p"].apply(lambda p: int((p >= 0.05).sum())),
            "independence_pass": g["independence_p"].apply(lambda p: int((p >= 0.05).sum())),
            "both_pass": g["conditional_p"].apply(lambda p: int((p >= 0.05).sum())),
            "red_years": g["red_years"].mean(),
            "excess": g["excess"].mean(),
        }
    )


def covid_svg(tables: dict[str, pd.DataFrame], path: Path) -> None:
    """S&P 500, February to May 2020: daily returns and each model's 99% VaR."""
    span = slice(pd.Timestamp("2020-02-03"), pd.Timestamp("2020-05-29"))
    hs = tables["HS"].loc[span]
    lines = {m: -tables[m].loc[span, "var"] for m in ("HS", "EWMA", "FHS")}
    width, height = 860, 380
    left, right, top, bottom = 56, 150, 24, 36
    lo = min(float(hs["return"].min()), *(float(v.min()) for v in lines.values())) * 1.08
    hi = float(hs["return"].max()) * 1.08
    n = len(hs)
    x = lambda i: left + (i + 0.5) * (width - left - right) / n  # noqa: E731
    y = lambda v: top + (hi - v) * (height - top - bottom) / (hi - lo)  # noqa: E731
    colors = {"HS": "#8a897f", "EWMA": "#eb6834", "FHS": "#2a78d6"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="12">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
    ]
    for tick in np.arange(np.ceil(lo * 20) / 20, hi, 0.05):
        parts.append(
            f'<line x1="{left}" x2="{width - right}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" '
            f'stroke="{"#8a897f" if abs(tick) < 1e-9 else "#e6e4dc"}" stroke-width="1"/>'
            f'<text x="{left - 8}" y="{y(tick) + 4:.1f}" text-anchor="end" fill="#55544d">'
            f"{tick * 100:.0f}%</text>"
        )
    bw = max(1.5, (width - left - right) / n * 0.6)
    for i, (ret, breach) in enumerate(zip(hs["return"], hs["breach"], strict=True)):
        top_y, h = min(y(0), y(ret)), abs(y(ret) - y(0))
        fill = "#b23a3a" if breach else "#c9c7bd"
        parts.append(
            f'<rect x="{x(i) - bw / 2:.1f}" y="{top_y:.1f}" width="{bw:.1f}" '
            f'height="{max(h, 0.6):.1f}" fill="{fill}"/>'
        )
    # End labels, pushed apart where the lines finish close together.
    label_y: dict[str, float] = {}
    for model in sorted(lines, key=lambda m: y(float(lines[m].iloc[-1]))):
        wanted = y(float(lines[model].iloc[-1])) + 4
        floor = max(label_y.values(), default=-1e9) + 15
        label_y[model] = max(wanted, floor)
    for model, series in lines.items():
        points = " ".join(f"{x(i):.1f},{y(float(v)):.1f}" for i, v in enumerate(series))
        dash = ' stroke-dasharray="5 4"' if model == "EWMA" else ""
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{colors[model]}" '
            f'stroke-width="2"{dash}/>'
        )
        label = {"HS": "Historical (HS)", "EWMA": "EWMA normal", "FHS": "Filtered HS"}[model]
        parts.append(
            f'<text x="{width - right + 8}" y="{label_y[model]:.1f}" fill="{colors[model]}" '
            f'font-weight="600">{label}</text>'
        )
    for i, d in enumerate(hs.index):
        if (d.day <= 7 and d.weekday() == 0) or i == 0:
            parts.append(
                f'<text x="{x(i):.1f}" y="{height - 12}" text-anchor="middle" fill="#55544d">'
                f"{d:%d %b}</text>"
            )
    parts.append(
        f'<text x="{left}" y="14" fill="#1c1b17" font-weight="600">S&amp;P 500, daily returns '
        "and the 99% VaR each model forecast that morning (red: loss beyond the HS forecast)"
        "</text></svg>"
    )
    path.write_bytes(("\n".join(parts) + "\n").encode("utf-8"))  # LF on every OS


def main() -> int:
    """Download or read the indices, run the study, write the CSV and the figure."""
    market = update_market_data(proxy_holdings(), HISTORY_START, ROOT / "data" / "cache")
    missing = [s for s in PROXIES if s not in market.prices.columns]
    if missing:
        print(f"warning: no data for {missing}", file=sys.stderr)
    results, kept = run(market.prices)
    OUT.mkdir(parents=True, exist_ok=True)
    results.to_csv(
        OUT / "var-backtest-results.csv", index=False, float_format="%.6g", lineterminator="\n"
    )
    if "^GSPC" in kept:
        covid_svg(kept["^GSPC"], OUT / "var-covid.svg")
    pd.set_option("display.width", 200)
    print(summary(results).round(4).to_string())
    print()
    print(results.round(4).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
