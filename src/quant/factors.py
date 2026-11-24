"""What the portfolio really depends on: exposures to markets and currencies.

The portfolio's weekly return in euro is regressed on a few factors: the stock markets
its assets follow (in their own currency) and the exchange rates of the currencies it
holds. Each slope (beta) says how much the portfolio moves when that factor moves 1%;
R² says how much of its ups and downs the factors explain together.

Exposures estimated on the past only matter if they hold on new data. A walk-forward
test refits the model every week using only earlier weeks and predicts the next one; the
out-of-sample R² measures how well that worked. A model that explains 80% in sample but
nothing out of sample has learned noise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt
import pandas as pd

Matrix = npt.NDArray[np.float64]
WEEKS_PER_YEAR = 52


@dataclass(frozen=True)
class Regression:
    """Ordinary least squares with an intercept."""

    alpha: float
    betas: pd.Series
    standard_errors: pd.Series
    alpha_se: float
    r2: float
    residuals: pd.Series

    @property
    def t_stats(self) -> pd.Series:
        """Beta over its standard error; beyond about 2 the beta is unlikely to be zero."""
        return self.betas / self.standard_errors


def _design(x: pd.DataFrame) -> Matrix:
    values = x.to_numpy(dtype=float)
    design: Matrix = np.ones((len(values), values.shape[1] + 1))
    design[:, 1:] = values
    return design


def ols(y: pd.Series, x: pd.DataFrame) -> Regression:
    """Fit ``y = alpha + x @ betas + e`` by least squares.

    Raises
    ------
    ValueError
        If rows contain missing values, there are not more rows than coefficients, or
        the factors are perfectly collinear.

    """
    if y.isna().any() or x.isna().to_numpy().any():
        raise ValueError("missing values in the regression")
    n, k = len(y), x.shape[1] + 1
    if n <= k:
        raise ValueError("need more observations than coefficients")
    design = _design(x)
    target = y.to_numpy(dtype=float)
    gram = design.T @ design
    if np.linalg.matrix_rank(gram) < k:
        raise ValueError("factors are collinear")
    coef = cast(Matrix, np.linalg.solve(gram, design.T @ target))
    fitted: Matrix = design @ coef
    resid: Matrix = target - fitted
    sigma2 = float(resid @ resid) / (n - k)
    inverse: Matrix = np.asarray(np.linalg.inv(gram), dtype=np.float64)
    se: Matrix = np.sqrt(np.maximum(sigma2 * inverse.diagonal(), 0.0))
    total = float(((target - target.mean()) ** 2).sum())
    r2 = 1 - float(resid @ resid) / total if total > 0 else 0.0
    return Regression(
        alpha=float(coef[0]),
        betas=pd.Series(coef[1:], index=x.columns),
        standard_errors=pd.Series(se[1:], index=x.columns),
        alpha_se=float(se[0]),
        r2=r2,
        residuals=pd.Series(resid, index=y.index),
    )


def walk_forward_r2(y: pd.Series, x: pd.DataFrame, min_train: int = WEEKS_PER_YEAR) -> float:
    """Out-of-sample R² of predicting each week from a model fitted on all earlier weeks.

    ``1 - sum((y - prediction)^2) / sum((y - mean of earlier y)^2)``: 0 means no better
    than guessing the past average, negative means worse.

    Raises
    ------
    ValueError
        If fewer than ``min_train + 10`` weeks are available.

    """
    if len(y) < min_train + 10:
        raise ValueError("not enough weeks for a walk-forward test")
    errors: list[float] = []
    naive: list[float] = []
    for t in range(min_train, len(y)):
        fit = ols(y.iloc[:t], x.iloc[:t])
        row = x.iloc[t].to_numpy(dtype=float)
        prediction = fit.alpha + float(row @ fit.betas.to_numpy(dtype=float))
        actual = float(y.iloc[t])
        errors.append((actual - prediction) ** 2)
        naive.append((actual - float(y.iloc[:t].mean())) ** 2)
    return 1 - sum(errors) / sum(naive)


def variance_shares(fit: Regression, x: pd.DataFrame) -> pd.Series:
    """Split the variance of the fitted portfolio into factors (Euler) and the rest.

    Each factor's share is ``beta_k * cov(f_k, x @ beta) / var(y)``; the shares plus
    ``"residual"`` (what no factor explains) sum to 1.
    """
    betas = fit.betas.to_numpy(dtype=float)
    cov = x.cov().to_numpy(dtype=float)
    explained = cov @ betas
    fitted_var = float(betas @ explained)
    resid_var = float(fit.residuals.var())
    total = fitted_var + resid_var
    if total <= 0:
        raise ValueError("no variance to split")
    shares = pd.Series(betas * explained / total, index=x.columns)
    shares["residual"] = resid_var / total
    return shares


def weekly(prices: pd.DataFrame | pd.Series) -> pd.DataFrame:
    """Friday-to-Friday returns; weeks with a missing price on either side are dropped."""
    frame = prices.to_frame() if isinstance(prices, pd.Series) else prices
    closes = frame.resample("W-FRI").last()
    return closes.pct_change(fill_method=None).iloc[1:]


@dataclass(frozen=True)
class Exposure:
    """Factor model of the portfolio and how well it holds out of sample."""

    fit: Regression
    shares: pd.Series
    weeks: int
    oos_r2: float | None
    alpha_annual: float


def factor_exposure(value: pd.Series, factor_prices: pd.DataFrame) -> Exposure:
    """Regress the portfolio's weekly returns on the factors' weekly returns.

    Parameters
    ----------
    value : pd.Series
        Portfolio value in euro, daily.
    factor_prices : pd.DataFrame
        Daily price of each factor (an index in its own currency, or an exchange rate in
        euro per unit), one column per factor.

    Raises
    ------
    ValueError
        If fewer than 30 complete weeks remain.

    """
    joined = pd.concat(
        [weekly(value).iloc[:, 0].rename("_y"), weekly(factor_prices)], axis=1, sort=True
    )
    joined = joined.dropna()
    if len(joined) < 30:
        raise ValueError("need at least 30 complete weeks")
    y, x = joined["_y"], joined.drop(columns="_y")
    x = x.loc[:, x.std() > 0]  # a factor that never moved (a pegged rate) explains nothing
    if x.shape[1] == 0:
        raise ValueError("no factor moved in the period")
    fit = ols(y, x)
    try:
        oos: float | None = walk_forward_r2(y, x)
    except ValueError:
        oos = None
    return Exposure(
        fit=fit,
        shares=variance_shares(fit, x),
        weeks=len(joined),
        oos_r2=oos,
        alpha_annual=(1 + fit.alpha) ** WEEKS_PER_YEAR - 1 if fit.alpha > -1 else -1.0,
    )


def significant(t_stat: float) -> bool:
    """Two-sided 5% test with a normal approximation: ``|t| > 1.96``."""
    return math.isfinite(t_stat) and abs(t_stat) > 1.96
