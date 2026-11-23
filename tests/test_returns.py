import numpy as np
import pandas as pd
import pytest

from quant.returns import portfolio_returns, portfolio_value, simple_returns


def _prices(data: dict[str, list[float]], start: str = "2026-01-05") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(next(iter(data.values()))), freq="B")
    return pd.DataFrame(data, index=index)


def test_known_answer_two_assets() -> None:
    # A: 100 -> 110 is +10%; 110 -> 99 is 99/110 - 1 = -10%.
    # B: 50 -> 50 is 0%;     50 -> 55 is +10%.
    prices = _prices({"A": [100.0, 110.0, 99.0], "B": [50.0, 50.0, 55.0]})

    result = simple_returns(prices)

    expected = pd.DataFrame(
        {"A": [0.10, -0.10], "B": [0.0, 0.10]},
        index=prices.index[1:],
    )
    pd.testing.assert_frame_equal(result, expected, rtol=1e-12)


def test_constant_prices_give_zero_returns() -> None:
    prices = _prices({"A": [42.0] * 5})

    result = simple_returns(prices)

    assert (result["A"] == 0.0).all()
    assert len(result) == 4


def test_missing_price_is_not_filled() -> None:
    # A missing price must stay visible: it makes the return of that day and of the
    # next day unknown, instead of being silently replaced by the previous price.
    prices = _prices({"A": [100.0, np.nan, 121.0, 133.1]})

    result = simple_returns(prices)["A"]

    assert np.isnan(result.iloc[0])
    assert np.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(0.10)  # 133.1 / 121 - 1


def test_future_prices_do_not_change_past_returns() -> None:
    prices = _prices({"A": [100.0, 102.0, 101.0, 105.0], "B": [10.0, 11.0, 12.0, 13.0]})
    changed_future = prices.copy()
    changed_future.iloc[-1] = [1.0, 1000.0]

    before = simple_returns(prices).iloc[:-1]
    after = simple_returns(changed_future).iloc[:-1]

    pd.testing.assert_frame_equal(before, after)


@pytest.mark.parametrize("bad_price", [0.0, -5.0])
def test_rejects_non_positive_prices(bad_price: float) -> None:
    prices = _prices({"A": [100.0, bad_price, 101.0]})

    with pytest.raises(ValueError, match="positive"):
        simple_returns(prices)


def test_rejects_dates_out_of_order() -> None:
    prices = _prices({"A": [100.0, 101.0, 102.0]}).iloc[::-1]

    with pytest.raises(ValueError, match="increasing"):
        simple_returns(prices)


def test_rejects_duplicate_dates() -> None:
    prices = _prices({"A": [100.0, 101.0]})
    prices = pd.concat([prices, prices.iloc[[-1]]])

    with pytest.raises(ValueError, match="increasing"):
        simple_returns(prices)


# ---------------------------------------------------------------- portfolio_returns


def test_portfolio_known_answer_and_weight_drift() -> None:
    # Holdings: 1 share of A, 2 shares of B.
    # Day 0: 1*100 + 2*50 = 200
    # Day 1: 1*110 + 2*50 = 210  ->  210/200 - 1 = +5%
    # Day 2: 1*99  + 2*55 = 209  ->  209/210 - 1 = -1/210 = -0.476...%
    # Constant 50/50 weights would give 0.5*(-10%) + 0.5*(+10%) = 0% on day 2: wrong for a
    # real portfolio, because after day 1 A is 110/210 = 52.4% of it, not 50%.
    prices = _prices({"A": [100.0, 110.0, 99.0], "B": [50.0, 50.0, 55.0]})
    quantities = pd.Series({"A": 1.0, "B": 2.0})

    result = portfolio_returns(prices, quantities)

    expected = pd.Series([0.05, -1 / 210], index=prices.index[1:], name="portfolio")
    pd.testing.assert_series_equal(result, expected, rtol=1e-12)


def test_portfolio_of_one_asset_equals_that_asset() -> None:
    prices = _prices({"A": [100.0, 104.0, 98.0, 101.0]})

    result = portfolio_returns(prices, pd.Series({"A": 7.0}))

    np.testing.assert_allclose(result.to_numpy(), simple_returns(prices)["A"].to_numpy())


def test_portfolio_missing_price_makes_value_unknown() -> None:
    prices = _prices({"A": [100.0, np.nan, 100.0], "B": [10.0, 10.0, 10.0]})

    result = portfolio_returns(prices, pd.Series({"A": 1.0, "B": 1.0}))

    assert result.isna().all()


def test_portfolio_future_prices_do_not_change_past_returns() -> None:
    prices = _prices({"A": [100.0, 102.0, 101.0, 105.0], "B": [10.0, 11.0, 12.0, 13.0]})
    quantities = pd.Series({"A": 1.0, "B": 3.0})
    changed_future = prices.copy()
    changed_future.iloc[-1] = [1.0, 1000.0]

    before = portfolio_returns(prices, quantities).iloc[:-1]
    after = portfolio_returns(changed_future, quantities).iloc[:-1]

    pd.testing.assert_series_equal(before, after)


def test_portfolio_rejects_assets_without_prices() -> None:
    prices = _prices({"A": [100.0, 101.0]})

    with pytest.raises(ValueError, match="no prices"):
        portfolio_returns(prices, pd.Series({"A": 1.0, "C": 1.0}))


@pytest.mark.parametrize(
    "quantities", [{"A": -1.0, "B": 1.0}, {"A": 0.0, "B": 0.0}, {"A": float("nan"), "B": 1.0}]
)
def test_portfolio_rejects_short_or_empty_holdings(quantities: dict[str, float]) -> None:
    prices = _prices({"A": [100.0, 101.0], "B": [10.0, 11.0]})

    with pytest.raises(ValueError, match="quantities"):
        portfolio_returns(prices, pd.Series(quantities))


# ---------------------------------------------------------------- portfolio_value


def test_portfolio_value_known_answer() -> None:
    # 1*100 + 2*50 = 200; 1*110 + 2*50 = 210
    prices = _prices({"A": [100.0, 110.0], "B": [50.0, 50.0]})

    value = portfolio_value(prices, pd.Series({"A": 1.0, "B": 2.0}))

    pd.testing.assert_series_equal(
        value, pd.Series([200.0, 210.0], index=prices.index, name="value")
    )


def test_portfolio_value_ignores_gaps_in_assets_not_held() -> None:
    prices = _prices({"A": [100.0, 110.0], "B": [50.0, np.nan]})

    value = portfolio_value(prices, pd.Series({"A": 1.0, "B": 0.0}))

    assert value.tolist() == [100.0, 110.0]
