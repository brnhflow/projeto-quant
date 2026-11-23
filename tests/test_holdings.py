from pathlib import Path

import pandas as pd
import pytest

from quant.holdings import load_holdings

EXAMPLE = Path(__file__).parents[1] / "data" / "holdings.example.csv"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "holdings.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_reads_example_file() -> None:
    holdings = load_holdings(EXAMPLE)

    assert list(holdings.columns) == ["quantity", "currency"]
    assert holdings.index.name == "asset"
    assert (holdings["quantity"] > 0).all()
    assert set(holdings["currency"]) <= {"EUR", "BRL", "USD"}


def test_known_values_and_cleanup(tmp_path: Path) -> None:
    path = _write(tmp_path, "asset,quantity,currency\n PETR4 ,100, brl\nBTC,0.05,USD\n")

    holdings = load_holdings(path)

    expected = pd.DataFrame(
        {"quantity": [100.0, 0.05], "currency": ["BRL", "USD"]},
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
    ],
)
def test_rejects_bad_files(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_holdings(_write(tmp_path, text))
