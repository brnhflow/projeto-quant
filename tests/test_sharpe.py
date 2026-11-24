import math
from statistics import NormalDist

import pytest

from quant.sharpe import deflated_sharpe, expected_max_sharpe, probabilistic_sharpe


def test_psr_is_one_half_at_the_benchmark() -> None:
    assert probabilistic_sharpe(0.05, 500, -0.5, 6.0, benchmark=0.05) == pytest.approx(0.5)


def test_psr_of_normal_returns_matches_the_closed_form() -> None:
    sr, n = 0.06, 1000

    psr = probabilistic_sharpe(sr, n, 0.0, 3.0)

    expected = NormalDist().cdf(sr * math.sqrt(n - 1) / math.sqrt(1 + sr**2 / 2))
    assert psr == pytest.approx(expected)


def test_more_data_and_thinner_tails_raise_confidence() -> None:
    assert probabilistic_sharpe(0.05, 2000, 0, 3) > probabilistic_sharpe(0.05, 200, 0, 3)
    # Negative skew and fat tails make the same Sharpe less convincing.
    assert probabilistic_sharpe(0.05, 500, -1.0, 10.0) < probabilistic_sharpe(0.05, 500, 0, 3)


def test_expected_maximum_grows_with_the_number_of_trials() -> None:
    values = [expected_max_sharpe(n, 0.01) for n in (2, 10, 100, 1000)]

    assert values == sorted(values)
    assert expected_max_sharpe(10, 0.0) == 0.0


def test_expected_maximum_is_close_to_the_exact_value() -> None:
    # The best of 20 standard normals averages 1.8675 (exact, by numerical integration); the
    # closed-form approximation of Bailey and Lopez de Prado gives 1.90, within 2%.
    assert expected_max_sharpe(20, 1.0) == pytest.approx(1.8675, rel=0.02)


def test_deflating_for_many_trials_lowers_the_probability() -> None:
    sr, n = 0.06, 750
    few = deflated_sharpe(sr, n, 0.0, 3.0, [0.06, 0.04])
    many = deflated_sharpe(sr, n, 0.0, 3.0, [0.06, 0.04, 0.05, 0.02, 0.03, 0.055, 0.01, 0.045])

    assert many < few <= probabilistic_sharpe(sr, n, 0.0, 3.0)


def test_invalid_input_is_refused() -> None:
    with pytest.raises(ValueError):
        probabilistic_sharpe(0.05, 1, 0, 3)
    with pytest.raises(ValueError):
        expected_max_sharpe(1, 0.01)
