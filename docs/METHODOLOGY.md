# Methodology

Each method is described here together with the assumptions it makes and the test that checks
it. Code references point to `src/quant/`. Returns are daily simple returns
$r_t = P_t / P_{t-1} - 1$ in euro unless stated otherwise; a year has 252 trading days.

## Contents

1. [Data and portfolio value](#1-data-and-portfolio-value)
2. [Risk measures](#2-risk-measures)
3. [Backtesting the VaR](#3-backtesting-the-var)
4. [Bootstrap intervals](#4-bootstrap-intervals)
5. [Benchmark comparison](#5-benchmark-comparison)
6. [Factor exposures](#6-factor-exposures)
7. [Historical stress tests](#7-historical-stress-tests)
8. [Monte Carlo and its calibration](#8-monte-carlo-and-its-calibration)
9. [Covariance estimation and risk parity](#9-covariance-estimation-and-risk-parity)
10. [Rebalancing](#10-rebalancing)
11. [Dividend income](#11-dividend-income)
12. [Signals](#12-signals)
13. [Gain on money invested](#13-gain-on-money-invested)
14. [Transaction log: time- and money-weighted returns](#14-transaction-log-time--and-money-weighted-returns)
15. [Brinson attribution](#15-brinson-attribution)
16. [Tearsheet](#16-tearsheet)
17. [Three VaR models on the portfolio](#17-three-var-models-on-the-portfolio)
18. [Volatility targeting](#18-volatility-targeting)
19. [Rebalancing rules, backtested](#19-rebalancing-rules-backtested)
20. [References](#references)

## 1. Data and portfolio value

**Prices.** Adjusted closes, which include splits and dividends, so a dividend is not a loss.
Adjustments rewrite history after each payment, so every run downloads the full history
again instead of appending.

**Calendar.** Markets close on different days. On each European business day, an asset takes
its last close at or before that day, provided it is at most 5 days old (`align.py`). Each
price is converted with the exchange rate of the same day, never a later one (`fx.py`).

**Portfolio value.** Today's quantities are held over the whole history (buy-and-hold, weights
drift with prices):

$$V_t = \sum_i q_i \, P_{i,t} \, X_{c(i),t}$$

Here $X_c$ is euro per unit of currency $c$. Cash in currency $c$ has $P \equiv 1$, so its only
risk is the exchange rate.

*Check:* on a live 12-asset, 6-currency portfolio, the report matched a value recomputed
independently with plain pandas to the cent.

## 2. Risk measures

`risk.py`

**Volatility:** $\hat\sigma \sqrt{252}$, with $\hat\sigma$ the sample standard deviation of daily returns.

**Drawdown:** $D_t = V_t / \max_{s \le t} V_s - 1$.

**Historical VaR and ES** at level $\alpha$ (95% by default):

- VaR is the negated "lower" empirical quantile of the returns, at position $\lfloor (n-1)(1-\alpha) \rfloor$ of the sorted sample.
- ES is the mean of the returns at or below that quantile, negated.

**Risk contributions (Euler).** With weights $w$ and covariance $\Sigma$:

$$\text{RC}_i = \frac{w_i (\Sigma w)_i}{w^\top \Sigma w}, \qquad \sum_i \text{RC}_i = 1$$

**Ratios** (no risk-free rate):

- Sharpe: $\bar r / \hat\sigma \cdot \sqrt{252}$.
- Sortino: $\bar r / \sqrt{\overline{\min(r,0)^2}} \cdot \sqrt{252}$.
- Calmar: compound annual return divided by $|\max D_t|$.

## 3. Backtesting the VaR

`validation.py`

For each day $t$, the VaR is computed only from the $W$ days before it ($W = 250$ when
possible) and compared with $r_t$. A breach is $I_t = \mathbb{1}[r_t < -\text{VaR}_t]$. Over
$n$ tested days with $x$ breaches and promised breach probability $p = 1-\alpha$:

**Kupiec proportion of failures.** Is $x/n$ compatible with $p$?

$$LR_{uc} = -2 \ln\!\left[(1-p)^{n-x} p^x\right] + 2 \ln\!\left[(1-\hat\pi)^{n-x} \hat\pi^x\right], \quad \hat\pi = x/n, \quad LR_{uc} \sim \chi^2_1$$

**Christoffersen independence.** Does a breach today make one tomorrow more likely? Let $n_{ij}$
count the transitions from state $i$ to state $j$ on consecutive days. With
$\pi_0 = n_{01}/(n_{00}+n_{01})$, $\pi_1 = n_{11}/(n_{10}+n_{11})$ and $\pi$ the pooled rate:

$$LR_{ind} = -2 \ln\!\left[(1-\pi)^{n_{00}+n_{10}} \pi^{n_{01}+n_{11}}\right] + 2 \ln\!\left[(1-\pi_0)^{n_{00}} \pi_0^{n_{01}} (1-\pi_1)^{n_{10}} \pi_1^{n_{11}}\right] \sim \chi^2_1$$

The conditional coverage test uses $LR_{uc} + LR_{ind} \sim \chi^2_2$. The p-values come from
closed forms: $P(\chi^2_1 > x) = \operatorname{erfc}(\sqrt{x/2})$ and
$P(\chi^2_2 > x) = e^{-x/2}$.

**Basel traffic light.** The zone is green while $P(X \le x) < 95\%$ under
$X \sim \text{Bin}(n, p)$, and red from 99.99%. For 250 days at 99% this reproduces the
regulatory table: green 0–4, yellow 5–9, red 10 or more.

*Checks:*

- $LR_{uc} = -500\ln 0.99$ for zero breaches.
- Jorion's acceptance region: 6 of 255 breaches accepted, 7 rejected.
- The Basel table.
- A forecast cannot change when a future return is altered.
- A correct model passes on i.i.d. data; a model blind to a volatility jump fails.

## 4. Bootstrap intervals

`validation.py`

Daily returns are resampled with the stationary bootstrap of Politis and Romano. Blocks of
consecutive days with geometric length (mean $\max(5, n^{1/3})$) keep calm and turbulent
stretches together, and wrapping around the end keeps the resampled series stationary. The
90% interval holds the 5th to 95th percentiles of the statistic over 2,000 resamples. All
resamples are generated in one vectorised draw.

*Assumption:* the past is representative. A resample cannot contain a crisis the sample never
had, so intervals from calm samples are too narrow.

## 5. Benchmark comparison

`benchmark.py`

All statistics use daily euro returns on common dates.

| Statistic | Formula |
|---|---|
| Beta | $\beta = \operatorname{cov}(r_p, r_b) / \operatorname{var}(r_b)$ |
| Jensen's alpha | $\alpha = 252 \cdot \overline{r_p - \beta r_b}$ |
| Tracking error | $\text{TE} = \sqrt{252}\,\operatorname{sd}(r_p - r_b)$ |
| Information ratio | $\text{IR} = 252 \cdot \overline{r_p - r_b} / \text{TE}$ |

Up (down) capture is the portfolio's mean return on the benchmark's up (down) days divided by
the benchmark's mean on those days. The MSCI ACWI benchmark comes from an ETF with dividends;
the other indices are price-only, which flatters the portfolio by roughly 2 to 4 points a year.

## 6. Factor exposures

`factors.py`

Weekly (Friday-to-Friday) portfolio returns are regressed by OLS on:

- the returns of the indices the holdings follow, in their own currency;
- the exchange rates of the currencies held.

Weekly data avoids the bias that different closing times across markets cause in daily data.

$$r_{p,t} = a + \sum_k \beta_k f_{k,t} + \varepsilon_t$$

- Standard errors are the classical ones, $\sqrt{\operatorname{diag}(\hat\sigma^2 (X^\top X)^{-1})}$.
- A factor that never moved is dropped.
- MSCI ACWI is left out when a regional index is already a factor, because it would only add collinearity.

**Variance split (Euler).** Factor $k$ explains $\beta_k \operatorname{cov}(f_k, f^\top\beta) / \operatorname{var}(r_p)$ of the variance; the rest is specific to the holdings.

**Walk-forward test.** Every week $t$ is predicted by a model fitted only on the weeks before $t$
(at least 52):

$$R^2_{oos} = 1 - \frac{\sum_t (r_t - \hat r_t)^2}{\sum_t (r_t - \bar r_{<t})^2}$$

Exposures are reported as stable when $R^2_{oos}$ keeps at least 80% of the in-sample $R^2$,
and as unstable below 50%.

## 7. Historical stress tests

`stress.py`

Each scenario is the move from the close before a crisis to its trough, applied to today's
quantities in euro. The exchange rate of the period counts.

**Assets with history in the window** use their own move.

**Assets without history** use a proxy index:

1. Among the candidate indices, pick the one with the highest $R^2$ on weekly euro returns, over all shared history since 2007 (at least 52 weeks).
2. Shrink the slope towards 1 according to its precision (Vasicek):

$$\beta^* = w\hat\beta + (1-w)\cdot 1, \qquad w = \frac{\sigma^2_{prior}}{\sigma^2_{prior} + \text{SE}(\hat\beta)^2}, \quad \sigma_{prior} = 0.5$$

$$\text{SE}(\hat\beta) = |\hat\beta| \sqrt{(1-R^2) / (R^2 (n-2))}$$

3. Estimate the move as $\max(-100\%, \beta^* \cdot \text{index move})$.

Positions with neither their own history nor an index (crypto before 2014) are reported as
"no data" and their share of the portfolio is shown.

## 8. Monte Carlo and its calibration

`simulation.py`

2,000 paths of 5 years are built from the portfolio's own daily log returns with the stationary
bootstrap, which keeps fat tails and volatility clustering.

- **No trend (default):** log returns are demeaned, so only the size of the moves comes from the past.
- **With trend:** the historical mean is kept.

The fan shows the 5, 25, 50, 75 and 95% quantiles month by month. The drawdown probability is
the share of paths whose running peak-to-trough fall within the first year reaches 10, 20 or 30%.

**Calibration.** At each non-overlapping month after the first year, the model (no trend) is
built only on data before that month and states the 90% range for the month ahead. The number
of hits $k$ out of $n$ months is tested against $\text{Bin}(n, 0.9)$ with a two-sided binomial
test.

*Checks:*

- With i.i.d. normal history the 1-year quantiles match the lognormal answer.
- Removing the trend shifts mean log growth by exactly the historical drift.
- A regime break makes the calibration fail.

## 9. Covariance estimation and risk parity

`risk.py`, `report/maths.js`

**Ledoit-Wolf.** The sample covariance $S$ (divided by $n$) is shrunk towards
$F = \mu I$, with $\mu = \operatorname{tr}(S)/p$:

$$\hat\Sigma = \delta F + (1-\delta) S, \qquad \delta = \frac{\min(b^2, d^2)}{d^2}$$

$$d^2 = \frac{\|S - F\|_F^2}{p}, \qquad b^2 = \frac{1}{n^2 p}\sum_t \|x_t x_t^\top - S\|_F^2$$

The implementation matches scikit-learn's shrinkage to 12 significant digits on a reference
sample.

**Risk parity.** Equal risk contributions are found by cyclical coordinate descent on

$$\min_y \tfrac12 y^\top \Sigma y - \sum_i b_i \ln y_i$$

With $c_i = \sum_{j \ne i} \Sigma_{ij} y_j$, each coordinate update is

$$y_i \leftarrow \frac{-c_i + \sqrt{c_i^2 + 4\Sigma_{ii} b_i}}{2\Sigma_{ii}}$$

and the weights are $w = y / \sum y$. Cash, which has zero variance, keeps its current weight.

*Checks:* independent assets give inverse-volatility weights; with correlation, the risk
contributions come out equal to within $10^{-6}$.

## 10. Rebalancing

`report/maths.js`

Each position's target value is $w_i (V + C)$, with $C$ the new money.

- **"Buy and sell"** trades only the positions outside a tolerance band.
- **"Only add money"** never sells, and spreads $C$ over the shortfalls in proportion to their size.

Costs are $|\text{trade}| \cdot c + f$ per traded position.

Every plan pays for itself: all buys are scaled by one factor $s \le 1$ so that

$$s \sum \text{buys}\,(1+c) + n_{buy} f = C + \sum \text{sales}\,(1-c) - n_{sell} f$$

Whole-unit rounding then never overspends: buys round down, and if rounding the sales leaves a
shortfall, units are removed from the largest buys. This was fuzzed on 20,000 random plans.

## 11. Dividend income

`income.py`

**Calendar.** The expected payment for each calendar month is the average paid in that month
over the last two years.

**Growth.** The median of the year-on-year changes in yearly payments per unit over the last
five full years:

- It needs at least three paying years and no year without payments.
- It is limited to ±10% a year.
- The median ignores a single special dividend; the limit stops a run of special dividends from compounding into an implausible projection.

**Projection.** Each holding keeps its growth for five years, fading linearly to zero by year
ten. New money and reinvested income earn the portfolio's current yield. Prices and exchange
rates stay as today, and amounts are gross of tax.

## 12. Signals

`signals.py`

Fixed rules, shown with what to check before acting:

| Signal | Rule |
|---|---|
| Far from the high | Last price ≤ 80% of the highest close of the last 252 days |
| Yield above its history | Trailing-12-month yield ≥ 1.25 × its median at the month-ends of the last five years (at least 36 month-ends) |
| Diversifier | The index whose 10% allocation (taken proportionally from every position) lowers last year's volatility the most, by at least 0.3 points |
| Concentration | A position above 25% of value or above 35% of risk |

## 13. Gain on money invested

`performance.py`, `_result` in `report/data.py`

With an average cost $c_i$ and first purchase date $d_i$ per position, the money invested is
$c_i q_i X_{c(i), d_i}$: the cost converted at the last exchange rate at or before the
purchase. Its gain is today's value over that amount. The annual money-weighted return is the
XIRR of the flows $(d_i, -\text{invested}_i)$ and $(\text{today}, +\sum \text{value}_i)$: the rate
$r$ that solves

$$\sum_k \frac{F_k}{(1+r)^{(t_k - t_0)/365}} = 0$$

It is found by bisection on $(-99.99\%, 10^6\%)$.

Unlike the time-weighted return, it rewards or penalises when the money went in. A position
bought several times enters at its first purchase date, which understates the rate.

*Checks:*

- 10% for a 1,100 return on 1,000 after 365 days, and after two years with 1,210.
- −20% for a loss.
- The NPV is zero at the solution for irregular flows.
- A later contribution before a gain raises the rate.
- With one purchase date for the whole portfolio, it equals the compound annual growth rate.

## 14. Transaction log: time- and money-weighted returns

`ledger.py`, `_ledger` in `report/data.py`

The other sections hold today's quantities over the whole history. With a log of every buy
and sell (date, ticker, side, quantity, price, fee), the units $u_{t,a}$ held at each close are
known, and two different questions get two different answers.

**Time-weighted return.** Each day's return is the return of the previous close's holdings:

$$r_t = \frac{\sum_a u_{t-1,a}\,(P_{t,a} - P_{t-1,a})}{\sum_a u_{t-1,a}\,P_{t-1,a}}, \qquad
\text{TWR} = \prod_t (1 + r_t) - 1$$

Trades are valued at the day's close, so money moving in or out never shows up as a return.
This is the measure GIPS requires of fund managers: it judges the investments and is blind to
the timing of contributions. A trade before the analysed history enters as the opening position;
a trade on a weekend counts from the next business day.

**Money-weighted return.** The XIRR (section 13) of the actual cash: each purchase
$-(q p + f)\,X_{d}$ and each sale $+(q p - f)\,X_{d}$ at the exchange rate $X_d$ of its date,
with today's value as the last flow. When contributions come before strong periods it is above
the TWR; before weak ones, below. The report compares the two only when the log starts inside
the analysed history, since otherwise they cover different spans.

**Realised and unrealised gains.** Average-cost method per asset, in euro: a purchase adds
$q p X_d + f X_d$ to the cost basis; a sale realises $(q p - f) X_d - \bar c\, q$, where $\bar c$ is
the average cost of the units held, and removes $\bar c\, q$ from the basis. Unrealised gain is
today's value minus the remaining basis. By construction

$$\text{realised} + \text{unrealised} = V_{\text{today}} + \sum \text{sales} - \sum \text{purchases}$$

Dividends received in cash are not in the log; the prices are adjusted closes, so the TWR
includes them as total return.

The log must end with the holdings' quantities: the app and the command line refuse a log that
does not, naming each asset that differs, and refuse a sale of more units than were held.

*Checks* (`tests/test_ledger.py`), on a hand-built example with two contributions and one
sale (prices 10, 11, 11, 12, 12; buy 10 at 10, buy 10 at 11, sell 5 at 12 with a fee of 1):

- Daily TWR 10%, 0%, 1/11, 0%, chaining to exactly the price return of 20%.
- Realised 6.5, unrealised 22.5, adding up to value plus sales minus purchases (29).
- The NPV of the cash flows is zero at the money-weighted rate.
- Moving all the money to a later date changes the MWR and leaves the TWR as the return of the
  days actually held.
- Cost in another currency uses the rate of the trade date; a sale beyond the units held, a log
  ending at different units, and malformed rows are refused.

## 15. Brinson attribution

`brinson.py`, `_brinson` in `report/data.py`

The gap to MSCI ACWI is split by market, in the Brinson-Fachler form of Brinson, Hood and
Beebower (1986). With portfolio weights $w^p_i$ and returns $r^p_i$ per market, benchmark weights
$w^b_i$ and index returns $r^b_i$, and $R^b = \sum_i w^b_i r^b_i$:

| Effect | Formula | Reads as |
|---|---|---|
| Allocation | $(w^p_i - w^b_i)(r^b_i - R^b)$ | More weight in markets that beat the benchmark |
| Selection | $w^b_i\,(r^p_i - r^b_i)$ | Your assets against their market's index |
| Interaction | $(w^p_i - w^b_i)(r^p_i - r^b_i)$ | Selection where you were overweight |

The three add up exactly to $\sum_i w^p_i r^p_i - R^b$. Weights are taken at the start of the
period and returns are buy-and-hold, which is exact for a portfolio that does not trade within
the period.

**Segments.** Each asset belongs to the regional index that explains its weekly euro returns
best (the stress-test mapping of section 7, with global stocks excluded). Cash is its own
segment, with zero benchmark weight; its whole effect is allocation.

**Benchmark weights by style analysis.** The index's regional mix is not taken from a factsheet
but estimated from its returns (Sharpe, 1992): the long-only weights summing to one that make
the mix of regional indices track ACWI best over the last two years of weekly returns,

$$\min_{w \ge 0,\ \mathbf 1^\top w = 1} \; \lVert r_{\text{ACWI}} - R\,w \rVert^2,$$

solved by projected gradient descent with the sorting projection onto the simplex (Duchi et al.,
2008). Weights under 1% are dropped as noise. The fit's R² is shown, and the replica's return is
shown beside ACWI's own, so any gap between the two is visible.

*Checks* (`tests/test_brinson.py`, `tests/test_stress.py`):

- Style weights recover a known 60/40 mix exactly (R² = 1) and stay long only when the best
  unconstrained fit would short.
- A textbook example reproduces each effect by hand, and the effects sum to the gap.
- In a full report on a synthetic market where ACWI is 70% US and 30% Europe, the weights come
  out at 70/30 and the effects add up to the gap in every period.

## 16. Tearsheet

`tearsheet.py`, `_tearsheet` in `report/data.py`

The usual one-page summary of a strategy, over the whole history, against MSCI ACWI on the days
it traded:

- **Statistics.** CAGR, volatility, Sharpe, Sortino, Calmar, maximum and longest drawdown,
  one-day 95% VaR and ES, best and worst day and month, share of positive days and months, and
  the bias-adjusted sample skew and excess kurtosis (zero for a normal distribution).
- **Monthly returns.** From each month's last close to the next; the first month starts from
  the first value. The year column compounds the months. The hit rate counts the months in which
  the portfolio beat the index.
- **Rolling Sharpe and volatility** over 126 trading days.
- **Worst drawdowns.** Each counted once from its peak to the first day back at that peak, with
  the trading days down and the days to recover; an open drawdown has no recovery yet.
- **Distribution.** Daily returns in 41 bins over ±4 standard deviations (outliers in the outer
  bins), against the counts a normal with the same mean and volatility would give.

*Checks* (`tests/test_tearsheet.py`): known month-end returns, months compounding to the total,
partial first years, drawdown periods with their peak, trough and recovery, the deepest ones
first, rolling ratios equal to the window computed directly, histogram counts adding up to the
number of days, and statistics on a series with a known CAGR, maximum drawdown and tail. In the
report, the tearsheet's maximum drawdown and VaR equal the summary's, and its months compound to
the whole-history return.

## 17. Three VaR models on the portfolio

`var_models.py`, `_var_models` in `report/data.py`

The research note's comparison runs on the user's portfolio: historical simulation, EWMA with
normal tails and filtered historical simulation, at 95% with the backtest window of section 3,
all tested on the same days with Kupiec, Christoffersen and the Basel zone. Each model's VaR for
the next day is computed by appending a placeholder day that no forecast can see, because every
model uses only the returns before the day it forecasts. The model with the highest conditional
coverage p-value is highlighted.

*Checks:* the three models are tested on identical days, and every forecast is positive; the
models themselves are covered in `tests/test_var_models.py` (no look-ahead, scaling, coverage on
normal returns, reaction to a volatility jump).

## 18. Volatility targeting

`insights.js`

Weight invested $= \min(1, \sigma^* / \hat\sigma)$, with $\sigma^*$ the target annual volatility and
$\hat\sigma = \text{VaR}^{\text{EWMA}}_{95\%} / 1.645 \cdot \sqrt{252}$ the EWMA forecast; the rest
is cash and there is no leverage. Redone at every rebalance, it holds risk roughly constant and
cuts exposure when volatility rises (Moreira and Muir, 2017).

## 19. Rebalancing rules, backtested

`rules.py` (reference), `cpp/include/quant/backtest.hpp` (engine)

Four rules on today's assets and weights, walk-forward over the report's history, paying 0.1%
on every amount traded:

| Rule | Trades when |
|---|---|
| Buy and hold | Never, after the initial purchase |
| Monthly | Every 21 trading days, back to the targets |
| Bands | Any weight is more than 5 points away from its target |
| Volatility target | Every 21 days, setting the share invested by section 18 from the EWMA of the strategy's own returns |

Each close: positions drift with prices, the rule decides on prices up to that close, and the
trade pays its cost. Using today's weights as targets is hindsight about the composition, as
everywhere else in the report; the decisions themselves never look ahead. Turnover excludes the
initial purchase; its cost is charged to every rule alike.

*Checks* (`tests/test_rules.py`, `cpp/tests/test_risk.cpp`): a rebalance with costs computed by
hand, costs only ever lowering value, bands trading far less often than a daily calendar, the
volatility target cutting volatility in a rough regime, no decision changing when future prices
change, and the C++ engine matching the Python reference to 1e-12 for every rule.

## References

- Bacon, C. (2008). *Practical Portfolio Performance Measurement and Attribution*, 2nd ed. Wiley.
- Basel Committee on Banking Supervision (1996). *Supervisory framework for the use of "backtesting" in conjunction with the internal models approach to market risk capital requirements.*
- Brinson, G., Hood, L. R., Beebower, G. (1986). Determinants of portfolio performance. *Financial Analysts Journal*, 42(4), 39–44.
- Christoffersen, P. (1998). Evaluating interval forecasts. *International Economic Review*, 39(4), 841–862.
- Duchi, J., Shalev-Shwartz, S., Singer, Y., Chandra, T. (2008). Efficient projections onto the l1-ball for learning in high dimensions. *ICML 2008*.
- Griveau-Billion, T., Richard, J.-C., Roncalli, T. (2013). A fast algorithm for computing high-dimensional risk parity portfolios. *SSRN 2325255.*
- Jorion, P. (2007). *Value at Risk: The New Benchmark for Managing Financial Risk*, 3rd ed. McGraw-Hill.
- Kupiec, P. (1995). Techniques for verifying the accuracy of risk measurement models. *Journal of Derivatives*, 3(2), 73–84.
- Ledoit, O., Wolf, M. (2004). A well-conditioned estimator for large-dimensional covariance matrices. *Journal of Multivariate Analysis*, 88(2), 365–411.
- Moreira, A., Muir, T. (2017). Volatility-managed portfolios. *Journal of Finance*, 72(4), 1611–1644.
- Politis, D., Romano, J. (1994). The stationary bootstrap. *Journal of the American Statistical Association*, 89(428), 1303–1313.
- Sharpe, W. F. (1992). Asset allocation: management style and performance measurement. *Journal of Portfolio Management*, 18(2), 7–19.
- Vasicek, O. (1973). A note on using cross-sectional information in Bayesian estimation of security betas. *Journal of Finance*, 28(5), 1233–1239.
