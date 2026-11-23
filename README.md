# projeto-quant

> Working title. Working today: returns, currency conversion, calendar alignment, risk
> measures, return attribution and an HTML report. Real market data is next;
> `scripts/demo_report.py` runs everything on synthetic data meanwhile.

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
uv run python scripts/demo_report.py     # HTML report of the example portfolio (synthetic data)
```

Tools are called as `python -m <tool>` because Windows Smart App Control blocks the
unsigned `.exe` launchers that pip/uv generate. On Linux or macOS, `uv run pytest` works too.

## The report

`quant.report.build_report(holdings, prices, fx, calendar, title=...)` writes one self-contained
HTML file (no server, no network). Every number in it comes from the tested functions; the
page only draws them. It has:

- a period selector (1, 3, 6 months, year to date, 12 months, all) that recomputes everything;
- value and drawdown charts with a shared crosshair;
- allocation by asset and by currency, with the effective number of positions;
- return attribution per asset, split into price and exchange-rate effects;
- weight versus share of risk, and the correlation matrix;
- a sortable positions table, plain-language definitions, light/dark mode, and print to PDF.

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
