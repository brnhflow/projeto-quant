# Changelog

All notable changes, newest first. Versions follow [Semantic Versioning](https://semver.org);
before 1.0 the interface may still change.

## Unreleased

### Added
- English interface, with a PT/EN switch in the report and the editor (remembered per
  browser). Quantities are read in the page's language.
- **Tearsheet** tab: statistics against MSCI ACWI, monthly return table with the hit rate,
  rolling 126-day Sharpe and volatility, worst drawdowns with recovery, calendar-year returns
  and the daily return distribution against a normal.
- **Transaction log** (CSV import in the editor, `--transactions` on the command line):
  time-weighted return, money-weighted return (XIRR), realised and unrealised gains by average
  cost, and value against net money invested. The log must end with the holdings' quantities.
- **Brinson-Fachler attribution** against MSCI ACWI by market, with the index's regional mix
  estimated by returns-based style analysis.
- Long-only minimum-variance targets in the rebalancing planner (projected gradient on the
  simplex, Ledoit-Wolf covariance), tested against the closed form.
- Optional average cost and purchase date per position: the summary shows the money invested
  (at the exchange rate of each purchase date), the gain, and the annual money-weighted
  return (XIRR); the positions table shows each position's cost and gain.

### Fixed
- The total row of the positions table sat one column off.
- The income calendar counts exactly 24 whole months, so a month is never counted three times.
- Dividend yield history uses quoted closes; adjusted prices overstated past yields.
- Benchmark statistics use only days the index traded, and the alpha note says when a price
  index flatters the portfolio.
- Cash is never flagged as concentration; "below target" reads only complete saved targets.

## 0.4.0 — 2026-11-24

### Added
- Report organised in eight tabs (summary, this week, risk, scenarios, income,
  opportunities, rebalance, method). The open tab is kept in the address.
- Asset types (stock, real-estate fund, ETF, BDR, fund, crypto, cash) with drawn icons,
  detected from the exchange's short names, plus a type picker in the editor.
- **Income** page: expected dividends month by month and a 25-year projection with
  contributions, reinvestment and a monthly goal.
- **Opportunities** page: rule-based signals to investigate.
- Benchmark comparison against MSCI ACWI, S&P 500, Euro Stoxx 50 and Ibovespa: beta, alpha,
  tracking error, information ratio, up and down capture.
- Ledoit-Wolf covariance for risk parity and rebalancing. Sharpe, Sortino and Calmar ratios.
- Live demo on GitHub Pages, built from an example portfolio by `scripts/build_site.py`.
- Methodology document with formulas, assumptions and references.

### Changed
- Report script split into one file per page, with a CI syntax check of the assembled script.
- Three hot loops vectorised (bootstrap, rolling VaR, proxy fits), and downloads run in
  parallel: a full analysis takes about 5 s instead of 8 s.

### Fixed
- Projected dividend growth is capped at ±10% a year.
- The factor model leaves global stocks out when regional indices are already factors.

## 0.3.0 — 2026-11-23

### Added
- Search that lists every instrument, filterable by market; cash positions in any currency.
- VaR backtesting (Kupiec, Christoffersen, Basel traffic light) and bootstrap intervals.
- Eight historical crises replayed on today's positions, with Vasicek-shrunk proxy betas, and
  a custom scenario builder.
- Rebalancing planner with costs, tolerance bands, whole units and risk-parity targets.
- Factor exposures with a walk-forward out-of-sample test.
- Unusual-move alerts with headlines, and dividend income received.
- Monte Carlo fan for 1 to 5 years with month-by-month calibration.

## 0.2.0 — 2026-11-23

### Added
- Live market data (Yahoo, Kraken, ECB via Frankfurter) with a local cache and fallback.
- Local web app to enter the portfolio and analyse it with fresh data.

## 0.1.0 — 2026-11-23

### Added
- Returns, currency conversion, calendar alignment, holdings loader.
- Risk measures (volatility, drawdown, historical VaR and ES, risk contributions) and return
  attribution split into price and currency.
- Self-contained HTML report.
- Tooling: uv, ruff, pyright (strict), pytest, pre-commit, GitHub Actions on Python 3.11 and 3.14.
