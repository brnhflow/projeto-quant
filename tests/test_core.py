"""The C++ kernels against the NumPy reference.

Skipped when the extension is not built (``uv pip install ./cpp``). CI builds it and sets
``QUANT_REQUIRE_CORE=1``, so there a missing extension is a failure, not a skip.
"""

import os

import numpy as np
import pandas as pd
import pytest

from quant import core
from quant.validation import rolling_var

REQUIRED = bool(os.environ.get("QUANT_REQUIRE_CORE"))
needs_core = pytest.mark.skipif(
    core.BACKEND != "c++" and not REQUIRED, reason="C++ extension not built"
)


def _returns(n: int = 3000, seed: int = 1) -> pd.Series:
    rng = np.random.default_rng(seed)
    values = rng.standard_t(4, n) * 0.01
    return pd.Series(values, index=pd.bdate_range("2010-01-01", periods=n))


def test_backend_is_reported() -> None:
    assert core.BACKEND in {"c++", "numpy"}
    if REQUIRED:
        assert core.BACKEND == "c++"


@needs_core
@pytest.mark.parametrize("level", [0.95, 0.99])
def test_historical_var_matches_numpy_exactly(level: float) -> None:
    r = _returns()

    fast = core.historical_var(r.to_numpy(), 250, level)
    reference = rolling_var(r, 250, level)["var"].to_numpy()

    assert fast is not None
    assert np.isnan(fast[:250]).all()
    assert (fast[250:] == reference).all()


@needs_core
def test_ewma_and_filtered_var_match_numpy_to_rounding() -> None:
    r = _returns().to_numpy()
    sigma = core.ewma_volatility(r, 0.94, 30)
    assert sigma is not None

    variance = float((r[:30] ** 2).mean())
    expected = np.full(len(r), np.nan)
    for t in range(30, len(r)):
        expected[t] = np.sqrt(variance)
        variance = 0.94 * variance + (1 - 0.94) * r[t] ** 2
    # NumPy sums the seed in pairs, C++ in sequence: equal to rounding, not bit for bit.
    np.testing.assert_allclose(sigma[30:], expected[30:], rtol=1e-12)

    fhs = core.filtered_historical_var(r, 250, 0.99, 0.94, 30)
    assert fhs is not None
    z = r / expected
    k = 2  # floor(249 * 0.01)
    reference = [-sorted(z[t - 250 : t].tolist())[k] * expected[t] for t in range(280, len(r))]
    np.testing.assert_allclose(fhs[280:], np.array(reference), rtol=1e-12)


@needs_core
def test_bootstrap_agrees_with_numpy_in_distribution() -> None:
    r = _returns(1500).to_numpy()

    fast = core.bootstrap_statistics(r, 4000, 20.0, 7)
    assert fast.shape == (4000, 4)
    # Same statistics from the NumPy engine (forced): compare the 5%, 50% and 95% quantiles.
    saved, core._core = core._core, None  # pyright: ignore[reportPrivateUsage]
    try:
        slow = core.bootstrap_statistics(r, 4000, 20.0, 7)
    finally:
        core._core = saved  # pyright: ignore[reportPrivateUsage]
    for column in range(4):
        q_fast = pd.Series(fast[:, column]).quantile([0.05, 0.5, 0.95]).to_numpy()
        q_slow = pd.Series(slow[:, column]).quantile([0.05, 0.5, 0.95]).to_numpy()
        spread = q_slow[2] - q_slow[0]
        assert np.abs(q_fast - q_slow).max() < 0.1 * spread


def test_numpy_bootstrap_of_constant_returns_is_exact() -> None:
    r = np.full(252, 0.001)

    stats = core.bootstrap_statistics(r, 30, 10.0, 1)

    assert stats[:, 0] == pytest.approx(1.001**252 - 1)
    assert stats[:, 1] == pytest.approx(0.0, abs=1e-9)
    assert stats[:, 3] == pytest.approx(-0.001)


@needs_core
def test_simulation_agrees_with_numpy_in_distribution() -> None:
    from quant.simulation import simulate_growth

    r = _returns(1000).to_numpy()
    fast = simulate_growth(r, 252, 3000, demean=True, seed=3)
    saved, core._core = core._core, None  # pyright: ignore[reportPrivateUsage]
    try:
        slow = simulate_growth(r, 252, 3000, demean=True, seed=3)
    finally:
        core._core = saved  # pyright: ignore[reportPrivateUsage]
    q_fast = pd.Series(fast[:, -1]).quantile([0.05, 0.5, 0.95]).to_numpy()
    q_slow = pd.Series(slow[:, -1]).quantile([0.05, 0.5, 0.95]).to_numpy()
    assert fast.shape == slow.shape == (3000, 252)
    assert np.abs(q_fast - q_slow).max() < 0.1 * (q_slow[2] - q_slow[0])
