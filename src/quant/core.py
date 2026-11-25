"""Bridge to the C++ risk kernels (``cpp/``), with the NumPy implementation as fallback.

The extension ``quant_core`` is optional: build it with ``uv pip install ./cpp`` (needs a C++20
compiler and CMake). When it is missing or cannot be loaded, every function here runs the
pure Python/NumPy reference, which gives the same numbers: the rolling historical VaR bit
for bit, the EWMA-based kernels to 1e-12 (tests/test_core.py).

``BACKEND`` says which one is in use: ``"c++"`` or ``"numpy"``.
"""

from __future__ import annotations

import importlib
import os
from types import ModuleType
from typing import Any

import numpy as np
import numpy.typing as npt

Vector = npt.NDArray[np.float64]


def _load() -> ModuleType | None:
    if os.environ.get("QUANT_NO_CORE"):
        return None
    try:
        return importlib.import_module("quant_core")
    except ImportError:  # not built, or blocked by the OS (e.g. unsigned DLL policies)
        return None


_core: Any = _load()
BACKEND = "c++" if _core is not None else "numpy"


def _vector(x: Any) -> Vector:
    return np.ascontiguousarray(x, dtype=np.float64)


def historical_var(returns: Any, window: int, level: float) -> Vector | None:
    """C++ rolling historical VaR (NaN before ``window``), or None without the extension."""
    if _core is None:
        return None
    return np.asarray(_core.historical_var(_vector(returns), window, level), dtype=np.float64)


def ewma_volatility(returns: Any, lam: float, seed: int) -> Vector | None:
    """C++ EWMA volatility forecast, or None without the extension."""
    if _core is None:
        return None
    return np.asarray(_core.ewma_volatility(_vector(returns), lam, seed), dtype=np.float64)


def filtered_historical_var(
    returns: Any, window: int, level: float, lam: float, seed: int
) -> Vector | None:
    """C++ filtered historical simulation VaR, or None without the extension."""
    if _core is None:
        return None
    out = _core.filtered_historical_var(_vector(returns), window, level, lam, seed)
    return np.asarray(out, dtype=np.float64)


def bootstrap_statistics(
    returns: Any, samples: int, mean_block: float, seed: int
) -> npt.NDArray[np.float64]:
    """Stationary-bootstrap statistics: ``samples x [annual return, volatility, Sharpe, VaR 95%]``.

    Uses the C++ engine when available; otherwise the same algorithm in NumPy. The two use
    different random generators, so they agree in distribution, not draw by draw.
    """
    r = _vector(returns)
    if _core is not None:
        return np.asarray(
            _core.stationary_bootstrap(r, samples, mean_block, seed), dtype=np.float64
        )
    from quant.validation import stationary_bootstrap_matrix

    rng = np.random.default_rng(seed)
    n = len(r)
    paths = r[stationary_bootstrap_matrix(n, mean_block, rng, samples)]
    k = int(np.floor(np.round((n - 1) * 0.05, 9)))
    growth: Vector = (1 + paths).prod(axis=1)
    sd: Vector = paths.std(axis=1, ddof=1)
    mean: Vector = paths.mean(axis=1)
    out = np.empty((samples, 4), dtype=np.float64)
    out[:, 0] = np.abs(growth) ** (252 / n) - 1
    out[growth <= 0, 0] = -1.0
    safe = sd.copy()
    safe[safe <= 1e-12] = np.inf  # no variation: Sharpe 0, as in C++
    out[:, 1] = sd * np.sqrt(252)
    out[:, 2] = mean / safe * np.sqrt(252)
    ordered = paths.copy()
    ordered.partition(k, axis=1)
    out[:, 3] = -ordered[:, k]
    return out


def backtest_rule(
    prices: Vector, targets: Vector, rule: int, params: Any
) -> tuple[Vector, float, float, int] | None:
    """C++ backtest of one allocation rule (see quant.rules), or None without the extension."""
    if _core is None:
        return None
    value, turnover, costs, trades = _core.backtest_rule(
        prices,
        targets,
        rule,
        params.cost,
        params.every,
        params.band,
        params.vol_target,
        params.lam,
        params.seed,
    )
    return np.asarray(value, dtype=np.float64), float(turnover), float(costs), int(trades)


def simulate_growth(
    logs: Vector, days: int, paths: int, mean_block: float, seed: int
) -> npt.NDArray[np.float64] | None:
    """C++ Monte Carlo growth paths (paths x days), or None without the extension."""
    if _core is None:
        return None
    out = _core.simulate_growth(_vector(logs), days, paths, mean_block, seed)
    return np.asarray(out, dtype=np.float64)


def ledoit_wolf(returns: npt.NDArray[np.float64]) -> tuple[npt.NDArray[np.float64], float] | None:
    """C++ Ledoit-Wolf covariance and shrinkage from an ``n x p`` matrix, or None without it."""
    if _core is None:
        return None
    matrix, shrinkage = _core.ledoit_wolf(np.ascontiguousarray(returns, dtype=np.float64))
    return np.asarray(matrix, dtype=np.float64), float(shrinkage)
