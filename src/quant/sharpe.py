"""Is a Sharpe ratio real? The probabilistic and deflated Sharpe ratios.

Bailey and López de Prado (2012, 2014). A Sharpe ratio estimated from ``n`` returns is noisy, more
so when returns are skewed or fat-tailed, and the best of several strategies tried is biased up.

- Probabilistic Sharpe ratio (PSR): the probability that the true Sharpe exceeds a benchmark
  ``SR*``, given the estimate, the sample size, skewness ``g3`` and kurtosis ``g4``:

  ``PSR = Phi( (SR - SR*) sqrt(n - 1) / sqrt(1 - g3 SR + (g4 - 1) / 4 SR^2) )``

- Deflated Sharpe ratio (DSR): the PSR against the Sharpe the best of ``N`` trials would show by
  luck alone, ``SR* = sqrt(V) ((1 - gamma) Phi^-1(1 - 1/N) + gamma Phi^-1(1 - 1/(N e)))``, where
  ``V`` is the variance of the trials' Sharpe ratios and ``gamma`` the Euler-Mascheroni constant.

All Sharpe ratios here are per period (daily), not annualised.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import NormalDist

EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


def probabilistic_sharpe(
    sharpe: float, n: int, skew: float, kurtosis: float, benchmark: float = 0.0
) -> float:
    """Probability that the true per-period Sharpe exceeds ``benchmark``.

    ``kurtosis`` is the plain (not excess) kurtosis: 3 for a normal distribution.
    """
    if n < 2:
        raise ValueError("need at least two returns")
    denominator = 1 - skew * sharpe + (kurtosis - 1) / 4 * sharpe**2
    if denominator <= 0:
        raise ValueError("skewness and kurtosis give a non-positive variance")
    return _N.cdf((sharpe - benchmark) * math.sqrt(n - 1) / math.sqrt(denominator))


def expected_max_sharpe(trials: int, variance: float) -> float:
    """Sharpe ratio the best of ``trials`` strategies with no skill would show, on average."""
    if trials < 2:
        raise ValueError("need at least two trials")
    if variance < 0:
        raise ValueError("variance must be non-negative")
    a = _N.inv_cdf(1 - 1 / trials)
    b = _N.inv_cdf(1 - 1 / (trials * math.e))
    return math.sqrt(variance) * ((1 - EULER_GAMMA) * a + EULER_GAMMA * b)


def deflated_sharpe(
    sharpe: float, n: int, skew: float, kurtosis: float, trial_sharpes: Sequence[float]
) -> float:
    """PSR of ``sharpe`` against the best of the trials by luck (all per-period Sharpe ratios)."""
    k = len(trial_sharpes)
    mean = sum(trial_sharpes) / k
    variance = sum((s - mean) ** 2 for s in trial_sharpes) / (k - 1) if k > 1 else 0.0
    return probabilistic_sharpe(sharpe, n, skew, kurtosis, expected_max_sharpe(k, variance))
