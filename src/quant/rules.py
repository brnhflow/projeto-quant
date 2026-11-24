"""Walk-forward backtests of allocation rules, with trading costs.

Four rules on the same assets and target weights:

- ``buy_and_hold``: buy the targets on day 0 and never trade;
- ``calendar``: trade back to the targets every ``every`` trading days;
- ``bands``: trade back to the targets when any weight drifts more than ``band`` from target;
- ``vol_target``: every ``every`` days, set the share invested so the risky part's EWMA
  volatility forecast matches ``vol_target`` (the rest in cash, no leverage).

Every trade pays ``cost`` times the amount traded. Decisions at a close use only prices up to
that close. This module is the reference; ``cpp/include/quant/backtest.hpp`` runs the same loop
in C++ and :func:`backtest_rules` uses it when the extension is built.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from quant import core

RULES = ("buy_and_hold", "calendar", "bands", "vol_target")


@dataclass(frozen=True)
class RuleParams:
    """Settings shared by the rules (each rule reads the ones it needs)."""

    cost: float = 0.001
    every: int = 21
    band: float = 0.05
    vol_target: float = 0.10
    lam: float = 0.94
    seed: int = 30


@dataclass(frozen=True)
class RuleResult:
    """Daily value (starting at 1), turnover, costs paid and number of rebalancing days."""

    value: npt.NDArray[np.float64]
    turnover: float
    costs: float
    trades: int


def backtest_rule_reference(
    prices: npt.NDArray[np.float64], targets: npt.NDArray[np.float64], rule: str, p: RuleParams
) -> RuleResult:
    """Run one rule day by day in Python; see the module docstring."""
    days, assets = prices.shape
    if len(targets) != assets or days < 2:
        raise ValueError("prices must be days x assets and targets one per asset")
    units = np.zeros(assets)
    state = {"cash": 0.0, "exposure": 1.0, "turnover": 0.0, "costs": 0.0, "trades": 0}

    def rebalance(t: int, value: float) -> float:
        row = prices[t]
        exposure = state["exposure"]
        traded = 0.0
        for i in range(assets):
            want = value * exposure * targets[i] / row[i]
            traded += abs(want - units[i]) * row[i]
        fee = traded * p.cost
        after = value - fee
        invested = 0.0
        for i in range(assets):
            units[i] = after * exposure * targets[i] / row[i]
            invested += units[i] * row[i]
        state["cash"] = after - invested
        state["turnover"] += traded / value
        state["costs"] += fee
        state["trades"] += 1
        return after

    out = np.empty(days)
    value = rebalance(0, 1.0)
    state["trades"] = 0  # the initial purchase costs, but is not a rebalance or turnover
    state["turnover"] = 0.0
    out[0] = value
    variance, last_value = 0.0, 1.0
    for t in range(1, days):
        row = prices[t]
        value = state["cash"]
        for i in range(assets):
            value += units[i] * row[i]
        r = value / last_value - 1.0
        last_value = value
        if t - 1 < p.seed:  # the first `seed` returns start the variance
            variance += r * r / p.seed
        else:
            variance = p.lam * variance + (1.0 - p.lam) * (r * r)
        trade = False
        if rule == "calendar":
            trade = t % p.every == 0
        elif rule == "bands":
            trade = any(abs(units[i] * row[i] / value - targets[i]) > p.band for i in range(assets))
        elif rule == "vol_target" and t % p.every == 0 and t >= p.seed:
            risky = math.sqrt(variance * 252.0) / max(state["exposure"], 1e-9)
            state["exposure"] = min(1.0, p.vol_target / max(risky, 1e-9))
            trade = True
        if trade:
            value = rebalance(t, value)
            last_value = value
        out[t] = value
    return RuleResult(out, state["turnover"], state["costs"], int(state["trades"]))


def backtest_rule(
    prices: Any, targets: Any, rule: str, params: RuleParams | None = None
) -> RuleResult:
    """Run one rule, in C++ when the extension is built (same results; tests/test_rules.py)."""
    if rule not in RULES:
        raise ValueError(f"unknown rule {rule!r}; use one of {RULES}")
    p = params or RuleParams()
    x = np.ascontiguousarray(prices, dtype=np.float64)
    w = np.ascontiguousarray(targets, dtype=np.float64)
    fast = core.backtest_rule(x, w, RULES.index(rule), p)
    if fast is not None:
        return RuleResult(fast[0], fast[1], fast[2], fast[3])
    return backtest_rule_reference(x, w, rule, p)
