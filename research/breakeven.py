"""Research note: does the inflation priced into Tesouro Direto predict the IPCA? 2005 to 2024.

Run: uv run python research/breakeven.py
Writes docs/research/breakeven-results.csv and docs/research/breakeven.svg, and prints the
tables used in docs/research/breakeven.md.

Design, fixed before looking at the results except where noted:
- Breakeven: on the last trading day of each month, the Prefixado (nominal) and IPCA+ (real)
  curves from the Tesouro Direto buy rates are each interpolated linearly at 1, 2 and 3 years
  (quant.fixed_income.breakeven), and the breakeven is (1 + nominal) / (1 + real) - 1. Months
  in which either curve does not reach the horizon are left out, not extrapolated.
- Changed after the first run: bonds with half a year or less to maturity are left out, and a
  curve only reaches a horizon if its two bonds around it are at most two years apart. The first
  run used the report's rule (more than three months, any gap) and gave a negative 2-year
  breakeven in April 2020, interpolated between an IPCA+ bond 3.5 months from maturity and one
  4.3 years out. Results under the report's rule are printed as a robustness check.
- Outcome: IPCA (BCB SGS series 433) compounded over the 12, 24 or 36 months after the
  observation month, annualised.
- Test 1, Mincer-Zarnowitz: realised on breakeven, joint Wald test of intercept 0 and slope 1,
  Newey-West errors with 12h - 1 lags (consecutive windows overlap), Holm across horizons.
- Test 2, premium: mean of breakeven minus realised, with a Newey-West 95% interval.
- Test 3, the Focus survey: the BCB's median forecast of IPCA over the next 12 months
  (non-smoothed series, official Olinda API), read on or before the same day. The same
  Mincer-Zarnowitz test, and a Diebold-Mariano comparison of squared errors against the
  1-year breakeven on the months both exist. Breakeven minus Focus is a second, survey-based
  estimate of the premium that does not depend on how inflation turned out.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from quant.data.http import fetch_bytes
from quant.data.rates import TESOURO_URL, parse_sgs, parse_tesouro, sgs_url
from quant.fixed_income import breakeven
from quant.inference import holm, mean_hac, normal_sf, ols_hac, wald_joint

ROOT = Path(__file__).parents[1]
OUT = ROOT / "docs" / "research"
CACHE = ROOT / "data" / "cache"
HORIZONS = (1, 2, 3)
MIN_YEARS = 0.5  # leave out bonds this close to maturity
MAX_GAP = 2.0  # interpolate only between bonds at most this many years apart
FOCUS_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
    "ExpectativasMercadoInflacao12Meses?$top=100000&$format=json&$select=Data,Mediana"
    "&$filter=Indicador%20eq%20'IPCA'%20and%20Suavizada%20eq%20'N'%20and%20baseCalculo%20eq%200"
)


def cached(name: str, url: str, today: pd.Timestamp) -> bytes:
    """Bytes of ``url``, downloaded at most once a day into the cache."""
    path = CACHE / f"research_{name}.bin"
    if path.exists() and pd.Timestamp(path.stat().st_mtime, unit="s").normalize() >= today:
        return path.read_bytes()
    data = fetch_bytes(url, timeout=120)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def load() -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Monthly breakevens (% a year, by horizon), monthly IPCA (%) and Focus by survey date."""
    today = pd.Timestamp.now().normalize()
    table = parse_tesouro(cached("tesouro", TESOURO_URL, today), pd.Timestamp("2000-01-01"))
    ipca = parse_sgs(cached("ipca", sgs_url(433, pd.Timestamp("2004-01-01"), today), today))
    rows = json.loads(cached("focus", FOCUS_URL, today))["value"]
    focus = pd.Series(
        [float(r["Mediana"]) for r in rows], index=pd.to_datetime([r["Data"] for r in rows])
    ).sort_index()
    days = pd.DatetimeIndex(sorted(table["date"].unique()))
    month_ends = pd.Series(days, index=days).groupby(days.to_period("M")).max()
    by_day = dict(tuple(table.groupby("date")))
    records: list[dict[str, float | pd.Timestamp | None]] = []
    for day in month_ends:
        rows_day = by_day[day]
        record: dict[str, float | pd.Timestamp | None] = {"date": day}
        for h in HORIZONS:
            record[f"be{h}"] = breakeven(rows_day, float(h), min_years=MIN_YEARS, max_gap=MAX_GAP)
            record[f"report{h}"] = breakeven(rows_day, float(h))
        records.append(record)
    frame = pd.DataFrame(records).set_index("date").astype(float)
    frame.index = pd.DatetimeIndex(frame.index).to_period("M")
    return frame, ipca, focus


