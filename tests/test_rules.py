import os

import numpy as np
import pytest

from quant import core
from quant.rules import RULES, RuleParams, backtest_rule, backtest_rule_reference

REQUIRED = bool(os.environ.get("QUANT_REQUIRE_CORE"))


def _prices(days: int = 800, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    vol = np.full(days, 0.01)
    vol[days // 2 + 1 :] = 0.03  # a calm half, then a rough one
    returns = rng.normal(0.0003, 1.0, (days, 3)) * vol[:, None] * np.array([1.0, 0.6, 1.4])
    return 100 * np.cumprod(1 + returns, axis=0)


TARGETS = np.array([0.5, 0.3, 0.2])


def test_hand_example_with_costs() -> None:
    prices = np.array([[1.0, 1.0], [2.0, 1.0], [2.0, 1.0]])
    p = RuleParams(cost=0.01, every=1)

    r = backtest_rule_reference(prices, np.array([0.5, 0.5]), "calendar", p)

    assert r.value[1] == pytest.approx(0.99 * 1.5 - 0.00495)
    assert r.trades == 2
    hold = backtest_rule_reference(prices, np.array([0.5, 0.5]), "buy_and_hold", RuleParams(cost=0))
    assert hold.value[-1] == pytest.approx(1.5)
    assert hold.trades == 0
    assert hold.turnover == 0.0


def test_costs_only_lower_the_value() -> None:
    prices = _prices()
    free = backtest_rule(prices, TARGETS, "calendar", RuleParams(cost=0.0))
    paid = backtest_rule(prices, TARGETS, "calendar", RuleParams(cost=0.002))

    assert (paid.value <= free.value + 1e-12).all()
    assert paid.costs > 0


def test_bands_trade_less_often_than_a_daily_calendar() -> None:
    prices = _prices()

    daily = backtest_rule(prices, TARGETS, "calendar", RuleParams(every=1))
    bands = backtest_rule(prices, TARGETS, "bands", RuleParams(band=0.05))

    assert bands.trades < daily.trades / 10
    assert bands.turnover < daily.turnover


def test_volatility_target_cuts_exposure_when_markets_get_rough() -> None:
    prices = _prices()
    hold = backtest_rule(prices, TARGETS, "buy_and_hold")
    target = backtest_rule(prices, TARGETS, "vol_target", RuleParams(vol_target=0.10))

    def vol(v: np.ndarray) -> float:
        r = v[1:] / v[:-1] - 1
        return float(r.std() * np.sqrt(252))

    rough = slice(500, None)
    assert vol(target.value[rough]) < 0.6 * vol(hold.value[rough])


def test_no_decision_uses_the_future() -> None:
    prices = _prices()
    changed = prices.copy()
    changed[600:] *= 1.5

    for rule in RULES:
        a = backtest_rule(prices, TARGETS, rule).value[:600]
        b = backtest_rule(changed, TARGETS, rule).value[:600]
        assert a == pytest.approx(b), rule


@pytest.mark.skipif(core.BACKEND != "c++" and not REQUIRED, reason="C++ extension not built")
@pytest.mark.parametrize("rule", RULES)
def test_cpp_matches_the_reference(rule: str) -> None:
    prices = _prices()
    p = RuleParams(cost=0.0015, every=10, band=0.04, vol_target=0.12)

    fast = backtest_rule(prices, TARGETS, rule, p)
    slow = backtest_rule_reference(prices, TARGETS, rule, p)

    np.testing.assert_allclose(fast.value, slow.value, rtol=1e-12)
    assert fast.trades == slow.trades
    assert fast.turnover == pytest.approx(slow.turnover, rel=1e-12)


def test_unknown_rule_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown rule"):
        backtest_rule(_prices(10), TARGETS, "momentum")
