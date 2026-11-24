# Roadmap

Ordered by how useful each step is for managing a real portfolio. A step ships only when its
"done when" holds, with tests against answers known in advance.

## Done

| Step | What | Done when (met) |
|---|---|---|
| 0 | Tooling: uv, ruff, pyright strict, pytest, pre-commit, CI on 3.11 and 3.14 | CI green on both versions |
| 1 | Holdings in, clean euro returns out; live data with cache and fallback | Value matches an independent recomputation on a live 12-asset portfolio |
| 2 | Descriptive risk: volatility, drawdown, correlation, concentration | Closed-form and hand-computed examples |
| 3 | VaR, ES and risk contributions, then VaR backtesting | Kupiec, Christoffersen and Basel answers from the literature |
| 4 | Historical crises and custom scenarios | One-asset portfolios reproduce the asset's own crisis move |
| 5 | Rebalancing with costs, bands and risk parity | Plans pay for themselves (fuzzed); risk parity matches inverse volatility |
| 6 | Monte Carlo with calibration | Lognormal answer on i.i.d. data; a regime break fails the calibration |
| — | Factor exposures, benchmark comparison, Ledoit-Wolf, income, signals | See [METHODOLOGY.md](METHODOLOGY.md) |
| 7 | Transaction log: TWR, MWR, average-cost gains; Brinson attribution; tearsheet | TWR and MWR match a hand-built example with two contributions and one sale |
| 11 | English interface | Every string in both languages; no Portuguese left in the English page |

## Next

### 7b. Taxes
Capital gains tax from the transaction log (Brazil: monthly exemption for stock sales up to
R$20,000 and 15% otherwise; Italy: 26%, 12.5% on government bonds), and a sale planner that
picks the lots with the lowest tax.

*Done when:* the tax matches hand-computed cases from each country's rules.

### 7c. Filtered historical VaR in the report
The [research note](research/var-backtest.md) shows historical simulation clustering its
breaches on every market tested, and filtered historical simulation holding up best. Show the
FHS VaR beside the historical one as today's conditional figure, with the same backtest.

*Done when:* the report's FHS backtest matches `research/var_backtest.py` on the same series.

### 8. Allocation with constraints
Minimum variance and a mean-variance frontier on the Ledoit-Wolf covariance, long only, with
per-asset limits. The report must show how much the weights move when the inputs change
slightly, because they usually move a lot.

*Done when:* the unconstrained solution matches the closed form, and the constrained one matches
a reference QP solver.

### 9. Backtesting allocation rules
Walk-forward tests of simple rules (calendar rebalancing, bands, risk parity) with costs and
point-in-time data. It comes late on purpose: this is where overfitting and look-ahead hide
best.

### 10. C++ core where profiling says so
Move the measured hot path (the bootstrap and Monte Carlo) to C++ behind the same Python
interface (CMake, scikit-build-core, nanobind). Results must match Python to a stated
tolerance, and the speed-up must be measured, not assumed.
