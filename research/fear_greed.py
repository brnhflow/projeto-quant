"""Research note: does a fear and greed gauge predict the S&P 500? A test, 2007 to 2026.

Run: uv run python research/fear_greed.py
Writes docs/research/fear-greed-results.csv and docs/research/fear-greed.svg, and prints the
tables used in docs/research/fear-greed.md.

Design, fixed before looking at the results:
- Gauge: quant.sentiment.gauge_series, the report's own five-part gauge. Each part is a rank
  against the previous two years only, so a day's value uses no later data.
- Target: total return of SPY (dividends included) over the next 5, 21 and 63 trading days,
  from the close on which the gauge is read.
- Test 1, predictive regressions: forward return on the gauge (per 10 points), Newey-West
  standard errors with h - 1 lags, Holm correction across the three horizons.
- Test 2, bands: forward 21-day return when the gauge is in each of the five bands the page
  uses, against all other days (regression on a dummy, Newey-West, Holm across five bands).
- Test 3, two simple rules chosen from the first day with a gauge (July 2007) to the end of
  2017 and judged from 2018 onwards: (A) hold SPY except when the gauge is above a threshold
  (avoid greed), (B) hold half the position except below a threshold, then all of it (lean
  into fear). Signal at the close, applied to the next
  day, 5 bp per unit traded, cash earns nothing. Five thresholds each, so ten trials: the best
  in-sample rule is reported out of sample with its deflated Sharpe ratio.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from quant.data.market import fetch_series
from quant.inference import Regression, holm, ols_hac
from quant.sentiment import BANDS, SYMBOLS, gauge_series
from quant.sharpe import deflated_sharpe, probabilistic_sharpe

ROOT = Path(__file__).parents[1]
OUT = ROOT / "docs" / "research"
HORIZONS = (5, 21, 63)
SPLIT = pd.Timestamp("2018-01-01")
COST = 0.0005
RULE_A = (70, 75, 80, 85, 90)
RULE_B = (10, 15, 20, 25, 30)
LABELS = {
    "extreme_fear": "Extreme fear",
    "fear": "Fear",
    "neutral": "Neutral",
    "greed": "Greed",
    "extreme_greed": "Extreme greed",
}


def load() -> tuple[pd.Series, pd.Series]:
    """Gauge and SPY total-return prices on common trading days."""
    now = pd.Timestamp.now(tz="UTC")
    series = fetch_series(
        [*SYMBOLS, "SPY"],
        pd.Timestamp("2006-01-01"),
        ROOT / "data" / "cache",
        now=now,
        adjusted=True,
        prefix="research",
    )
    prices = {s: v.prices.dropna().astype(float) for s, v in series.items()}
    gauge = gauge_series({s: p for s, p in prices.items() if s in SYMBOLS})
    spy = prices["SPY"]
    common = gauge.index.intersection(spy.index)
    return gauge.loc[common], spy.loc[common]


def band_of(value: float) -> str:
    """Name of the band a gauge value falls in."""
    return next(name for top, name in BANDS if value < top)


def stats(daily: pd.Series) -> dict[str, float]:
    """Annualised return, volatility and Sharpe (no risk-free rate), per-day moments."""
    r = daily.dropna()
    mu, sd = float(r.mean()), float(r.std())
    centred = r - mu
    skew = float((centred**3).mean() / sd**3) if sd > 0 else 0.0
    kurt = float((centred**4).mean() / sd**4) if sd > 0 else 3.0
    return {
        "ret": (1 + mu) ** 252 - 1,
        "vol": sd * math.sqrt(252),
        "sharpe": mu / sd * math.sqrt(252) if sd > 0 else 0.0,
        "sr_day": mu / sd if sd > 0 else 0.0,
        "skew": skew,
        "kurt": kurt,
        "n": float(len(r)),
    }


def rule_returns(exposure: pd.Series, spy_ret: pd.Series) -> pd.Series:
    """Daily return of holding ``exposure`` (decided at the previous close), net of costs."""
    held = exposure.shift(1).fillna(exposure.iloc[0])
    turnover = held.diff().abs().fillna(0.0)
    return held * spy_ret - turnover * COST


def main() -> int:
    """Run the three tests, print the tables and write the CSV and the chart."""
    gauge, spy = load()
    start = gauge.index[0]
    print(f"gauge from {start:%Y-%m-%d} to {gauge.index[-1]:%Y-%m-%d}: {len(gauge)} days")
    rows: list[dict[str, object]] = []

    # ---- test 1: predictive regressions
    print("\nTest 1: forward SPY return on the gauge (slope per 10 points)")
    fits = []
    for h in HORIZONS:
        forward = spy.shift(-h) / spy - 1
        fit = ols_hac(forward.to_numpy(), (gauge / 10).to_numpy(), lags=h - 1)
        fits.append((h, fit))
    adjusted = holm([f.p_slope for _, f in fits])
    for (h, fit), p_adj in zip(fits, adjusted, strict=True):
        print(
            f"  h={h:>2}d  slope {fit.slope * 100:+.3f} pp  t {fit.t_slope:+.2f}  "
            f"p {fit.p_slope:.3f}  Holm {p_adj:.3f}  R2 {fit.r2 * 100:.2f}%  n {fit.n}"
        )
        rows.append(
            {
                "test": "regression",
                "item": f"{h}d",
                "estimate": fit.slope,
                "t": fit.t_slope,
                "p": fit.p_slope,
                "p_holm": p_adj,
                "r2": fit.r2,
                "n": fit.n,
            }
        )

    # Robustness: the same regressions without the 2008-09 crisis.
    late = gauge.index >= pd.Timestamp("2010-01-01")
    print("  robustness, from 2010:", end="")
    for h in HORIZONS:
        forward = spy.shift(-h) / spy - 1
        fit = ols_hac(forward[late].to_numpy(), (gauge[late] / 10).to_numpy(), lags=h - 1)
        print(f"  h={h}d t {fit.t_slope:+.2f}", end="")
        rows.append(
            {
                "test": "regression_2010",
                "item": f"{h}d",
                "estimate": fit.slope,
                "t": fit.t_slope,
                "p": fit.p_slope,
                "r2": fit.r2,
                "n": fit.n,
            }
        )
    print()

    # ---- test 2: bands
    print("\nTest 2: forward 21-day SPY return by band, against all other days")
    forward21 = spy.shift(-21) / spy - 1
    bands = gauge.map(band_of)
    band_fits = []
    for name in LABELS:
        dummy = (bands == name).astype(float)
        fit = ols_hac(forward21.to_numpy(), dummy.to_numpy(), lags=20)
        inside = forward21[bands == name].dropna()
        band_fits.append((name, fit, inside))
    band_holm = holm([f.p_slope for _, f, _ in band_fits])
    for (name, fit, inside), p_adj in zip(band_fits, band_holm, strict=True):
        print(
            f"  {LABELS[name]:<14} days {len(inside):>5}  mean {inside.mean() * 100:+.2f}%  "
            f"vs rest {fit.slope * 100:+.2f} pp  t {fit.t_slope:+.2f}  Holm p {p_adj:.3f}"
        )
        rows.append(
            {
                "test": "band",
                "item": name,
                "estimate": fit.slope,
                "t": fit.t_slope,
                "p": fit.p_slope,
                "p_holm": p_adj,
                "mean": float(inside.mean()),
                "se_mean": fit.se_at(1.0),
                "n": len(inside),
            }
        )
    overall = float(forward21.mean())

    # ---- test 3: rules, chosen in-sample, judged out of sample
    print("\nTest 3: rules chosen in 2007-2017, judged from 2018 (net of 5 bp per unit traded)")
    spy_ret = spy.pct_change()
    trials: dict[str, pd.Series] = {}
    for t in RULE_A:
        trials[f"A: out above {t}"] = rule_returns((gauge <= t).astype(float), spy_ret)
    for t in RULE_B:
        trials[f"B: full below {t}, else half"] = rule_returns(
            np.where(gauge < t, 1.0, 0.5) * pd.Series(1.0, index=gauge.index), spy_ret
        )
    first = spy_ret.index >= gauge.index[0] + pd.Timedelta(days=1)
    in_sample = first & (spy_ret.index < SPLIT)
    out_sample = spy_ret.index >= SPLIT
    trial_in = {k: stats(v[in_sample]) for k, v in trials.items()}
    hold_in, hold_out = stats(spy_ret[in_sample]), stats(spy_ret[out_sample])
    best = max(trial_in, key=lambda k: trial_in[k]["sharpe"])
    print(f"  buy and hold    in-sample Sharpe {hold_in['sharpe']:.2f}", end="")
    print(f"  out-of-sample {hold_out['sharpe']:.2f}")
    for name, s in trial_in.items():
        mark = "  <- chosen" if name == best else ""
        print(f"  {name:<30} in-sample Sharpe {s['sharpe']:.2f}{mark}")
    chosen_out = stats(trials[best][out_sample])
    excess = trials[best][out_sample] - spy_ret[out_sample]
    ex = stats(excess)
    psr = probabilistic_sharpe(ex["sr_day"], int(ex["n"]), ex["skew"], ex["kurt"], 0.0)
    trial_sr = [stats(v[out_sample] - spy_ret[out_sample])["sr_day"] for v in trials.values()]
    dsr = deflated_sharpe(ex["sr_day"], int(ex["n"]), ex["skew"], ex["kurt"], trial_sr)
    co, ho = chosen_out, hold_out
    print(
        f"  chosen rule out of sample: return {co['ret']:.1%}  vol {co['vol']:.1%}  "
        f"Sharpe {co['sharpe']:.2f}"
    )
    print(f"  buy and hold out of sample: return {ho['ret']:.1%}  vol {ho['vol']:.1%}  ", end="")
    print(f"Sharpe {ho['sharpe']:.2f}")
    print(f"  excess over hold: P(Sharpe > 0) {psr:.2f}  deflated for 10 trials {dsr:.2f}")
    rows.append(
        {
            "test": "rule",
            "item": best,
            "estimate": chosen_out["sharpe"],
            "hold": hold_out["sharpe"],
            "ret": chosen_out["ret"],
            "vol": chosen_out["vol"],
            "hold_ret": hold_out["ret"],
            "hold_vol": hold_out["vol"],
            "psr": psr,
            "dsr": dsr,
            "n": int(chosen_out["n"]),
        }
    )

    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "fear-greed-results.csv", index=False, float_format="%.6g")
    write_svg(band_fits, overall, OUT / "fear-greed.svg")
    print(f"\nwrote {OUT / 'fear-greed-results.csv'} and fear-greed.svg")
    return 0


def write_svg(
    band_fits: list[tuple[str, Regression, pd.Series]], overall: float, path: Path
) -> None:
    """Mean forward 21-day return by band, with a 95% interval from the Newey-West error."""
    width, height = 720, 360
    m = {"l": 64, "r": 20, "t": 46, "b": 64}
    means = [float(inside.mean()) for _, _, inside in band_fits]
    ses = [fit.se_at(1.0) for _, fit, _ in band_fits]
    lo = min(0.0, min(mu - 2 * se for mu, se in zip(means, ses, strict=True)))
    hi = max(mu + 2 * se for mu, se in zip(means, ses, strict=True))
    lo, hi = math.floor(lo * 100) / 100, math.ceil(hi * 100) / 100
    plot_w, plot_h = width - m["l"] - m["r"], height - m["t"] - m["b"]

    def y(v: float) -> float:
        return m["t"] + (hi - v) / (hi - lo) * plot_h

    step = plot_w / len(band_fits)
    colors = ["#c53030", "#d9774b", "#7f8da0", "#4f9a75", "#0e7a4d"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'font-family="Segoe UI, Inter, system-ui, sans-serif" font-size="12">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{m["l"]}" y="22" font-size="14" font-weight="600" fill="#0b1b2b">'
        "S&amp;P 500 (SPY) return over the next 21 trading days, by gauge band</text>",
        f'<text x="{m["l"]}" y="38" fill="#475569">Mean and 95% interval (Newey-West, 20 lags). '
        "Dashed line: all days.</text>",
    ]
    tick = 0.01
    v = lo
    while v <= hi + 1e-9:
        parts.append(
            f'<line x1="{m["l"]}" x2="{width - m["r"]}" y1="{y(v):.1f}" y2="{y(v):.1f}" '
            f'stroke="{"#7f8da0" if abs(v) < 1e-9 else "#e4e9ef"}"/>'
        )
        label = f"{v * 100:+.0f}%"
        parts.append(
            f'<text x="{m["l"] - 8}" y="{y(v) + 4:.1f}" text-anchor="end" fill="#7f8da0">'
            f"{label}</text>"
        )
        v += tick
    parts.append(
        f'<line x1="{m["l"]}" x2="{width - m["r"]}" y1="{y(overall):.1f}" y2="{y(overall):.1f}" '
        'stroke="#1e5bb8" stroke-dasharray="5 4"/>'
    )
    for k, ((name, _, inside), mu, se) in enumerate(zip(band_fits, means, ses, strict=True)):
        cx = m["l"] + step * (k + 0.5)
        bw = step * 0.46
        top, base = y(max(mu, 0.0)), y(min(mu, 0.0))
        parts.append(
            f'<rect x="{cx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{base - top:.1f}" '
            f'rx="3" fill="{colors[k]}" opacity="0.85"/>'
        )
        top_e, low_e = y(mu + 2 * se), y(mu - 2 * se)
        parts.append(
            f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{top_e:.1f}" y2="{low_e:.1f}" '
            'stroke="#0b1b2b" stroke-width="1.5"/>'
        )
        for e in (mu + 2 * se, mu - 2 * se):
            parts.append(
                f'<line x1="{cx - 6:.1f}" x2="{cx + 6:.1f}" y1="{y(e):.1f}" y2="{y(e):.1f}" '
                'stroke="#0b1b2b" stroke-width="1.5"/>'
            )
        base_y = height - m["b"]
        parts.append(
            f'<text x="{cx:.1f}" y="{base_y + 20}" text-anchor="middle" fill="#0b1b2b" '
            f'font-weight="600">{LABELS[name]}</text>'
        )
        note = f"{mu * 100:+.2f}% · {len(inside):,} days"
        parts.append(
            f'<text x="{cx:.1f}" y="{base_y + 36}" text-anchor="middle" fill="#7f8da0">'
            f"{note}</text>"
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
