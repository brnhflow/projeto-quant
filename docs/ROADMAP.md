# Roadmap

Ordered by how useful each step is for managing my own portfolio, not by how impressive it
sounds. Each step ships only when its "done when" holds, with tests that check known answers.

## 0. Tooling (done)

uv, ruff, mypy (strict), pytest, pre-commit, GitHub Actions CI.

## 1. Portfolio and prices in, returns out

Load my holdings from a CSV I export by hand; fetch daily prices for them; compute simple and
log returns, in a single base currency (positions in other currencies converted with the FX
rate of the same day).

- *Useful because:* everything else depends on clean returns.
- *Done when:* returns match a hand-computed spreadsheet for 3 assets over 10 days, including
  one FX conversion and one missing price day handled explicitly.
- *Decide here:* first data source (free, documented; its known flaws written in the module).

## 2. Descriptive risk

Annualised volatility, maximum drawdown, correlation matrix, concentration (largest weights,
Herfindahl index).

- *Useful because:* answers "how bumpy is this, and is it really diversified?"
- *Done when:* each metric matches a closed-form or textbook example (e.g. volatility of a
  constant-return series is 0; drawdown of a known path equals the value worked out by hand).

## 3. Loss estimates and who causes them

Historical Value at Risk and Expected Shortfall; each position's contribution to total risk.

- *Useful because:* "in a bad month I could lose about X, and half of that comes from Y."
- *Done when:* parametric VaR matches the normal-distribution formula; contributions sum to
  the total; rolling estimates use only past data (look-ahead test).

## 4. Scenarios and stress tests

Replay historical crises (2008, March 2020, 2022) on today's weights; apply hand-made shocks
("equities -30%, rates +2pp, EUR -10%").

- *Useful because:* concrete stories are easier to act on than a single number.
- *Done when:* a one-asset portfolio reproduces that asset's actual crisis drawdown.

## 5. What-if trades and rebalancing

Current vs. target weights, drift, and the effect of a proposed trade on every metric above,
including transaction costs.

- *Useful because:* this is the moment of decision.
- *Done when:* a report shows before/after for a proposed trade; costs reduce the result by
  exactly the stated amount.

## 6. Monte Carlo for goals

Simulate future portfolio paths to answer "what is the chance of reaching X by year Y?",
with the return model and its assumptions stated next to the result.

- *Done when:* with zero volatility the simulation equals compound growth; with normal returns
  the simulated mean and variance converge to the analytical values.

## 7. Backtesting rules (later on purpose)

Walk-forward testing of simple allocation rules, with costs and strict point-in-time data.
Placed late because it is where overfitting and look-ahead mistakes hide best.

## 8. Allocation methods

Mean-variance, minimum variance, risk parity, with a sensitivity check showing how much the
weights move when inputs change slightly (they usually move a lot; the report should say so).

## 9. C++ core where profiling says so

Move the measured hot path (likely the Monte Carlo engine) to C++ (CMake, scikit-build-core,
pybind11 or nanobind), keeping the Python interface and the same tests. Python and C++ results
must agree to a stated tolerance.
