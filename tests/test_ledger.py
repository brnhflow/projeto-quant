"""Transaction log against a hand-built example: two contributions and one sale.

One asset in euro, prices 10, 11, 11, 12, 12 on five dates two months apart.
- Day 0: buy 10 at 10 (pays 100).
- Day 2: buy 10 at 11 (pays 110). Average cost 210 / 20 = 10.5.
- Day 3: sell 5 at 12 with a fee of 1 (receives 59). Realises 60 - 1 - 5 * 10.5 = 6.5.
Held at the end: 15 units at 12 = 180, cost basis 157.5, so 22.5 unrealised.
Time-weighted: 10% on day 1, 0% on day 2, 1/11 on day 3, 0% on day 4, which chains to
exactly the price return 10 -> 12 = 20%, whatever the timing of the money.
"""

from collections.abc import Sequence

import pandas as pd
import pytest

from quant.ledger import (
    analyse_ledger,
    average_cost,
    check_against_holdings,
    net_units,
    parse_transactions,
    time_weighted_returns,
    units_over_time,
)
from quant.performance import npv

DATES = pd.DatetimeIndex(["2025-01-02", "2025-03-03", "2025-05-02", "2025-07-01", "2025-09-01"])
DAILY = pd.bdate_range("2025-03-03", periods=5)


def _trades(rows: Sequence[tuple[str, str, str, float, float, float]]) -> pd.DataFrame:
    return parse_transactions(
        pd.DataFrame(rows, columns=["date", "symbol", "side", "quantity", "price", "fee"])
    )


EXAMPLE = [
    ("2025-01-02", "X.AS", "buy", 10, 10, 0),
    ("2025-05-02", "X.AS", "buy", 10, 11, 0),
    ("2025-07-01", "X.AS", "sell", 5, 12, 1),
]
HOLDINGS = pd.DataFrame(
    {"quantity": [15.0], "currency": ["EUR"], "source": ["yahoo"], "symbol": ["X.AS"]},
    index=pd.Index(["X"], name="asset"),
)
PRICES = pd.DataFrame({"X": [10.0, 11.0, 11.0, 12.0, 12.0]}, index=DATES)
FX = pd.DataFrame({"USD": [0.9] * 5}, index=DATES)


def test_hand_built_example() -> None:
    result = analyse_ledger(_trades(EXAMPLE), HOLDINGS, PRICES, FX)

    assert result["twrTotal"] == pytest.approx(0.20)
    twr = result["twr"]
    assert isinstance(twr, pd.Series)
    assert twr.tolist() == pytest.approx([0.10, 0.0, 1 / 11, 0.0])
    assert result["end"] == pytest.approx(180.0)
    assert result["netInvested"] == pytest.approx(151.0)
    assert result["realised"] == pytest.approx(6.5)
    assert result["unrealised"] == pytest.approx(22.5)
    # Every euro of profit is either realised or unrealised.
    assert float(result["realised"]) + float(result["unrealised"]) == pytest.approx(29.0)  # pyright: ignore[reportArgumentType]


def test_money_weighted_return_solves_the_cash_flows() -> None:
    result = analyse_ledger(_trades(EXAMPLE), HOLDINGS, PRICES, FX)
    flows = [
        (DATES[0], -100.0),
        (DATES[2], -110.0),
        (DATES[3], 59.0),
        (DATES[4], 180.0),
    ]

    rate = result["mwr"]

    assert isinstance(rate, float)
    assert npv(rate, flows) == pytest.approx(0.0, abs=1e-6)


def test_timing_moves_the_money_weighted_return_but_not_the_time_weighted() -> None:
    # Same prices; all the money goes in on day 2 instead of being split.
    late = [("2025-05-02", "X.AS", "buy", 20, 11, 0), ("2025-07-01", "X.AS", "sell", 5, 12, 1)]
    early = analyse_ledger(_trades(EXAMPLE), HOLDINGS, PRICES, FX)
    after = analyse_ledger(_trades(late), HOLDINGS, PRICES, FX)

    # Time-weighted: the late log missed day 1's 10%; only day 3's 1/11 remains.
    assert after["twrTotal"] == pytest.approx(1 / 11)
    assert early["twrTotal"] == pytest.approx(0.20)
    assert early["mwr"] != pytest.approx(after["mwr"])


