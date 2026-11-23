import numpy as np
import pandas as pd
import pytest

from quant.attribution import return_attribution
from quant.returns import portfolio_value

DATES = pd.date_range("2026-01-05", periods=3, freq="B")


def _frame(data: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(data, index=DATES)


def test_known_answer_price_and_fx() -> None:
    # Holdings: 10 PETR4 (BRL), 1 ASML (EUR).
    # Start: PETR4 40 BRL at 0.16 -> 6.40 EUR -> 64 EUR; ASML 136 EUR. V0 = 200 EUR.
    # End:   PETR4 44 BRL at 0.20 -> 8.80 EUR -> 88 EUR; ASML 146 EUR.
    # PETR4 total = (88 - 64) / 200 = 12%.
    #   price effect at the start rate: 10 * 0.16 * (44 - 40) / 200 = 3.2%
    #   FX effect on the end price:     10 * 44 * (0.20 - 0.16) / 200 = 8.8%
    # ASML: price (146 - 136) / 200 = 5%, FX 0.
    local = _frame({"PETR4": [40.0, 42.0, 44.0], "ASML": [136.0, 140.0, 146.0]})
    eur = _frame({"PETR4": [6.4, 7.56, 8.8], "ASML": [136.0, 140.0, 146.0]})
    quantities = pd.Series({"PETR4": 10.0, "ASML": 1.0})

    result = return_attribution(local, eur, quantities)

    expected = pd.DataFrame(
        {"price": [0.032, 0.05], "fx": [0.088, 0.0], "total": [0.12, 0.05]},
        index=pd.Index(["PETR4", "ASML"], name="asset"),
    )
    pd.testing.assert_frame_equal(result, expected, rtol=1e-12)


def test_totals_add_up_to_portfolio_return() -> None:
    rng = np.random.default_rng(5)
    local = _frame({"A": [10.0, 11.0, 9.5], "B": [100.0, 98.0, 103.0], "C": [1.0, 1.2, 1.1]})
    rates = _frame({"A": [0.9, 0.92, 0.95], "B": [1.0, 1.0, 1.0], "C": [0.16, 0.15, 0.17]})
    eur = local * rates
    quantities = pd.Series(rng.uniform(1, 10, 3), index=["A", "B", "C"])

    result = return_attribution(local, eur, quantities)

    value = portfolio_value(eur, quantities)
    assert result["total"].sum() == pytest.approx(value.iloc[-1] / value.iloc[0] - 1)
    np.testing.assert_allclose(result["price"] + result["fx"], result["total"])


def test_currency_only_move_is_all_fx() -> None:
    local = _frame({"PETR4": [40.0, 40.0, 40.0]})
    eur = _frame({"PETR4": [6.4, 6.6, 7.04]})  # rate 0.16 -> 0.176: +10%

    result = return_attribution(local, eur, pd.Series({"PETR4": 1.0}))

    assert result.loc["PETR4", "price"] == pytest.approx(0.0)
    assert result.loc["PETR4", "fx"] == pytest.approx(0.10)


def test_rejects_missing_first_or_last_price() -> None:
    local = _frame({"A": [10.0, 11.0, np.nan]})
    eur = _frame({"A": [10.0, 11.0, np.nan]})

    with pytest.raises(ValueError, match="first and last"):
        return_attribution(local, eur, pd.Series({"A": 1.0}))


def test_rejects_tables_that_do_not_match() -> None:
    local = _frame({"A": [10.0, 11.0, 12.0]})
    eur = pd.DataFrame({"A": [10.0, 11.0]}, index=DATES[:2])

    with pytest.raises(ValueError, match="same dates"):
        return_attribution(local, eur, pd.Series({"A": 1.0}))
