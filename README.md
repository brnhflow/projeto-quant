# projeto-quant

[![CI](https://github.com/brnhflow/projeto-quant/actions/workflows/ci.yml/badge.svg)](https://github.com/brnhflow/projeto-quant/actions/workflows/ci.yml)

> Working title. Working today: live market data (B3, European exchanges, crypto, ECB
> exchange rates), returns, currency conversion, calendar alignment, risk measures, return
> attribution and an HTML report.

## The problem

I hold a small investment portfolio and, until now, most of my decisions about it were made by
feel: a position looks too big, a market drop feels scary, a rebalance seems like a good idea.
I want to replace "feels" with numbers I can check:

- How much could this portfolio lose in a bad month, and which positions drive that loss?
- What would have happened to it in 2008, 2020 or 2022?
- If I make this trade, how do risk and concentration change?

This repository is where I build the tools to answer those questions, one piece at a time.

## Approach

- **Decision support, not trading.** The code reads data and produces analysis. It never places
  orders and never connects to a broker with trading permissions.
- **Small, tested pieces.** Each function is written alone, with tests that compare it against
  results known in advance (a hand calculation, a textbook example, a closed-form formula).
- **No look-ahead.** Any calculation dated *t* uses only information available at *t*.
  This is the easiest way to fool yourself in finance, so it is checked in tests, not just promised.
- **Assumptions written down.** Every model states what it assumes (normal returns, constant
  volatility, no transaction costs...) next to the code, in plain language.
- **Python first, C++ where it pays.** Python for everything until profiling shows a hot path
  (likely Monte Carlo); then that piece moves to C++ behind the same Python interface.

The order of the work, from most to least useful to me, is in [docs/ROADMAP.md](docs/ROADMAP.md).

## Running it

Requires [uv](https://docs.astral.sh/uv/). It installs the right Python version by itself.

```bash
uv sync                                  # create .venv with the project and dev tools
uv run python -m pytest                  # tests
uv run ruff check .                      # lint
uv run ruff format .                     # format
uv run python -m pyright                 # type check (strict)
uv run python -m pre_commit install      # run all checks before each commit
uv run python -m quant app               # open the portfolio editor in the browser
uv run python -m quant report            # same analysis from the command line
uv run python scripts/demo_report.py     # the report on synthetic data, no network
```

## Using it

`python -m quant app` opens a page on this computer (http://127.0.0.1:8750). Search each
asset by name or ticker ("petrobras", "ASML", "bitcoin"), type the quantity, and press
**Analisar carteira**: prices and exchange rates are downloaded at that moment and the
report opens. The portfolio is saved to `data/private/holdings.csv` and comes back filled in
next time; **Editar carteira** on the report goes back to it.

The server listens only on 127.0.0.1, rejects requests whose `Host` is not its own (DNS
rebinding) and accepts only JSON posts (other websites cannot trigger it).

Tools are called as `python -m <tool>` because Windows Smart App Control blocks the
unsigned `.exe` launchers that pip/uv generate. On Linux or macOS, `uv run pytest` works too.

## The report

One self-contained HTML file (no server, no network once written). Every number comes from
tested Python functions; the page only draws them. Sections:

| Section | What it answers | How it is checked |
|---|---|---|
| Performance | Value and drawdown over 1M, 3M, 6M, YTD, 12M or all | Matches an independent pandas recomputation |
| This week | Which assets moved beyond 2.5x their usual daily or weekly size, with the latest headlines (Google News) and dividends received in 12 months | z-score against the year before the move; feed parsing tested on saved responses |
| Composition, attribution, risk | Weights by asset and currency, return split into price and FX, share of risk, correlations | Attribution sums exactly to the total; risk shares sum to 1 |
| Factors | How much the portfolio moves with each market and currency (betas with error bands), and how its variance splits | Walk-forward out-of-sample R² next to the in-sample R²; alpha t-stat |
| Crises | Eight real crises (2008, euro debt, Brazil 2015, Brexit, Joesley Day, Covid, 2022 rates, FTX) replayed on today's positions, plus sliders to build a scenario | Assets that did not exist yet use their best index proxy and a Vasicek-shrunk beta; coverage is shown per crisis |
| The future | A fan of 2000 block-bootstrapped paths for 1, 3 or 5 years, with and without the past trend, and the chance of a 10/20/30% fall | Month-by-month calibration: how often reality landed inside the 90% range, with a binomial test |
| How far to trust the numbers | Day-by-day VaR backtest; 90% bootstrap ranges for return, volatility, Sharpe and VaR | Kupiec, Christoffersen and the Basel traffic light, with textbook answers in the tests |
| Rebalance | What to buy and sell to reach target weights (or only with new money), costs, cash left, risk before and after; current, equal or risk-parity targets | Plans always pay for themselves; risk parity equals inverse volatility for independent assets |

Plus a sortable positions table, plain-language definitions of every method, light and dark
mode, and print to PDF.

## Market data

Every analysis re-downloads the full history of every holding since 2007, four series at a time
(adjusted prices change after dividends, so appending would mix adjustments), keeps a copy
in `data/cache/`, and falls back to that copy if a source is down. The report says, per
series, where it came from, the date of the last price, whether that price is from a
session still trading, and whether it is a stale cached copy.

| Data | Source | Notes |
|---|---|---|
| Stocks, ETFs (B3 `PETR4.SA`, Euronext `ASML.AS`, London `VOD.L`...) | Yahoo Finance chart API | Unofficial and undocumented: can rate-limit or change. Prices adjusted for splits and dividends. Pence converted to pounds. |
| Crypto | Kraken public API (or Yahoo, e.g. `BTC-USD`) | Official, no key. Kraken returns at most 720 days. |
| Exchange rates | ECB euro reference rates, via [Frankfurter](https://frankfurter.dev) | One rate per TARGET business day, set around 16:00 CET. |
| Search | Yahoo search and lookup APIs | Search ranks well but returns 7 results; lookup lists every match, paged. |
| Market indices for crises and factors | Yahoo chart API (`^BVSP`, `^GSPC`, `^STOXX50E`, `^FTSE`, `^SSMI`, `BTC-USD`) | Price indices, no dividends. From 2007. |
| Dividends | Yahoo chart API events | Gross amounts per share; Brazilian JCP included as reported. |
| Headlines | Google News RSS | No key. B3 stocks by ticker in Portuguese, others by company name in English. |

Each holding names its source and ticker in the holdings CSV (see
`data/holdings.example.csv`). The currency in the file must match what the source reports,
or the update stops with an error instead of mixing currencies.

## Data and privacy

My real holdings live in `data/private/`, which is git-ignored. Anything committed here uses
made-up or public data. API keys go in `.env` (see `.env.example`), which is also git-ignored.

## Limitations

- Nothing here is financial advice, including for me: models are simplifications and past
  data does not repeat on schedule.
- Results are only as good as the input data. Free market data has gaps, survivorship bias
  and adjustment errors; each data source will document what it is known to get wrong.
- I am learning as I build this (calculus, linear algebra, ODEs, C++). Expect the early
  modules to be simple, and the git history to show the learning.

## License

MIT. See `LICENSE`. Nothing here is financial advice.
