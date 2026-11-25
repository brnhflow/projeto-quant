"""Minimum-variance allocation with weight limits, and how much it moves with the data.

The problem, long only with per-asset limits ``lower <= w <= upper``:

``min w' S w / 2   subject to   sum(w) = 1``,

on the Ledoit-Wolf covariance ``S``. Expected returns are left out on purpose: they are the
noisiest input, and an optimiser fed with them mostly amplifies their errors (Michaud, 1989).

Even without them, the weights are unstable: two covariance estimates that differ only by
sampling noise can give quite different portfolios. ``resampled_weights`` measures that by
re-estimating ``S`` on stationary-bootstrap resamples of the returns and solving again: the spread
of each weight across resamples says how much of it is signal.

Two independent solvers are used and checked against each other:

- here, a primal active-set method, exact up to rounding in a finite number of steps;
- in C++ (``cpp/include/quant/allocation.hpp``), accelerated projected gradient (FISTA), which
  also runs the resampling in parallel.

Both are verified with the KKT conditions, which certify the optimum of a convex problem.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

from quant import core
from quant.risk import _ledoit_wolf_numpy  # pyright: ignore[reportPrivateUsage]

Vector = npt.NDArray[np.float64]
Matrix = npt.NDArray[np.float64]


def _bounds(p: int, lower: float, upper: float) -> tuple[Vector, Vector]:
    if not 0 <= lower <= upper:
        raise ValueError("need 0 <= lower <= upper")
    if p * lower > 1 + 1e-12 or p * upper < 1 - 1e-12:
        raise ValueError("no weights within the limits add up to 1")
    return np.full(p, lower), np.full(p, upper)


def _start(lo: Vector, hi: Vector) -> Vector:
    """Return a feasible starting point, as equal as the limits allow."""
    w = lo.copy()
    room = hi - lo
    rest = 1 - w.sum()
    # Fill the assets with the least room first so nobody exceeds its upper limit.
    order = room.argsort()
    for k, i in enumerate(order):
        share = rest / (len(order) - k)
        add = min(share, float(room[i]))
        w[i] += add
        rest -= add
    return w


def min_variance(cov: Matrix, lower: float = 0.0, upper: float = 1.0) -> Vector:
    """Long-only minimum-variance weights within ``[lower, upper]`` (primal active set).

    Each step solves the problem with the assets at a limit held there (one linear system),
    moves towards that solution as far as the limits allow, and frees a held asset only when its
    Lagrange multiplier says the variance would fall by letting it go.
    """
    s = np.asarray(cov, dtype=float)
    p = s.shape[0]
    lo, hi = _bounds(p, lower, upper)
    w = _start(lo, hi)
    tol = 1e-12
    held = (w <= lo + tol) | (w >= hi - tol)
    for _ in range(50 * p + 50):
        free = ~held
        if not free.any():
            # Every asset at a limit: the only candidate is the current point.
            target = w.copy()
        else:
            ff = s[np.ix_(free, free)]
            fixed = s[np.ix_(free, held)] @ w[held]
            a = np.linalg.solve(ff, np.ones(int(free.sum())))
            c = np.linalg.solve(ff, fixed)
            budget = 1 - float(w[held].sum())
            lam = (budget + float(c.sum())) / float(a.sum())
            target = w.copy()
            target[free] = lam * a - c
        step = target - w
        if np.abs(step).max() > tol:
            # Move towards the target until the first free asset reaches a limit.
            alpha, hit = 1.0, -1
            for i in free.nonzero()[0]:
                if step[i] < 0 and w[i] + step[i] < lo[i] - tol:
                    t = (lo[i] - w[i]) / step[i]
                elif step[i] > 0 and w[i] + step[i] > hi[i] + tol:
                    t = (hi[i] - w[i]) / step[i]
                else:
                    continue
                if t < alpha:
                    alpha, hit = t, i
            w = w + alpha * step
            if hit >= 0:
                w[hit] = lo[hit] if step[hit] < 0 else hi[hit]
                held[hit] = True
                continue
        # At the optimum of the current working set: check the held assets' multipliers.
        g = s @ w
        lam = float(g[~held].mean()) if (~held).any() else float(g.mean())
        # At the lower limit, the gradient must be at least lam; at the upper one, at most.
        at_lo = (held & (w <= lo + tol)).astype(float)
        at_hi = (held & (w >= hi - tol)).astype(float)
        wrong = at_lo * (lam - g) + at_hi * (g - lam)
        worst = int(wrong.argmax())
        if wrong[worst] <= 1e-14 * max(1.0, abs(lam)):
            return w
        held[worst] = False
    raise RuntimeError("active set did not converge")


def kkt_gap(cov: Matrix, w: Vector, lower: float = 0.0, upper: float = 1.0) -> float:
    """Largest violation of the optimality conditions, relative to the gradient's size.

    For a convex problem these conditions are sufficient: zero (to rounding) means optimal.
    """
    s = np.asarray(cov, dtype=float)
    g = s @ w
    tol = 1e-9
    interior = (w > lower + tol) & (w < upper - tol)
    lam = float(g[interior].mean()) if interior.any() else float(np.median(g))
    gaps = np.zeros_like(w)
    gaps[interior] = np.abs(g[interior] - lam)
    at_lo, at_hi = w <= lower + tol, w >= upper - tol
    gaps[at_lo] = np.maximum(lam - g[at_lo], 0)
    gaps[at_hi] = np.maximum(g[at_hi] - lam, 0)
    feasibility = max(abs(float(w.sum()) - 1), float(np.maximum(lower - w, 0).max()))
    return max(float(gaps.max()) / max(float(np.abs(g).max()), 1e-300), feasibility)


def _block_indices(n: int, mean_block: float, rng: np.random.Generator) -> npt.NDArray[np.intp]:
    """Row indices of one stationary-bootstrap resample (blocks wrap around the end)."""
    out = np.empty(n, dtype=np.intp)
    filled = 0
    while filled < n:
        start = int(rng.integers(n))
        length = min(int(rng.geometric(1 / mean_block)), n - filled)
        out[filled : filled + length] = (start + np.arange(length)) % n
        filled += length
    return out


def resampled_weights(
    returns: Any,
    samples: int = 300,
    mean_block: float = 20.0,
    lower: float = 0.0,
    upper: float = 1.0,
    seed: int = 1,
) -> Matrix:
    """Minimum-variance weights on ``samples`` resamples of the returns (``samples x p``).

    Rows of the ``n x p`` return matrix are resampled in blocks (stationary bootstrap), so
    cross-asset correlation and short-term dependence are kept. Each resample gets its own
    Ledoit-Wolf covariance and its own solution. Uses the parallel C++ engine when available.
    """
    x = np.ascontiguousarray(returns, dtype=np.float64)
    n, p = x.shape
    if n < 20:
        raise ValueError("need at least 20 rows")
    _bounds(p, lower, upper)
    fast = core.resampled_min_variance(x, samples, mean_block, lower, upper, seed)
    if fast is not None:
        return fast
    rng = np.random.default_rng(seed)
    out = np.empty((samples, p))
    for k in range(samples):
        cov, _ = _ledoit_wolf_numpy(x[_block_indices(n, mean_block, rng)])
        out[k] = min_variance(cov, lower, upper)
    return out
