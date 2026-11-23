"""The quantity parser runs in the browser; test it with Node when Node is installed."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "src" / "quant" / "app" / "static" / "quantity.js"
NODE = shutil.which("node")

CASES = [
    ("200", 200),
    ("0,05", 0.05),
    ("0.05", 0.05),
    ("1.5", 1.5),
    ("1.500", 1500),  # pt-BR thousands
    ("1.000.000", 1_000_000),
    ("1.234,56", 1234.56),
    ("1234,5", 1234.5),
    ("0.500", 0.5),  # leading zero: a decimal, never "500"
    ("  12 ", 12),
    ("", None),
    ("1.23,4", "NaN"),
    ("1,2,3", "NaN"),
    ("abc", "NaN"),
    ("-5", "NaN"),
]


def _run(expression: str) -> object:
    assert NODE is not None
    code = (
        f"const q = require({json.dumps(str(SCRIPT))}); console.log(JSON.stringify({expression}));"
    )
    out = subprocess.run([NODE, "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_parse_quantity_cases() -> None:
    inputs = [c[0] for c in CASES]
    mapper = "t => { const v = q.parseQuantity(t); return Number.isNaN(v) ? 'NaN' : v; }"
    expression = f"{json.dumps(inputs)}.map({mapper})"

    assert _run(expression) == [c[1] for c in CASES]


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_formatted_input_parses_back_to_the_same_number() -> None:
    values = [1500, 0.05, 1234.56, 1_000_000, 3]
    mapper = "v => [q.formatQuantityInput(v), q.parseQuantity(q.formatQuantityInput(v))]"
    expression = f"{json.dumps(values)}.map({mapper})"

    result = _run(expression)

    assert isinstance(result, list)
    assert [pair[1] for pair in result] == values  # pyright: ignore[reportUnknownVariableType]
    assert [pair[0] for pair in result] == ["1500", "0,05", "1234,56", "1000000", "3"]  # pyright: ignore[reportUnknownVariableType]
