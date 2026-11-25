"""Measure the C++ kernels against the NumPy reference on the same inputs.

Run: uv run python research/benchmark.py   (with the extension built: uv pip install ./cpp)
Prints one line per kernel: median time over repeats for each backend and the speed-up.
CI runs it on every push, so the numbers in the README come from a log anyone can open.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

import numpy as np
import pandas as pd

from quant import core
from quant.validation import rolling_var


def timed(fn: Callable[[], object], repeats: int = 5) -> float:
    """Median wall time of ``fn`` in milliseconds."""
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    return float(np.median(times))


def main() -> int:
    """Time each kernel with the C++ engine and with NumPy."""
    rng = np.random.default_rng(0)
    r = pd.Series(
        rng.standard_t(4, 20_000) * 0.01, index=pd.bdate_range("1950-01-02", periods=20_000)
    )
    x = r.to_numpy()
    print(f"backend: {core.BACKEND}; 20,000 daily returns (about 80 years)")
    if core.BACKEND != "c++":
        print("C++ extension not built: run `uv pip install ./cpp` first")
        return 0

    def numpy_fhs() -> None:
        sigma = np.full(len(x), np.nan)
        variance = float((x[:30] ** 2).mean())
        for t in range(30, len(x)):
            sigma[t] = variance**0.5
            variance = 0.94 * variance + 0.06 * x[t] ** 2
        z = x / sigma
        for t in range(280, len(x)):
            np.partition(z[t - 250 : t], 12)

    saved = core._core  # pyright: ignore[reportPrivateUsage]

    def numpy_bootstrap() -> None:
        core._core = None  # pyright: ignore[reportPrivateUsage]
        try:
            core.bootstrap_statistics(x[:2500], 2000, 20.0, 1)
        finally:
            core._core = saved  # pyright: ignore[reportPrivateUsage]

    from quant.simulation import simulate_growth

    def numpy_simulation() -> None:
        core._core = None  # pyright: ignore[reportPrivateUsage]
        try:
            simulate_growth(x[:2500], 1260, 2000, demean=True)
        finally:
            core._core = saved  # pyright: ignore[reportPrivateUsage]

    from quant.risk import _ledoit_wolf_numpy  # pyright: ignore[reportPrivateUsage]

    small = np.ascontiguousarray(x[:7500].reshape(750, 10))
    wide = np.ascontiguousarray(x[:15000].reshape(300, 50))

    cases = [
        (
            "rolling historical VaR (250d)",
            lambda: rolling_var(r, 250, 0.95),
            lambda: core.historical_var(x, 250, 0.95),
        ),
        (
            "filtered historical VaR",
            numpy_fhs,
            lambda: core.filtered_historical_var(x, 250, 0.95, 0.94, 30),
        ),
        (
            "stationary bootstrap, 2,000 x 2,500 days",
            numpy_bootstrap,
            lambda: core.bootstrap_statistics(x[:2500], 2000, 20.0, 1),
        ),
        (
            "Monte Carlo, 2,000 paths x 5 years",
            numpy_simulation,
            lambda: simulate_growth(x[:2500], 1260, 2000, demean=True),
        ),
        (
            "Ledoit-Wolf, 750 days x 10 assets",
            lambda: _ledoit_wolf_numpy(small),
            lambda: core.ledoit_wolf(small),
        ),
        (
            "Ledoit-Wolf, 300 days x 50 assets",
            lambda: _ledoit_wolf_numpy(wide),
            lambda: core.ledoit_wolf(wide),
        ),
    ]
    for name, slow, fast in cases:
        t_slow, t_fast = timed(slow), timed(fast)
        print(f"{name:<42} numpy {t_slow:9.1f} ms   c++ {t_fast:8.1f} ms   x{t_slow / t_fast:6.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
