import numpy as np
import pandas as pd
import pytest

from quant.brinson import brinson_fachler, project_to_simplex, style_r2, style_weights


def test_projection_lands_on_the_simplex_and_keeps_points_already_there() -> None:
    inside = np.array([0.2, 0.3, 0.5])
    assert project_to_simplex(inside) == pytest.approx(inside)
    projected = project_to_simplex(np.array([2.0, -1.0, 0.5]))
    assert projected.sum() == pytest.approx(1.0)
    assert (projected >= 0).all()
    assert projected == pytest.approx([1.0, 0.0, 0.0])


def test_style_weights_recover_a_known_mix() -> None:
    rng = np.random.default_rng(5)
    factors = pd.DataFrame(rng.normal(0, 0.02, (300, 3)), columns=["US", "EU", "BR"])
    target = 0.6 * factors["US"] + 0.4 * factors["EU"]

    w = style_weights(target, factors)

    assert w.to_dict() == pytest.approx({"US": 0.6, "EU": 0.4, "BR": 0.0}, abs=1e-6)
    assert style_r2(target, factors, w) == pytest.approx(1.0)


def test_style_weights_stay_long_only_when_the_best_fit_would_short() -> None:
    rng = np.random.default_rng(6)
    factors = pd.DataFrame(rng.normal(0, 0.02, (300, 2)), columns=["A", "B"])
    target = 1.5 * factors["A"] - 0.5 * factors["B"]

    w = style_weights(target, factors)

    assert w.min() >= 0
    assert w.sum() == pytest.approx(1.0)
    assert w["A"] == pytest.approx(1.0, abs=1e-6)


def test_brinson_effects_add_up_to_the_gap() -> None:
    # Textbook example: overweight the market that did better, and pick well inside it.
    segments = ["US", "EU", "Cash"]
    wp = pd.Series([0.7, 0.2, 0.1], index=segments)
    wb = pd.Series([0.6, 0.4, 0.0], index=segments)
    rp = pd.Series([0.12, 0.03, 0.0], index=segments)
    rb = pd.Series([0.10, 0.05, 0.0], index=segments)

    effects = brinson_fachler(wp, rp, wb, rb)

    total_b = 0.6 * 0.10 + 0.4 * 0.05
    assert effects["allocation"]["US"] == pytest.approx(0.1 * (0.10 - total_b))
    assert effects["selection"]["US"] == pytest.approx(0.6 * 0.02)
    assert effects["interaction"]["EU"] == pytest.approx(-0.2 * -0.02)
    assert effects["allocation"]["Cash"] == pytest.approx(0.1 * (0.0 - total_b))
    assert effects["total"].sum() == pytest.approx(float((wp * rp).sum()) - total_b)
