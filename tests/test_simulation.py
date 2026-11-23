# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
import math

import numpy as np
import pandas as pd
import pytest

from quant.simulation import (
    calibrate,
    drawdown_probability,
    quantile_table,
    simulate_growth,
)


def _normal(n: int, sd: float = 0.01, mean: float = 0.0, seed: int = 1) -> np.ndarray:
    return np.random.default_rng(seed).normal(mean, sd, n)


def test_no_trend_simulation_matches_the_lognormal_answer() -> None:
    # i.i.d. daily log returns with sd 1%: after 252 days the log growth is about
    # normal with sd 0.01 * sqrt(252), centred on zero once the trend is removed.
    growth = simulate_growth(np.expm1(_normal(2000)), 252, 4000, demean=True, seed=3)

    final = np.log(growth[:, -1])
    assert final.mean() == pytest.approx(0.0, abs=0.01)
    assert final.std() == pytest.approx(0.01 * math.sqrt(252), rel=0.08)
    q5, q50, q95 = quantile_table(growth, (0.05, 0.5, 0.95))[:, -1]
    assert q50 == pytest.approx(1.0, abs=0.02)
    assert q5 == pytest.approx(math.exp(-1.645 * 0.01 * math.sqrt(252)), rel=0.05)
    assert q95 == pytest.approx(math.exp(1.645 * 0.01 * math.sqrt(252)), rel=0.05)


def test_trend_is_kept_only_when_asked() -> None:
    history = np.expm1(_normal(1500, mean=0.0008))  # about +22% a year

    neutral = simulate_growth(history, 252, 2000, demean=True, seed=1)
    trend = simulate_growth(history, 252, 2000, demean=False, seed=1)

    gap = np.log(trend[:, -1]).mean() - np.log(neutral[:, -1]).mean()
    assert gap == pytest.approx(np.log1p(history).mean() * 252, rel=1e-6)


def test_simulation_is_reproducible_and_shaped_by_paths_and_days() -> None:
    history = np.expm1(_normal(300))

    a = simulate_growth(history, 600, 50, demean=True, seed=9)  # longer than the history
    b = simulate_growth(history, 600, 50, demean=True, seed=9)

    assert a.shape == (50, 600)
    np.testing.assert_array_equal(a, b)


def test_simulation_rejects_bad_history() -> None:
    with pytest.raises(ValueError):
        simulate_growth(np.array([0.01] * 10), 10, 10, demean=True)
    with pytest.raises(ValueError):
        simulate_growth(np.array([0.01] * 30 + [-1.0]), 10, 10, demean=True)


def test_drawdown_probability_on_known_paths() -> None:
    growth = np.array(
        [
            [1.1, 0.95, 1.2],  # peak 1.1 then 0.95: -13.6%
            [0.7, 0.8, 0.9],  # from the starting 1.0 to 0.7: -30%
            [1.0, 1.05, 1.1],  # never falls
        ]
    )

    assert drawdown_probability(growth, 0.10) == pytest.approx(2 / 3)
    assert drawdown_probability(growth, 0.20) == pytest.approx(1 / 3)
    assert drawdown_probability(growth, 0.50) == 0.0


def test_calibration_passes_when_the_world_does_not_change() -> None:
    returns = pd.Series(_normal(252 + 21 * 40, seed=4))

    result = calibrate(returns, paths=500)

    assert result.checks == 40
    assert 0.75 <= result.coverage <= 1.0
    assert result.p_value > 0.01


def test_calibration_fails_when_the_future_breaks_from_the_past() -> None:
    # Calm months, then a steady slide of -1% every day: each month ends about -19%,
    # far outside any range drawn from the calm past. The method must report it.
    calm = _normal(252 + 21 * 4, sd=0.004, seed=5)
    slide = np.full(21 * 12, -0.01)
    returns = pd.Series(np.concatenate([calm, slide]))

    result = calibrate(returns, paths=500)

    assert result.checks == 16
    assert result.coverage <= 4 / 16 + 1e-9
    assert result.p_value < 0.001


def test_calibration_needs_enough_months() -> None:
    with pytest.raises(ValueError):
        calibrate(pd.Series(_normal(300)))
