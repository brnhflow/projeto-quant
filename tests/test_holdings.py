from pathlib import Path

import pandas as pd
import pytest

from quant.holdings import asset_labels, load_holdings, save_holdings

EXAMPLE = Path(__file__).parents[1] / "data" / "holdings.example.csv"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "holdings.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_reads_example_file() -> None:
    holdings = load_holdings(EXAMPLE)

    assert list(holdings.columns) == ["quantity", "currency", "source", "symbol", "cost", "since"]
    assert holdings.index.name == "asset"
    assert (holdings["quantity"] > 0).all()
    assert set(holdings["currency"]) <= {"EUR", "BRL", "USD"}


def test_known_values_and_cleanup(tmp_path: Path) -> None:
    path = _write(tmp_path, "asset,quantity,currency\n PETR4 ,100, brl\nBTC,0.05,USD\n")

    holdings = load_holdings(path)

    expected = pd.DataFrame(
        {
            "quantity": [100.0, 0.05],
            "currency": ["BRL", "USD"],
            "source": ["yahoo", "yahoo"],
            "symbol": ["PETR4", "BTC"],
        },
        index=pd.Index(["PETR4", "BTC"], name="asset"),
    )
    pd.testing.assert_frame_equal(holdings, expected)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("asset,quantity\nA,1\n", "missing columns"),
        ("asset,quantity,currency\nA,1,EUR\nA,2,EUR\n", "duplicate"),
        ("asset,quantity,currency\nA,-1,EUR\n", "quantity"),
        ("asset,quantity,currency\nA,abc,EUR\n", "quantity"),
        ("asset,quantity,currency\nA,1,EURO\n", "currency"),
        ("asset,quantity,currency\n", "no positions"),
        ("asset,quantity,currency\nA,inf,EUR\n", "quantity"),
        ("asset,quantity,currency\n,5,EUR\n", "asset name"),
        ("asset,quantity,currency,source\nA,1,EUR,stooq\n", "unknown source"),
    ],
)
def test_rejects_bad_files(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_holdings(_write(tmp_path, text))


def test_source_and_symbol_columns(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        (
            "asset,quantity,currency,source,symbol\n"
            "PETR4,1,BRL,,PETR4.SA\n"
            "BTC,1,USD,Kraken,XBTUSD\n"
            "X,1,EUR,yahoo,\n"
        ),
    )

    holdings = load_holdings(path)

    assert holdings["source"].tolist() == ["yahoo", "kraken", "yahoo"]
    assert holdings["symbol"].tolist() == ["PETR4.SA", "XBTUSD", "X"]


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    original = load_holdings(EXAMPLE)
    path = tmp_path / "private" / "holdings.csv"

    save_holdings(original, path)

    pd.testing.assert_frame_equal(load_holdings(path), original)


def test_asset_labels_shorten_unless_ambiguous() -> None:
    labels = asset_labels(["PETR4.SA", "ASML.AS", "ASML", "BTC-USD", "IWDA.AS"])

    assert labels == ["PETR4", "ASML.AS", "ASML", "BTC-USD", "IWDA"]


def test_cash_row_needs_its_currency_as_symbol(tmp_path: Path) -> None:
    path = tmp_path / "h.csv"
    path.write_text(
        "asset,quantity,currency,source,symbol\nCaixa,10,BRL,cash,EUR\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="cash row"):
        load_holdings(path)


def test_cash_row_is_read(tmp_path: Path) -> None:
    path = tmp_path / "h.csv"
    path.write_text(
        "asset,quantity,currency,source,symbol\nCash BRL,10,BRL,cash,BRL\n", encoding="utf-8"
    )

    assert load_holdings(path).loc["Cash BRL", "source"] == "cash"
