"""Rebalancing maths runs in the browser; test it with Node when Node is installed."""

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest

SCRIPT = Path(__file__).parents[1] / "src" / "quant" / "report" / "rebalance.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js not installed")


def _call(function: str, *args: Any) -> Any:
    assert NODE is not None
    code = (
        f"const r = require({json.dumps(str(SCRIPT))});"
        f"console.log(JSON.stringify(r.{function}(...{json.dumps(list(args))})));"
    )
    out = subprocess.run([NODE, "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


# ---------------------------------------------------------------- risk


def test_volatility_matches_numpy() -> None:
    cov = [[0.04, 0.006], [0.006, 0.09]]
    w = [0.6, 0.4]

    expected = math.sqrt(float(np.array(w) @ np.array(cov) @ np.array(w)))

    assert _call("portfolioVol", cov, w) == pytest.approx(expected)


def test_risk_shares_sum_to_one_and_match_the_formula() -> None:
    cov = np.array([[0.04, 0.006, 0.0], [0.006, 0.09, 0.01], [0.0, 0.01, 0.16]])
    w = np.array([0.5, 0.3, 0.2])
    expected = w * (cov @ w) / (w @ cov @ w)

    shares = _call("riskShares", cov.tolist(), w.tolist())

    assert shares == pytest.approx(expected.tolist())
    assert sum(shares) == pytest.approx(1.0)


def test_risk_parity_with_independent_assets_is_inverse_volatility() -> None:
    # Known answer: with no correlation, equal risk means weights proportional to 1/vol.
    vols = np.array([0.1, 0.2, 0.4])
    cov = np.eye(3) * vols**2

    weights = _call("riskParity", cov.tolist())

    expected = (1 / vols) / (1 / vols).sum()
    assert weights == pytest.approx(expected.tolist(), abs=1e-9)


def test_risk_parity_equalises_contributions_with_correlation() -> None:
    cov = np.array([[0.04, 0.03, 0.0], [0.03, 0.09, 0.02], [0.0, 0.02, 0.25]])

    weights = np.array(_call("riskParity", cov.tolist()))

    contributions = weights * (cov @ weights)
    assert weights.sum() == pytest.approx(1.0)
    assert contributions == pytest.approx([contributions.mean()] * 3, rel=1e-6)


def test_risk_parity_gives_no_weight_to_a_riskless_asset() -> None:
    cov = [[0.04, 0.0], [0.0, 0.0]]

    assert _call("riskParity", cov) == pytest.approx([1.0, 0.0])


# ---------------------------------------------------------------- trades

POSITIONS = [
    {"asset": "A", "value": 6000.0, "priceBase": 100.0, "kind": "security"},
    {"asset": "B", "value": 3000.0, "priceBase": 30.0, "kind": "security"},
    {"asset": "BTC", "value": 1000.0, "priceBase": 50000.0, "kind": "crypto"},
]


def _plan(**options: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "positions": POSITIONS,
        "targets": {"A": 0.5, "B": 0.4, "BTC": 0.1},
        "mode": "full",
        "contribution": 0,
        "costPct": 0,
        "fixedFee": 0,
        "band": 0,
        "wholeUnits": False,
    }
    base.update(options)
    return _call("planTrades", base)


def test_full_rebalance_reaches_the_targets_and_balances_cash() -> None:
    plan = _plan()

    trades = {t["asset"]: t for t in plan["trades"]}
    assert trades["A"]["delta"] == pytest.approx(-1000)  # 6000 -> 5000
    assert trades["A"]["units"] == pytest.approx(-10)
    assert trades["B"]["delta"] == pytest.approx(1000)  # 3000 -> 4000
    assert trades["BTC"]["delta"] == pytest.approx(0)
    assert plan["leftover"] == pytest.approx(0)


def test_costs_are_paid_by_buying_a_little_less() -> None:
    plan = _plan(costPct=0.001, fixedFee=2)

    trades = {t["asset"]: t for t in plan["trades"]}
    # Selling 1000 of A leaves 1000 - 1 - 2 = 997; the buy of B must also pay its own
    # costs: b + 0.001 b + 2 = 997, so b = 995 / 1.001.
    assert trades["A"]["delta"] == pytest.approx(-1000)
    assert trades["B"]["delta"] == pytest.approx(995 / 1.001)
    assert plan["totalCost"] == pytest.approx(3 + 995 / 1.001 * 0.001 + 2)
    assert plan["leftover"] == pytest.approx(0, abs=1e-9)


def test_band_never_asks_for_money_it_does_not_have() -> None:
    # A is 10 p.p. over target and sold; B (10 under) and BTC (exact) are inside a
    # 12 p.p. band... only A is outside, so its sale stays in cash.
    plan = _plan(targets={"A": 0.4, "B": 0.4, "BTC": 0.2}, band=0.12)

    trades = {t["asset"]: t for t in plan["trades"]}
    assert trades["A"]["delta"] == pytest.approx(-2000)  # 20 p.p. over: outside the band
    assert trades["B"]["delta"] == 0  # 10 p.p. under: inside
    assert trades["BTC"]["delta"] == 0  # 10 p.p. under: inside
    assert plan["leftover"] == pytest.approx(2000)


def test_buys_are_scaled_to_what_the_sales_raise() -> None:
    # B (+20 p.p.) is outside a 15 p.p. band, A (-10 p.p.) inside: nothing is sold, so
    # without new money nothing can be bought.
    plan = _plan(targets={"A": 0.5, "B": 0.5, "BTC": 0.0}, band=0.15)

    assert {t["asset"]: t["delta"] for t in plan["trades"]} == {
        "A": 0,
        "B": 0,
        "BTC": 0,
    }
    assert plan["leftover"] == pytest.approx(0)


def test_band_leaves_small_deviations_alone() -> None:
    # A is 10 p.p. over target, B 10 under; BTC exact. A 15 p.p. band skips both.
    assert all(t["delta"] == 0 for t in _plan(band=0.15)["trades"])
    assert _plan(band=0.05)["trades"][0]["delta"] == pytest.approx(-1000)


def test_contribution_only_buys_the_furthest_below_target() -> None:
    plan = _plan(mode="contribute", contribution=500)

    trades = {t["asset"]: t for t in plan["trades"]}
    # Target with 10500 in total: B should be 4200 (gap 1200), BTC 1050 (gap 50), A none.
    assert trades["A"]["delta"] == 0
    assert trades["B"]["delta"] == pytest.approx(500 * 1200 / 1250)
    assert trades["BTC"]["delta"] == pytest.approx(500 * 50 / 1250)
    assert plan["leftover"] == pytest.approx(0)


def test_large_contribution_fills_every_gap_and_keeps_the_rest() -> None:
    plan = _plan(mode="contribute", contribution=5000)

    # Total 15000: A 7500 (+1500), B 6000 (+3000), BTC 1500 (+500): exactly 5000.
    assert [t["delta"] for t in plan["trades"]] == pytest.approx([1500, 3000, 500])
    assert plan["leftover"] == pytest.approx(0)


def test_whole_units_for_securities_only() -> None:
    plan = _plan(targets={"A": 0.5, "B": 0.405, "BTC": 0.095}, wholeUnits=True)

    trades = {t["asset"]: t for t in plan["trades"]}
    assert trades["B"]["units"] == 35  # 1050 / 30 = 35 exactly
    assert trades["BTC"]["units"] == pytest.approx(-50 / 50000)  # fractional crypto
    assert trades["A"]["units"] == -10


def test_contribution_with_whole_units_never_overspends() -> None:
    plan = _plan(mode="contribute", contribution=100, wholeUnits=True)

    spent = sum(t["delta"] for t in plan["trades"])
    assert spent <= 100
    assert plan["leftover"] == pytest.approx(100 - spent)


def test_whole_units_never_leave_the_plan_short_of_money() -> None:
    odd = [
        {"asset": "A", "value": 5000.0, "priceBase": 333.0, "kind": "security"},
        {"asset": "B", "value": 5000.0, "priceBase": 47.0, "kind": "security"},
    ]
    for wa in (0.31, 0.37, 0.43, 0.58, 0.66):
        plan = _plan(
            positions=odd,
            targets={"A": wa, "B": 1 - wa},
            costPct=0.002,
            fixedFee=1,
            wholeUnits=True,
        )
        assert plan["leftover"] >= -1e-9
        assert all(float(t["units"]).is_integer() for t in plan["trades"])
