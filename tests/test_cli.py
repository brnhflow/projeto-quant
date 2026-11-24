import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from quant.__main__ import main
from quant.data import update_market_data
from quant.holdings import load_holdings

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    holdings_file = tmp_path / "holdings.csv"
    holdings_file.write_text(
        "asset,quantity,currency,source,symbol\nPETR4,100,BRL,yahoo,PETR4.SA\n", encoding="utf-8"
    )
    cache = tmp_path / "cache"

    def fetch(url: str) -> Any:
        return _fixture("yahoo_petr4" if "yahoo" in url else "frankfurter")

    update_market_data(
        load_holdings(holdings_file), pd.Timestamp("2026-01-01"), cache, fetch=fetch, pause=0
    )
    return holdings_file, cache


def test_offline_report_from_cache(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    holdings_file, cache = _setup(tmp_path)
    out = tmp_path / "out" / "report.html"

    code = main(
        [
            "report",
            "--offline",
            "--holdings",
            str(holdings_file),
            "--cache",
            str(cache),
            "--out",
            str(out),
        ]
    )

    assert code == 0
    page = out.read_text(encoding="utf-8")
    assert '"name": "PETR4"' in page
    assert '"fromCache": true' in page
    assert "wrote" in capsys.readouterr().out


def test_missing_holdings_file_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["report", "--offline", "--holdings", str(tmp_path / "nope.csv")])

    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_offline_without_cache_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    holdings_file, _ = _setup(tmp_path)

    code = main(
        [
            "report",
            "--offline",
            "--holdings",
            str(holdings_file),
            "--cache",
            str(tmp_path / "empty"),
        ]
    )

    assert code == 2
    assert "no cached copy" in capsys.readouterr().err


def test_cash_does_not_push_the_report_past_the_last_trading_day(tmp_path: Path) -> None:
    from quant.pipeline import analyse_portfolio

    holdings = pd.DataFrame(
        {
            "quantity": [10.0, 100.0],
            "currency": ["BRL", "EUR"],
            "source": ["yahoo", "cash"],
            "symbol": ["PETR4.SA", "EUR"],
        },
        index=pd.Index(["PETR4", "Cash EUR"], name="asset"),
    )
    fixture = json.loads((FIXTURES / "yahoo_petr4.json").read_text(encoding="utf-8"))
    last_trade = pd.Timestamp(fixture["chart"]["result"][0]["timestamp"][-1], unit="s").normalize()
    later = (last_trade + pd.Timedelta(days=4)).tz_localize("UTC") + pd.Timedelta(hours=12)

    def fetch(url: str) -> object:
        if "PETR4" in url:
            return fixture
        if "frankfurter" in url:
            return json.loads((FIXTURES / "frankfurter.json").read_text(encoding="utf-8"))
        raise ConnectionError("no index data in this test")

    analysis = analyse_portfolio(
        holdings, 1, tmp_path, title="T", fetch=fetch, now=later, pause=0, fetch_text=lambda u: b""
    )

    as_of = re.search(r'"asOf": "([0-9-]+)"', analysis.page)
    assert as_of is not None
    assert pd.Timestamp(as_of.group(1)) <= last_trade
