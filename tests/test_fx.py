import numpy as np
import pandas as pd
import pytest

from quant.fx import to_base_currency
from quant.returns import simple_returns

DATES = pd.date_range("2026-01-05", periods=3, freq="B")


def _frame(data: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(data, index=DATES)


def test_known_answer_three_currencies() -> None:
    # Rates are euros per 1 unit of the currency.
    # B3 stock: 40 BRL * 0.16 EUR/BRL = 6.40 EUR
    # Crypto:   100 000 USD * 0.90 EUR/USD = 90 000 EUR
    # EU stock: already in EUR, unchanged (no rate needed).
    prices = _frame({"PETR4": [40.0] * 3, "BTC": [100_000.0] * 3, "ASML": [700.0] * 3})
    currencies = pd.Series({"PETR4": "BRL", "BTC": "USD", "ASML": "EUR"})
    fx = _frame({"BRL": [0.16] * 3, "USD": [0.90] * 3})

    result = to_base_currency(prices, currencies, fx)

    expected = _frame({"PETR4": [6.4] * 3, "BTC": [90_000.0] * 3, "ASML": [700.0] * 3})
    pd.testing.assert_frame_equal(result, expected, rtol=1e-12)


def test_currency_move_alone_shows_up_as_return() -> None:
    # The stock does not move in reais, but the real gains 10% against the euro:
    # for an investor counting in euros that is a +10% return.
    prices = _frame({"PETR4": [40.0, 40.0, 40.0]})
    fx = _frame({"BRL": [0.16, 0.176, 0.176]})

    in_eur = to_base_currency(prices, pd.Series({"PETR4": "BRL"}), fx)

    np.testing.assert_allclose(simple_returns(in_eur)["PETR4"].to_numpy(), [0.10, 0.0])


def test_missing_rate_leaves_only_that_currency_unknown() -> None:
    prices = _frame({"PETR4": [40.0] * 3, "ASML": [700.0] * 3})
    fx = pd.DataFrame({"BRL": [0.16, 0.16]}, index=DATES[[0, 2]])  # no rate on day 1

    result = to_base_currency(prices, pd.Series({"PETR4": "BRL", "ASML": "EUR"}), fx)

    assert np.isnan(result["PETR4"].iloc[1])
    assert result["PETR4"].iloc[[0, 2]].tolist() == pytest.approx([6.4, 6.4])
    assert result["ASML"].tolist() == [700.0] * 3


def test_future_rates_do_not_change_past_prices() -> None:
    prices = _frame({"PETR4": [40.0, 41.0, 42.0]})
    currencies = pd.Series({"PETR4": "BRL"})
    fx = _frame({"BRL": [0.16, 0.17, 0.18]})
    changed_future = fx.copy()
    changed_future.iloc[-1] = 5.0

    before = to_base_currency(prices, currencies, fx).iloc[:-1]
    after = to_base_currency(prices, currencies, changed_future).iloc[:-1]

    pd.testing.assert_frame_equal(before, after)


def test_rejects_asset_without_currency() -> None:
    prices = _frame({"PETR4": [40.0] * 3, "ASML": [700.0] * 3})

    with pytest.raises(ValueError, match="no currency"):
        to_base_currency(prices, pd.Series({"PETR4": "BRL"}), _frame({"BRL": [0.16] * 3}))


def test_rejects_currency_without_rates() -> None:
    prices = _frame({"BTC": [100_000.0] * 3})

    with pytest.raises(ValueError, match="no FX rates"):
        to_base_currency(prices, pd.Series({"BTC": "USD"}), _frame({"BRL": [0.16] * 3}))


@pytest.mark.parametrize("bad_rate", [0.0, -0.16])
def test_rejects_non_positive_rates(bad_rate: float) -> None:
    prices = _frame({"PETR4": [40.0] * 3})

    with pytest.raises(ValueError, match="positive"):
        to_base_currency(
            prices, pd.Series({"PETR4": "BRL"}), _frame({"BRL": [0.16, bad_rate, 0.16]})
        )
