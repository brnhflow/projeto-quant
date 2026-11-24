"""Asset-type classifier runs in the browser; test it with Node when Node is installed."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parents[1] / "src" / "quant" / "app" / "static" / "assets.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js not installed")


def _types(cases: list[dict[str, Any]]) -> list[str]:
    assert NODE is not None
    code = (
        f"const a = require({json.dumps(str(SCRIPT))});"
        f"console.log(JSON.stringify({json.dumps(cases)}.map(a.assetType)));"
    )
    out = subprocess.run([NODE, "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


# Short and long names as Yahoo returns them (checked on 2026-11-24).
CASES = [
    ({"symbol": "PETR4.SA", "kind": "EQUITY", "detail": "PETROBRAS   PN      N2"}, "acao"),
    ({"symbol": "HGLG11.SA", "kind": "EQUITY", "detail": "FII HGLG PAXCI"}, "fii"),
    ({"symbol": "XPML11.SA", "kind": "EQUITY", "detail": "FII XP MALLSCI  ER"}, "fii"),
    ({"symbol": "TAEE11.SA", "kind": "EQUITY", "detail": "TAESA       UNT ED  N2"}, "acao"),
    ({"symbol": "SANB11.SA", "kind": "EQUITY", "detail": "SANTANDER BRUNT"}, "acao"),
    ({"symbol": "BOVA11.SA", "kind": "EQUITY", "detail": "ISHARES BOVACI"}, "etf"),
    ({"symbol": "IVVB11.SA", "kind": "EQUITY", "detail": "ISHARE SP500CI"}, "etf"),
    ({"symbol": "AAPL34.SA", "kind": "EQUITY", "detail": "APPLE       DRN ED"}, "bdr"),
    ({"symbol": "MSFT34.SA", "kind": "EQUITY", "detail": ""}, "bdr"),
    ({"symbol": "IWDA.AS", "kind": "ETF", "name": "iShares Core MSCI World"}, "etf"),
    ({"symbol": "0P0000VNYB.SA", "kind": "MUTUALFUND"}, "fundo"),
    ({"symbol": "BTC-USD", "kind": "CRYPTOCURRENCY"}, "cripto"),
    ({"symbol": "ETH-USD"}, "cripto"),
    ({"symbol": "ASML.AS", "kind": "EQUITY", "name": "ASML Holding N.V."}, "acao"),
    ({"symbol": "BRL", "cash": True}, "caixa"),
]


def test_asset_types_from_source_names() -> None:
    assert _types([c[0] for c in CASES]) == [c[1] for c in CASES]