def realised(ipca: pd.Series, months: pd.PeriodIndex, h: int) -> pd.Series:
    """IPCA compounded over the 12h months after each month, % a year (NaN if not yet known)."""
    monthly = pd.Series(ipca.to_numpy() / 100, index=ipca.index.to_period("M"))
    out = []
    for m in months:
        window = monthly.reindex(pd.period_range(m + 1, m + 12 * h, freq="M"))
        if window.isna().any():
            out.append(math.nan)
        else:
            out.append((float(np.prod(1 + window.to_numpy())) ** (1 / h) - 1) * 100)
    return pd.Series(out, index=months)


def main() -> int:
    """Run the three tests, print the tables and write the CSV and the chart."""
    be, ipca, focus = load()
    print(f"Tesouro month-ends {be.index[0]} to {be.index[-1]}: {len(be)} months")
    print(f"IPCA to {ipca.index[-1]:%Y-%m}; Focus {focus.index[0]:%Y-%m-%d} to ", end="")
    print(f"{focus.index[-1]:%Y-%m-%d}")
    rows: list[dict[str, object]] = []
    real = {h: realised(ipca, be.index, h) for h in HORIZONS}
    month_end = be.index.to_timestamp(how="end").normalize()
    focus_at = pd.Series(
        focus.reindex(month_end, method="ffill").to_numpy(), index=be.index, dtype=float
    )

    # ---- tests 1 and 2: Mincer-Zarnowitz and the premium, by horizon
    print("\nTests 1-2: realised IPCA on the breakeven; premium = breakeven - realised")
    fits = []
    for h in HORIZONS:
        both = pd.DataFrame({"be": be[f"be{h}"], "real": real[h]}).dropna()
        fit = ols_hac(both["real"].to_numpy(), both["be"].to_numpy(), lags=12 * h - 1)
        stat, p = wald_joint(fit, 0.0, 1.0)
        prem, se, n = mean_hac((both["be"] - both["real"]).to_numpy(), lags=12 * h - 1)
        span = (both.index[-1] - both.index[0]).n + 1
        fits.append((h, both, fit, stat, p, prem, se, n, span))
    adjusted = holm([f[4] for f in fits])
    for (h, both, fit, stat, p, prem, se, n, span), p_adj in zip(fits, adjusted, strict=True):
        independent = span / (12 * h)
        corr = float(np.corrcoef(both["be"], both["real"])[0, 1])
        print(
            f"  {h}y  months {n:>3} ({both.index[0]} to {both.index[-1]}, span {span}, "
            f"~{independent:.0f} non-overlapping)  mean BE {both['be'].mean():.2f}  "
            f"mean realised {both['real'].mean():.2f}"
        )
        print(
            f"      MZ a {fit.intercept:+.2f}  b {fit.slope:.2f} (se {fit.se_slope:.2f})  "
            f"Wald {stat:.2f} p {p:.4f} Holm {p_adj:.4f}  R2 {fit.r2:.2f}  corr {corr:.2f}"
        )
        print(
            f"      premium {prem:+.2f} pp  se {se:.2f}  95% [{prem - 1.96 * se:+.2f}, "
            f"{prem + 1.96 * se:+.2f}]  t {prem / se:+.2f}"
        )
        rows.append(
            {
                "test": "mincer_zarnowitz",
                "item": f"breakeven_{h}y",
                "a": fit.intercept,
                "b": fit.slope,
                "se_b": fit.se_slope,
                "wald": stat,
                "p": p,
                "p_holm": p_adj,
                "r2": fit.r2,
                "n": n,
                "span_months": span,
                "start": str(both.index[0]),
                "end": str(both.index[-1]),
                "mean_forecast": float(both["be"].mean()),
                "mean_realised": float(both["real"].mean()),
            }
        )
        rows.append(
            {
                "test": "premium",
                "item": f"breakeven_{h}y",
                "estimate": prem,
                "se": se,
                "low": prem - 1.96 * se,
                "high": prem + 1.96 * se,
                "n": n,
            }
        )

    # Where the misses came from: mean 2-year error by year of observation.
    two = fits[1][1]
    by_year = (two["be"] - two["real"]).groupby(two.index.year).mean()
    print("  2y error (breakeven - realised) by year of observation:")
    print("    " + "  ".join(f"{year} {err:+.1f}" for year, err in by_year.items()))
    for year, err in by_year.items():
        rows.append({"test": "error_by_year", "item": f"breakeven_2y_{year}", "estimate": err})
    calendar = ((1 + ipca / 100).groupby(ipca.index.year).prod() - 1) * 100
    print("  IPCA by calendar year: " + "  ".join(f"{y} {calendar[y]:.1f}%" for y in (2015, 2021)))

    # Robustness: the report's rule (bonds with more than three months left, any gap).
    print("  robustness, report's interpolation rule:")
    for h in HORIZONS:
        loose = pd.DataFrame({"be": be[f"report{h}"], "real": real[h]}).dropna()
        fit = ols_hac(loose["real"].to_numpy(), loose["be"].to_numpy(), lags=12 * h - 1)
        stat, p = wald_joint(fit, 0.0, 1.0)
        prem, se, n = mean_hac((loose["be"] - loose["real"]).to_numpy(), lags=12 * h - 1)
        print(
            f"    {h}y  months {n:>3}  b {fit.slope:.2f} (se {fit.se_slope:.2f})  "
            f"R2 {fit.r2:.2f}  Wald p {p:.4f}  premium {prem:+.2f} pp  se {se:.2f}  "
            f"95% [{prem - 1.96 * se:+.2f}, {prem + 1.96 * se:+.2f}]  "
            f"~{((loose.index[-1] - loose.index[0]).n + 1) / (12 * h):.0f} non-overlapping"
        )
        # Exploratory, chosen after seeing the result: the same without 2018-2020, when the
        # IPCA+ curve had no bonds between a few months and about four years.
        calm = ~loose.index.year.isin([2018, 2019, 2020])
        part = ols_hac(
            loose["real"][calm].to_numpy(), loose["be"][calm].to_numpy(), lags=12 * h - 1
        )
        print(
            f"         without 2018-2020: months {part.n}  b {part.slope:.2f} "
            f"(se {part.se_slope:.2f})  R2 {part.r2:.2f}"
        )
        rows.append(
            {
                "test": "robustness_report_rule_without_2018_2020",
                "item": f"breakeven_{h}y",
                "a": part.intercept,
                "b": part.slope,
                "se_b": part.se_slope,
                "r2": part.r2,
                "n": part.n,
            }
        )
        rows.append(
            {
                "test": "robustness_report_rule",
                "item": f"breakeven_{h}y",
                "a": fit.intercept,
                "b": fit.slope,
                "se_b": fit.se_slope,
                "wald": stat,
                "p": p,
                "r2": fit.r2,
                "estimate": prem,
                "se": se,
                "n": n,
            }
        )

    # ---- test 3: Focus survey at one year
    print("\nTest 3: Focus median for the next 12 months")
    focus_frame = pd.DataFrame({"focus": focus_at, "real": real[1], "be": be["be1"]})
    full = focus_frame[["focus", "real"]].dropna()
    ffit = ols_hac(full["real"].to_numpy(), full["focus"].to_numpy(), lags=11)
    fstat, fp = wald_joint(ffit, 0.0, 1.0)
    ferr, fse, fn = mean_hac((full["focus"] - full["real"]).to_numpy(), lags=11)
    print(
        f"  Focus, every month-end with a known outcome ({full.index[0]} to {full.index[-1]}, "
        f"{fn}): MZ a {ffit.intercept:+.2f} b {ffit.slope:.2f} (se {ffit.se_slope:.2f}) "
        f"Wald {fstat:.2f} p {fp:.3f} R2 {ffit.r2:.2f}; mean error {ferr:+.2f} se {fse:.2f}"
    )
    rows.append(
        {
            "test": "mincer_zarnowitz",
            "item": "focus_1y",
            "a": ffit.intercept,
            "b": ffit.slope,
            "se_b": ffit.se_slope,
            "wald": fstat,
            "p": fp,
            "r2": ffit.r2,
            "n": fn,
            "start": str(full.index[0]),
            "end": str(full.index[-1]),
            "mean_forecast": float(full["focus"].mean()),
            "mean_realised": float(full["real"].mean()),
        }
    )
    rows.append({"test": "mean_error", "item": "focus_1y", "estimate": ferr, "se": fse, "n": fn})

    common = focus_frame.dropna()
    e_be, e_focus = common["be"] - common["real"], common["focus"] - common["real"]
    rmse_be = float(np.sqrt((e_be**2).mean()))
    rmse_focus = float(np.sqrt((e_focus**2).mean()))
    loss, loss_se, cn = mean_hac((e_be**2 - e_focus**2).to_numpy(), lags=11)
    dm_t = loss / loss_se
    dm_p = 2 * normal_sf(abs(dm_t))
    print(
        f"  common months {cn} ({common.index[0]} to {common.index[-1]}): mean error BE "
        f"{e_be.mean():+.2f}, Focus {e_focus.mean():+.2f}; RMSE BE {rmse_be:.2f}, "
        f"Focus {rmse_focus:.2f}; DM t {dm_t:+.2f} p {dm_p:.3f}"
    )
    rows.append(
        {
            "test": "diebold_mariano",
            "item": "breakeven_1y_vs_focus",
            "estimate": loss,
            "t": dm_t,
            "p": dm_p,
            "rmse_breakeven": rmse_be,
            "rmse_focus": rmse_focus,
            "mean_error_breakeven": float(e_be.mean()),
            "mean_error_focus": float(e_focus.mean()),
            "n": cn,
            "start": str(common.index[0]),
            "end": str(common.index[-1]),
        }
    )

    # Survey-based premium: breakeven minus Focus, on every month with both (outcome not needed).
    gap_frame = focus_frame[["be", "focus"]].dropna()
    gap, gap_se, gn = mean_hac((gap_frame["be"] - gap_frame["focus"]).to_numpy(), lags=11)
    print(
        f"  breakeven 1y - Focus, {gn} months ({gap_frame.index[0]} to {gap_frame.index[-1]}): "
        f"{gap:+.2f} pp  se {gap_se:.2f}  95% [{gap - 1.96 * gap_se:+.2f}, "
        f"{gap + 1.96 * gap_se:+.2f}]"
    )
    rows.append(
        {
            "test": "premium_vs_focus",
            "item": "breakeven_1y",
            "estimate": gap,
            "se": gap_se,
            "low": gap - 1.96 * gap_se,
            "high": gap + 1.96 * gap_se,
            "n": gn,
            "start": str(gap_frame.index[0]),
            "end": str(gap_frame.index[-1]),
        }
    )
    OUT.mkdir(parents=True, exist_ok=True)
    results = pd.DataFrame(rows)
    results.to_csv(
        OUT / "breakeven-results.csv", index=False, float_format="%.6g", lineterminator="\n"
    )
    write_svg(be["be2"], real[2], OUT / "breakeven.svg")
    print(f"\nwrote {OUT / 'breakeven-results.csv'} and breakeven.svg")
    return 0


