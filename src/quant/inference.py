"""Inference for return-predictability tests: HAC standard errors and multiple-testing control.

A regression of the next h days' return on a signal observed today uses overlapping windows:
consecutive observations share h - 1 days, so the errors are autocorrelated and ordinary
standard errors are far too small. Newey and West (1987) correct them with a Bartlett-weighted
sum of autocovariances of the score; with h-day overlap the usual choice is h - 1 lags.

When several horizons or thresholds are tried, the smallest p-value overstates the evidence.
Holm (1979) adjusts a family of p-values so that the chance of any false rejection stays at the
chosen level, with more power than Bonferroni.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class Regression:
    """Slope of y on x with an intercept, its HAC standard error and the fit."""

    intercept: float
    slope: float
    se_slope: float
    t_slope: float
    p_slope: float  # two-sided, normal approximation
    r2: float
    n: int
    cov: tuple[tuple[float, float], tuple[float, float]]  # HAC covariance of (intercept, slope)

    def se_at(self, x: float) -> float:
        """Return the standard error of the fitted value intercept + slope * x."""
        (a, b), (_, c) = self.cov
        return math.sqrt(max(a + 2 * x * b + x * x * c, 0.0))


def normal_sf(z: float) -> float:
    """Upper tail of the standard normal."""
    return 0.5 * math.erfc(z / math.sqrt(2))


def ols_hac(
    y: Sequence[float] | FloatArray, x: Sequence[float] | FloatArray, lags: int
) -> Regression:
    """Ordinary least squares of y on [1, x] with Newey-West standard errors.

    ``lags`` = 0 gives White's heteroskedasticity-robust errors. Rows with a missing value in
    either series are dropped.
    """
    yv, xv = np.asarray(y, dtype=float), np.asarray(x, dtype=float)
    keep = np.isfinite(yv) & np.isfinite(xv)
    yv, xv = yv[keep], xv[keep]
    n = len(yv)
    if n < 3 or lags < 0:
        raise ValueError("need at least 3 observations and lags >= 0")
    design = np.ones((n, 2))
    design[:, 1] = xv
    bread = np.linalg.inv(design.T @ design)
    beta = bread @ design.T @ yv
    resid = yv - design @ beta
    score = design * resid[:, None]
    meat = score.T @ score
    for lag in range(1, min(lags, n - 1) + 1):
        weight = 1 - lag / (lags + 1)
        gamma = score[lag:].T @ score[:-lag]
        meat += weight * (gamma + gamma.T)
    cov = bread @ meat @ bread
    se = math.sqrt(max(float(cov[1, 1]), 0.0))
    slope = float(beta[1])
    t = slope / se if se > 0 else math.inf
    total = float(((yv - yv.mean()) ** 2).sum())
    r2 = 1 - float((resid**2).sum()) / total if total > 0 else 0.0
    matrix = ((float(cov[0, 0]), float(cov[0, 1])), (float(cov[1, 0]), float(cov[1, 1])))
    return Regression(float(beta[0]), slope, se, t, 2 * normal_sf(abs(t)), r2, n, matrix)


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm-adjusted p-values, in the order given (each capped at 1, monotone in rank)."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted
