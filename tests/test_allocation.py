import os

import numpy as np
import pytest

from quant import core
from quant.allocation import kkt_gap, min_variance, resampled_weights
from quant.risk import _ledoit_wolf_numpy  # pyright: ignore[reportPrivateUsage]

needs_core = pytest.mark.skipif(
    core.BACKEND != "c++" and not os.environ.get("QUANT_REQUIRE_CORE"),
    reason="C++ extension not built",
)


def _cov(p: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(p, p))
    vols = rng.uniform(0.1, 0.4, p)
    corr = a @ a.T
    d = np.sqrt(corr.diagonal())
    corr = corr / np.outer(d, d)
    return np.outer(vols, vols) * (0.5 * corr + 0.5 * np.eye(p))


def _returns(n: int, p: int, seed: int = 4) -> np.ndarray:
    rng = np.random.default_rng(seed)
    mix = np.eye(p) + rng.normal(size=(p, p)) * 0.3
    return rng.standard_t(5, size=(n, p)) @ mix * 0.01


def test_two_assets_match_the_closed_form() -> None:
    s = np.array([[0.04, 0.006], [0.006, 0.01]])

    w = min_variance(s)

    expected = (0.01 - 0.006) / (0.04 + 0.01 - 2 * 0.006)
    assert w == pytest.approx([expected, 1 - expected], abs=1e-14)


def test_interior_solution_matches_the_unconstrained_formula() -> None:
    # Nearly uncorrelated, similar variances: no weight hits zero, so the answer is
    # S^-1 1 / (1' S^-1 1).
    s = np.eye(4) * np.array([0.04, 0.05, 0.06, 0.045]) + 0.002

    w = min_variance(s)

    inv = np.linalg.solve(s, np.ones(4))
    assert w == pytest.approx(inv / inv.sum(), abs=1e-14)


def test_limits_bind_and_the_kkt_conditions_hold() -> None:
    s = _cov(8)

    free = min_variance(s)
    capped = min_variance(s, 0.0, 0.2)
    floored = min_variance(s, 0.05, 0.3)

    assert capped.max() <= 0.2 + 1e-12 and free.max() > 0.2
    assert floored.min() >= 0.05 - 1e-12
    for w, lo, hi in ((free, 0.0, 1.0), (capped, 0.0, 0.2), (floored, 0.05, 0.3)):
        assert w.sum() == pytest.approx(1.0, abs=1e-12)
        assert kkt_gap(s, w, lo, hi) < 1e-10


def test_the_optimum_beats_random_feasible_portfolios() -> None:
    s = _cov(6, seed=3)
    w = min_variance(s, 0.0, 0.35)
    best = float(w @ s @ w)
    rng = np.random.default_rng(1)

    for _ in range(2000):
        v = rng.dirichlet(np.ones(6))
        if v.max() <= 0.35:
            assert float(v @ s @ v) >= best - 1e-15


def test_impossible_limits_are_refused() -> None:
    with pytest.raises(ValueError):
        min_variance(np.eye(3), 0.0, 0.3)  # three assets cannot reach 100% at 30% each
    with pytest.raises(ValueError):
        min_variance(np.eye(3), 0.4, 1.0)


def test_resampled_weights_spread_around_the_full_sample_answer() -> None:
    x = _returns(500, 5)
    full = min_variance(_ledoit_wolf_numpy(x)[0])

    draws = resampled_weights(x, samples=200, mean_block=10, seed=3)

    assert draws.shape == (200, 5)
    assert np.abs(draws.sum(axis=1) - 1).max() < 1e-9
    assert (draws >= -1e-12).all()
    # The full-sample answer sits inside the middle 90% of the resamples for every asset.
    ordered = draws.copy()
    ordered.sort(axis=0)
    lo, hi = ordered[10], ordered[189]
    assert ((full >= lo - 1e-9) & (full <= hi + 1e-9)).all()


def test_more_data_gives_more_stable_weights() -> None:
    short = resampled_weights(_returns(120, 5, seed=8), samples=150, seed=2)
    long = resampled_weights(_returns(2000, 5, seed=8), samples=150, seed=2)

    assert long.std(axis=0).mean() < short.std(axis=0).mean()


@needs_core
def test_cpp_solver_matches_the_active_set() -> None:
    for seed in range(5):
        s = _cov(10, seed)
        for lo, hi in ((0.0, 1.0), (0.0, 0.15), (0.02, 0.25)):
            fast = core.min_variance(s, lo, hi)
            assert fast is not None
            assert fast == pytest.approx(min_variance(s, lo, hi), abs=1e-8)
            assert kkt_gap(s, fast, lo, hi) < 1e-7


@needs_core
def test_cpp_resampling_agrees_with_numpy_in_distribution() -> None:
    x = _returns(400, 4)
    fast = core.resampled_min_variance(x, 400, 10.0, 0.0, 1.0, 1)
    saved = core._core  # pyright: ignore[reportPrivateUsage]
    core._core = None  # pyright: ignore[reportPrivateUsage]
    try:
        slow = resampled_weights(x, samples=400, mean_block=10, seed=1)
    finally:
        core._core = saved  # pyright: ignore[reportPrivateUsage]

    assert fast is not None
    np.testing.assert_allclose(fast.mean(axis=0), slow.mean(axis=0), atol=0.02)
    np.testing.assert_allclose(fast.std(axis=0), slow.std(axis=0), rtol=0.25, atol=0.005)
