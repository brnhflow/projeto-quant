"""Brinson attribution: the gap to a benchmark split into allocation and selection.

Brinson, Hood and Beebower (1986), in the Brinson-Fachler form. With segments ``i``
(here, markets), portfolio weights ``wp`` and returns ``rp``, benchmark weights ``wb`` and
returns ``rb``, and ``Rb = sum(wb * rb)``:

- allocation  ``(wp_i - wb_i) * (rb_i - Rb)``: more weight in markets that beat the benchmark;
- selection   ``wb_i * (rp_i - rb_i)``: your assets against their own market's index;
- interaction ``(wp_i - wb_i) * (rp_i - rb_i)``: both at once.

The three add up exactly to ``sum(wp * rp) - Rb``.

The benchmark's market weights come from returns-based style analysis (Sharpe, 1992): the
long-only weights on the regional indices whose mix best tracks the global index's returns.
No holdings file of the index is needed, and the fit's R² says how good the replica is.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd

Vector = npt.NDArray[np.float64]


def project_to_simplex(v: Vector) -> Vector:
    """Closest point to ``v`` with non-negative entries that add up to one.

    Euclidean projection by sorting (Duchi, Shalev-Shwartz, Singer and Chandra, 2008).
    """
    u = np.asarray(sorted(v.tolist(), reverse=True), dtype=np.float64)
    cumulative = u.cumsum() - 1.0
    k = np.arange(1, len(v) + 1)
    rho = int(np.nonzero(u - cumulative / k > 0)[0][-1])
    theta = cumulative[rho] / (rho + 1)
    return np.maximum(v - theta, 0.0)


def style_weights(target: pd.Series, factors: pd.DataFrame, iterations: int = 20_000) -> pd.Series:
    """Long-only weights summing to one whose mix of ``factors`` best tracks ``target``.

    Minimises ``||target - factors @ w||²`` over the simplex by projected gradient descent,
    with step ``1 / L`` where ``L`` is the largest eigenvalue of ``2 factors' factors``.

    Parameters
    ----------
    target : pd.Series
        Returns of the series to explain (e.g. the global index), no missing values.
    factors : pd.DataFrame
        Returns of the candidates (e.g. regional indices) on the same dates.

    Returns
    -------
    pd.Series
        Weights by factor column.

    """
    x = factors.to_numpy(dtype=np.float64)
    y = target.to_numpy(dtype=np.float64)
    gram = x.T @ x
    lipschitz = 2 * float(np.linalg.eigvalsh(gram).max())
    if lipschitz <= 0:
        raise ValueError("factors have no variation")
    w = np.full(x.shape[1], 1.0 / x.shape[1])
    xty = x.T @ y
    for _ in range(iterations):
        step = project_to_simplex(w - (2 * (gram @ w - xty)) / lipschitz)
        if float(np.abs(step - w).max()) < 1e-12:
            w = step
            break
        w = step
    return pd.Series(w, index=factors.columns)


def style_r2(target: pd.Series, factors: pd.DataFrame, weights: pd.Series) -> float:
    """Share of the target's variance the style mix explains."""
    fitted = factors[weights.index].to_numpy(dtype=np.float64) @ weights.to_numpy(dtype=np.float64)
    residual = target.to_numpy(dtype=np.float64) - fitted
    total = float(((target - target.mean()) ** 2).sum())
    return 1 - float((residual**2).sum()) / total if total > 0 else 0.0


def brinson_fachler(wp: pd.Series, rp: pd.Series, wb: pd.Series, rb: pd.Series) -> pd.DataFrame:
    """Allocation, selection and interaction by segment.

    All four series share the segment index; weights add up to one on each side (a segment
    can have zero weight on one side). ``rp`` of a segment the portfolio does not hold and
    ``rb`` of one the benchmark does not hold are not used by the formulas where their
    weight is zero, but must be numbers.

    Returns
    -------
    pd.DataFrame
        Columns ``allocation``, ``selection``, ``interaction`` and ``total`` by segment.

    """
    total_b = float((wb * rb).sum())
    active = wp - wb
    out = pd.DataFrame(
        {
            "allocation": active * (rb - total_b),
            "selection": wb * (rp - rb),
            "interaction": active * (rp - rb),
        }
    )
    out["total"] = out.sum(axis=1)
    return out
