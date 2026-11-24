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
13. [References](#references)

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

## References

- Basel Committee on Banking Supervision (1996). *Supervisory framework for the use of "backtesting" in conjunction with the internal models approach to market risk capital requirements.*
- Christoffersen, P. (1998). Evaluating interval forecasts. *International Economic Review*, 39(4), 841–862.
- Griveau-Billion, T., Richard, J.-C., Roncalli, T. (2013). A fast algorithm for computing high-dimensional risk parity portfolios. *SSRN 2325255.*
- Jorion, P. (2007). *Value at Risk: The New Benchmark for Managing Financial Risk*, 3rd ed. McGraw-Hill.
- Kupiec, P. (1995). Techniques for verifying the accuracy of risk measurement models. *Journal of Derivatives*, 3(2), 73–84.
- Ledoit, O., Wolf, M. (2004). A well-conditioned estimator for large-dimensional covariance matrices. *Journal of Multivariate Analysis*, 88(2), 365–411.
- Politis, D., Romano, J. (1994). The stationary bootstrap. *Journal of the American Statistical Association*, 89(428), 1303–1313.
- Vasicek, O. (1973). A note on using cross-sectional information in Bayesian estimation of security betas. *Journal of Finance*, 28(5), 1233–1239.
