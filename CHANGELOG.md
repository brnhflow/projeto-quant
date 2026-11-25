# Changelog

All notable changes, newest first. Versions follow [Semantic Versioning](https://semver.org);
before 1.0 the interface may still change.

## Unreleased

### Added
- **Fixed income tab**: government yield curves for Brazil, the US, the euro area, the UK and
  Japan (today, a month and a year ago), policy rates, curve slope with inversion flagged, every
  Tesouro Direto bond on sale with its change, and the inflation Brazil's bonds price in. Official
  sources only (Treasury, ECB, Bank of England, Japan's Ministry of Finance, Tesouro Nacional,
  BCB, New York Fed); the slow files download in the background and never hold up the report.
- **Fear and greed**: a stock gauge rebuilt from public prices with a stated method (momentum,
  strength, VIX, safe-haven and junk-bond demand, each a two-year percentile), next to the crypto
  index, with dials, the five parts and a year of history.
- Drawn arrows beside every change, a tab bar that scrolls with arrows when the tabs do not fit,
  and more motion: rows rise in turn, gauge needles sweep, curves draw, numbers fade when the
  period changes. All of it off under reduced motion.
- **Markets tab**: stock indices, currencies, US Treasury yields, commodities, crypto and the
  39 largest stocks in Brazil, the US and Europe, over a day, week, month, year to date and 12
  months. Moves are ranked by how unusual they were (the change over the series' own typical
  move for that many sessions), and each series shows its weekly correlation with the
  portfolio. Downloaded with every report, failures tolerated one by one.
- **Excel import and export** in the editor: the positions and the transaction log as a
  formatted .xlsx, read back from .xlsx or CSV (including semicolon files with 1.234,5
  numbers), headers in either language, with undo.
- Minimum variance with limits and how stable it is: 300 bootstrap re-estimates of the
  covariance, a 90% range for each weight on the Rebalance tab. Two solvers (active set in
  Python, FISTA in C++, which also runs the resamples in parallel) checked with the KKT
  conditions and against each other.
- Motion in the report: blocks rise as they come into view, lines draw, bars grow, headline
  numbers count up. Off when the system asks for reduced motion.
- A demo GIF and a "Notes from building it" section in the README.

### Changed
- Ledoit-Wolf noise term rewritten as matrix products: 13–40× faster in NumPy. A C++ kernel
  was added and benchmarked; BLAS is faster at 50 assets, so the report keeps NumPy.
- Finding cards jump to the section they come from and ring it briefly.
- Charts on hidden tabs are no longer redrawn on every change; switching tabs takes 10–20 ms.

## 0.5.0 — 2026-11-25

### Added
- **C++20 core** (`cpp/`, nanobind): rolling historical, EWMA and filtered historical VaR,
  stationary bootstrap, Monte Carlo paths and a walk-forward backtest engine. Parallel and
  reproducible for any thread count, checked against NumPy in CI (bit for bit or 1e-12), with
  C++ unit tests (CTest) and a benchmark (6-20x). Optional: without a compiler the package falls
  back to NumPy.
- **Rebalancing rules, backtested with costs**: buy and hold, monthly, 5% bands and a 10%
  volatility target, with probabilistic and deflated Sharpe ratios.
- **Three VaR models compared on each portfolio** with tomorrow's forecast, and
  **volatility-targeted sizing** on the Risk tab.
- **Key findings** at the top of the overview, linking to the tab with the detail.
- Info icons next to section and chart titles, replacing explanatory text; the methodology tab is
  a searchable glossary.
- Overview and Performance tabs instead of one long summary; every section on its own card.
- Author credit in the report, the editor and the README; `docs/APPLICATIONS.md` on where the
  project creates value.
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
- Research note comparing historical, EWMA and filtered historical VaR on seven markets since
  2008, with a script that reproduces every number (`research/var_backtest.py`).
- Long-only minimum-variance targets in the rebalancing planner (projected gradient on the
  simplex, Ledoit-Wolf covariance), tested against the closed form.
- Optional average cost and purchase date per position: the summary shows the money invested
  (at the exchange rate of each purchase date), the gain, and the annual money-weighted
  return (XIRR); the positions table shows each position's cost and gain.

### Fixed
- Parallel downloads could corrupt the exchange-rate cache, and a damaged cache file stopped the
  next analysis instead of being downloaded again.
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