def write_svg(forecast: pd.Series, outcome: pd.Series, path: Path) -> None:
    """Two-year breakeven against the IPCA of the following two years, by observation month."""
    width, height = 720, 360
    m = {"l": 52, "r": 20, "t": 64, "b": 40}
    first = min(forecast.first_valid_index(), outcome.first_valid_index())
    last = max(forecast.last_valid_index(), outcome.last_valid_index())
    months = forecast.index[(forecast.index >= first) & (forecast.index <= last)]
    x0, x1 = months[0].ordinal, months[-1].ordinal
    values = pd.concat([forecast, outcome]).dropna()
    lo, hi = 0.0, math.ceil(float(values.max()) / 2) * 2
    plot_w, plot_h = width - m["l"] - m["r"], height - m["t"] - m["b"]

    def x(p: pd.Period) -> float:
        return m["l"] + (p.ordinal - x0) / (x1 - x0) * plot_w

    def y(v: float) -> float:
        return m["t"] + (hi - v) / (hi - lo) * plot_h

    def path_of(series: pd.Series) -> str:
        parts: list[str] = []
        pen = "M"
        for p in months:
            v = series.get(p)
            if v is None or not math.isfinite(float(v)):
                pen = "M"
                continue
            parts.append(f"{pen}{x(p):.1f},{y(float(v)):.1f}")
            pen = "L"
        return " ".join(parts)

    blue, dark = "#1e5bb8", "#0b1b2b"
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'font-family="Segoe UI, Inter, system-ui, sans-serif" font-size="12">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{m["l"]}" y="22" font-size="14" font-weight="600" fill="{dark}">'
        "Inflation priced into Tesouro Direto at two years, and what followed</text>",
        f'<text x="{m["l"]}" y="38" fill="#475569">% a year, by month of observation. '
        "Gaps: no IPCA+ bonds close enough to two years to interpolate.</text>",
        f'<line x1="{m["l"]}" x2="{m["l"] + 22}" y1="52" y2="52" stroke="{blue}" '
        'stroke-width="2"/>',
        f'<text x="{m["l"] + 28}" y="56" fill="{dark}">2-year breakeven</text>',
        f'<line x1="{m["l"] + 150}" x2="{m["l"] + 172}" y1="52" y2="52" stroke="{dark}" '
        'stroke-width="2" stroke-dasharray="5 3"/>',
        f'<text x="{m["l"] + 178}" y="56" fill="{dark}">IPCA over the next two years</text>',
    ]
    v = lo
    while v <= hi + 1e-9:
        out.append(
            f'<line x1="{m["l"]}" x2="{width - m["r"]}" y1="{y(v):.1f}" y2="{y(v):.1f}" '
            f'stroke="{"#7f8da0" if v == 0 else "#e4e9ef"}"/>'
        )
        out.append(
            f'<text x="{m["l"] - 8}" y="{y(v) + 4:.1f}" text-anchor="end" fill="#7f8da0">'
            f"{v:.0f}%</text>"
        )
        v += 2
    for year in range(months[0].year + 1, months[-1].year + 1):
        if year % 2:
            continue
        p = pd.Period(f"{year}-01", freq="M")
        out.append(
            f'<text x="{x(p):.1f}" y="{height - m["b"] + 18}" text-anchor="middle" '
            f'fill="#7f8da0">{year}</text>'
        )
    out.append(
        f'<path d="{path_of(outcome)}" fill="none" stroke="{dark}" stroke-width="1.6" '
        'stroke-dasharray="5 3"/>'
    )
    out.append(f'<path d="{path_of(forecast)}" fill="none" stroke="{blue}" stroke-width="2"/>')
    out.append("</svg>")
    path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    sys.exit(main())
