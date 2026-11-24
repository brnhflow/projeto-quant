# Where this makes money

Trading firms and asset managers build tools like this for one reason: to make or keep more
money than they spend. This page maps each part of the project to the way it creates value,
what it would take to turn that into an edge or a business, and where the claims stop.

## The principle

Money in markets comes from three places, and only the third is hard:

| Source | What it means | Where it is in this project |
|---|---|---|
| **Not losing it** | Sizing positions so a bad month cannot end the strategy; knowing when a risk model is wrong | VaR with backtests, filtered historical VaR, stress tests, Monte Carlo calibration |
| **Not wasting it** | Paying less in costs, taxes and currency drag | Rebalancing with tolerance bands, "new money only" mode, cost estimates, FX attribution |
| **Finding an edge** | A signal that predicts returns after costs, out of sample | Rule-based signals, walk-forward testing, the research pipeline |

Most strategies that fail do not fail because their signal was wrong. They fail because they
were sized on a risk number that was too small. The [research note](research/var-backtest.md)
shows exactly this: the historical VaR most tools use was broken 8 times in 29 days in March
2020 on the S&P 500. A fund sized on it would have run out of risk budget in the crash.

## 1. Risk that holds up in a crisis (what keeps a strategy alive)

**What firms do.** Every desk has a risk limit. When realised losses break the model, positions
are cut, often at the worst moment. A model that underestimates risk forces selling at the
bottom; one that overestimates it leaves returns unused.

**What this project adds.**
- The VaR is tested every day against what happened (Kupiec, Christoffersen, Basel traffic
  light). A Christoffersen failure warns that risk comes in clusters, before the crisis.
- Filtered historical simulation reacts to volatility within days and kept every rolling year
  out of the Basel red zone on seven markets since 2008.
- **Volatility targeting** follows directly: scale the position by `target vol / FHS vol`. This
  is how CTAs and risk-parity funds keep risk constant. Holding risk constant through 2008 and
  2020 is what kept their drawdowns survivable.

**Next step that turns it into money:** a position-sizing module that takes the FHS forecast
and a target volatility and outputs units per asset, backtested with costs (roadmap step 9).

## 2. Costs, taxes and currency (savings anyone can measure)

- **Rebalancing with bands** trades only what drifted past its tolerance. The planner shows the
  turnover and cost of each plan before any trade, so the cost of a rule is visible and can be
  compared with a calendar rule.
- **"New money only"** reaches the target without selling, so no capital gain is realised.
  In Brazil (2025 rules), stock sales above R$20,000 a month pay 15% on the gain; in Italy, 26%.
  Deferring that tax keeps the money compounding.
- **Currency attribution** separates what the assets earned from what the exchange rate did.
  For a Brazilian investing in euro, or a European holding B3 stocks, the currency is often the
  largest single risk, and it is usually invisible in broker reports.

## 3. Finding an edge (the hard part, done honestly)

The Signals tab finds candidates with fixed rules: price far below the 52-week high, dividend
yield above its own history, diversifying indices. **A signal is not an edge until it survives
three tests**, and the project already has the machinery for each:

1. **Out of sample.** Fit on the past, test on what came after (the walk-forward used for the
   factor model).
2. **After costs.** The rebalancing cost model applied to every trade the signal generates.
3. **Against chance.** With many signals tried, some look good by luck. The bootstrap gives each
   Sharpe ratio an interval; a multiple-testing correction (Bonferroni or the deflated Sharpe
   ratio of Bailey and López de Prado) says how many to discount.

This is how quantitative firms work: most ideas die in this pipeline, and the value is in
killing bad ones cheaply, before real money finds out.

## 4. As a product

| Customer | Pain | What they would pay for |
|---|---|---|
| Individual investors with assets in more than one country | Broker reports show each account in its own currency, with no consolidated risk | A consolidated report in their home currency: risk, income, tax-aware rebalancing |
| Independent advisors (RIAs; *assessores de investimento* in Brazil) | Manual spreadsheets for client reviews; little risk analysis | White-label reports per client, with a methodology they can show a regulator |
| Family offices and small funds | Need institutional analytics (attribution, stress tests, VaR backtests) without a Bloomberg PORT licence | Attribution and risk reporting at a fraction of the cost |

What already fits: the report is one self-contained HTML file (easy to send to a client), every
method is documented with references, and the numbers are tested. What it would need: user
accounts, scheduled runs, a licensed data feed instead of free sources, and a compliance review.

## 5. What this is not

- **Not a guarantee of returns.** Markets are close to efficient; any edge is small and decays
  once found. The project measures and controls risk; it does not predict prices.
- **Not trading software.** It places no orders and connects to no broker, by design.
- **Free data has limits:** gaps, survivorship bias and adjustment errors. A commercial version
  needs a licensed feed.
- **Nothing here is financial advice.**

## Roadmap to an edge

| Step | Turns into money by | Status |
|---|---|---|
| FHS VaR in the report | Sizing on a risk number that holds in crises | Researched; next |
| Volatility-targeted position sizing | Constant risk, smaller drawdowns | Planned |
| Walk-forward backtests of rules with costs | Knowing which rules pay after costs | Planned (step 9) |
| Deflated Sharpe ratio on every signal | Not trading what was luck | Planned |
| Taxes from the transaction log | Measurable savings for Brazilian and Italian investors | Planned (step 7b) |

*References: Bailey, D., López de Prado, M. (2014). The deflated Sharpe ratio. Journal of
Portfolio Management, 40(5), 94–107. Moreira, A., Muir, T. (2017). Volatility-managed portfolios.
Journal of Finance, 72(4), 1611–1644.*
