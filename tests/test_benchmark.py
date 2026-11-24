import numpy as np
import pandas as pd
import pytest

from quant.benchmark import compare

DAYS = pd.bdate_range("2024-01-01", periods=500)


def _prices(returns: np.ndarray) -> pd.Series:
    return pd.Series(100 * np.cumprod(1 + returns), index=DAYS)


def _market(seed: int = 1) -> np.ndarray:
    return np.random.default_rng(seed).normal(0.0004, 0.01, len(DAYS))


def test_the_benchmark_against_itself() -> None:
    market = _prices(_market())

    s = compare(market, market)

    assert s.beta == pytest.approx(1.0)
    assert s.alpha == pytest.approx(0.0, abs=1e-12)
    assert s.correlation == pytest.approx(1.0)
    assert s.tracking_error == pytest.approx(0.0, abs=1e-12)
    assert s.information_ratio is None
    assert s.up_capture == pytest.approx(1.0)
    assert s.down_capture == pytest.approx(1.0)


def test_a_leveraged_portfolio_has_beta_two_and_no_alpha() -> None:
    r = _market()

    s = compare(_prices(2 * r), _prices(r))

    assert s.beta == pytest.approx(2.0)
    assert s.alpha == pytest.approx(0.0, abs=1e-12)
    assert s.up_capture == pytest.approx(2.0)
    assert s.down_capture == pytest.approx(2.0)
    # Excess returns are the market itself: tracking error is the market's volatility.
    assert s.tracking_error == pytest.approx(r[1:].std(ddof=1) * np.sqrt(252))


def test_a_constant_daily_edge_is_alpha() -> None:
    r = _market()
    edge = 0.0002  # 0.02% a day on top of the market

    s = compare(_prices(r + edge), _prices(r))

    assert s.beta == pytest.approx(1.0)
    assert s.alpha == pytest.approx(edge * 252)
    assert s.portfolio_return > s.benchmark_return


def test_information_ratio_matches_its_definition() -> None:
    rng = np.random.default_rng(3)
    r = _market()
    p = 0.8 * r + rng.normal(0.0001, 0.004, len(r))

    s = compare(_prices(p), _prices(r))

    excess = pd.Series(p[1:] - r[1:])
    te = excess.std() * np.sqrt(252)
    assert s.tracking_error == pytest.approx(te)
    assert s.information_ratio == pytest.approx(excess.mean() * 252 / te)
    assert s.days == len(DAYS) - 1


def test_compare_uses_common_dates_only() -> None:
    market = _prices(_market())
    late = market.iloc[100:]

    assert compare(late, market).days == len(late) - 1


def test_compare_rejects_short_or_flat_inputs() -> None:
    market = _prices(_market())
    with pytest.raises(ValueError):
        compare(market.iloc[:10], market.iloc[:10])
    with pytest.raises(ValueError):
        compare(market, pd.Series(100.0, index=DAYS))