def test_cost_in_another_currency_uses_the_trade_date_rate() -> None:
    fx = pd.DataFrame({"USD": [0.9, 0.9, 0.8, 0.8, 0.8]}, index=DATES)
    holdings = HOLDINGS.assign(currency=["USD"])
    trades = _trades(
        [("2025-01-02", "X.AS", "buy", 10, 10, 0), ("2025-05-02", "X.AS", "buy", 5, 20, 0)]
    )

    result = analyse_ledger(trades, holdings, PRICES, fx)

    # 10 x 10 USD at 0.9 plus 5 x 20 USD at 0.8.
    assert result["netInvested"] == pytest.approx(90.0 + 80.0)


def test_average_cost_after_a_partial_sale() -> None:
    trades = _trades(EXAMPLE).assign(asset="X")
    trades["amount"] = trades["quantity"] * trades["price"]
    trades["fee_base"] = trades["fee"]

    (position,) = average_cost(trades).values()

    assert position.units == pytest.approx(15)
    assert position.cost_basis == pytest.approx(157.5)
    assert position.realised == pytest.approx(6.5)
    assert (position.bought, position.sold) == pytest.approx((210.0, 59.0))


def test_units_count_trades_before_the_history_and_on_weekends() -> None:
    trades = _trades(
        [
            ("2025-01-10", "X.AS", "buy", 3, 10, 0),  # before the first date: opening units
            ("2025-03-08", "X.AS", "buy", 2, 10, 0),  # a Saturday: counts from Monday
        ]
    ).assign(asset="X")

    units = units_over_time(trades, DAILY)

    assert units["X"].tolist() == [3, 3, 3, 3, 3]
    later = pd.bdate_range("2025-03-06", periods=3)
    assert units_over_time(trades, later)["X"].tolist() == [3, 3, 5]


def test_time_weighted_return_ignores_a_day_with_nothing_held() -> None:
    prices = pd.DataFrame({"X": [10.0, 12.0, 6.0]}, index=DAILY[:3])
    units = pd.DataFrame({"X": [0.0, 1.0, 1.0]}, index=DAILY[:3])

    r = time_weighted_returns(prices, units)

    assert r.isna().iloc[0]
    assert r.iloc[1] == pytest.approx(-0.5)


def test_log_must_match_the_holdings() -> None:
    trades = _trades(EXAMPLE)

    assert check_against_holdings(trades, HOLDINGS) == []
    assert check_against_holdings(trades, HOLDINGS.assign(quantity=[20.0])) == [
        "X.AS: log 15, portfolio 20"
    ]
    other = _trades([*EXAMPLE, ("2025-03-06", "Y.AS", "buy", 1, 5, 0)])
    assert check_against_holdings(other, HOLDINGS) == ["Y.AS: log 1, portfolio 0"]


def test_selling_more_than_held_is_refused() -> None:
    with pytest.raises(ValueError, match="sells more"):
        net_units(
            _trades(
                [("2025-03-03", "X.AS", "buy", 1, 10, 0), ("2025-03-04", "X.AS", "sell", 2, 10, 0)]
            )
        )


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (("03/03/2025", "X", "buy", "1", "1", ""), "YYYY-MM-DD"),
        (("2025-03-03", "X", "hold", "1", "1", ""), "buy or sell"),
        (("2025-03-03", "X", "buy", "-1", "1", ""), "above zero"),
        (("2025-03-03", "X", "buy", "1", "abc", ""), "price must be a number"),
        (("2025-03-03", "X", "buy", "1", "1", "-2"), "negative"),
        (("2025-03-03", "", "buy", "1", "1", ""), "symbol"),
    ],
)
def test_invalid_rows_are_refused(row: tuple[str, ...], message: str) -> None:
    raw = pd.DataFrame([row], columns=["date", "symbol", "side", "quantity", "price", "fee"])

    with pytest.raises(ValueError, match=message):
        parse_transactions(raw)


def test_fee_column_is_optional_and_same_day_order_is_kept() -> None:
    raw = pd.DataFrame(
        [
            ("2025-03-04", "B", "buy", "1", "1"),
            ("2025-03-03", "A", "buy", "1", "1"),
            ("2025-03-04", "C", "buy", "1", "1"),
        ],
        columns=["date", "symbol", "side", "quantity", "price"],
    )

    trades = parse_transactions(raw)

    assert trades["symbol"].tolist() == ["A", "B", "C"]
    assert trades["fee"].tolist() == [0.0, 0.0, 0.0]
