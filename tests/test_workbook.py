import base64
import io
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook

from quant.workbook import WorkbookError, portfolio_from_file, portfolio_to_xlsx

POSITIONS: list[dict[str, Any]] = [
    {
        "symbol": "PETR4.SA",
        "kind": "instrument",
        "quantity": 1000,
        "currency": "BRL",
        "cost": 32.5,
        "since": "2023-05-02",
        "name": "Petrobras",
        "exchange": "São Paulo",
        "price": 40.55,
    },
    {"symbol": "EUR", "kind": "cash", "quantity": 2500.5, "currency": "EUR"},
]
TRADES: list[dict[str, Any]] = [
    {"date": "2023-05-02", "symbol": "PETR4.SA", "side": "buy", "quantity": 1000, "price": 32.5}
]


def _xlsx(rows: list[list[Any]], title: str = "Planilha1") -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = title
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


@pytest.mark.parametrize("lang", ["pt", "en"])
def test_export_and_import_round_trip(lang: str) -> None:
    data = portfolio_to_xlsx(POSITIONS, TRADES, lang)

    positions, trades = portfolio_from_file(data, "carteira.xlsx")

    assert positions == [
        {
            "symbol": "PETR4.SA",
            "kind": "instrument",
            "quantity": 1000.0,
            "currency": "BRL",
            "cost": 32.5,
            "since": "2023-05-02",
        },
        {
            "symbol": "EUR",
            "kind": "cash",
            "quantity": 2500.5,
            "currency": "EUR",
            "cost": None,
            "since": None,
        },
    ]
    assert trades == [
        {
            "date": "2023-05-02",
            "symbol": "PETR4.SA",
            "side": "buy",
            "quantity": 1000.0,
            "price": 32.5,
            "fee": 0.0,
        }
    ]


def test_export_writes_headers_in_the_page_language_with_real_numbers_and_dates() -> None:
    book = load_workbook(io.BytesIO(portfolio_to_xlsx(POSITIONS, [], "pt")))

    sheet = book["Carteira"]
    assert [c.value for c in sheet[1]][:6] == [
        "Ativo",
        "Tipo",
        "Quantidade",
        "Moeda",
        "Preço médio",
        "Comprado em",
    ]
    assert sheet["C2"].value == 1000
    assert sheet["B3"].value == "Caixa"
    assert f"{sheet['F2'].value:%Y-%m-%d}" == "2023-05-02"
    assert sheet["J2"].value == pytest.approx(40550.0)  # value, for reading only
    assert "Operações" not in book.sheetnames  # no log, no sheet


def test_a_hand_made_sheet_is_read_with_portuguese_headers_and_formats() -> None:
    data = _xlsx(
        [
            ["Minha carteira"],
            [],
            ["Código", "Qtd", "Preço médio", "Data de compra", "Observação"],
            ["petr4.sa", "1.000", "32,50", "02/05/2023", "longo prazo"],
            [None, None, None, None, None],
            ["AAPL", 10.5, None, None, None],
        ]
    )

    positions, trades = portfolio_from_file(data, "minha.xlsx")

    assert [(p["symbol"], p["quantity"], p["cost"], p["since"]) for p in positions] == [
        ("PETR4.SA", 1000.0, 32.5, "2023-05-02"),
        ("AAPL", 10.5, None, None),
    ]
    assert trades == []


def test_semicolon_csv_uses_brazilian_numbers_and_comma_csv_does_not() -> None:
    pt, _ = portfolio_from_file(
        b"Ativo;Tipo;Quantidade\nPETR4.SA;Ativo;1.000\nBRL;Caixa;1.500,50\n", "c.csv"
    )
    en, _ = portfolio_from_file(b"symbol,quantity,cost\nAAPL,10.5,180.25\n", "c.csv")

    assert [(p["symbol"], p["kind"], p["quantity"], p["currency"]) for p in pt] == [
        ("PETR4.SA", "instrument", 1000.0, ""),
        ("BRL", "cash", 1500.5, "BRL"),
    ]
    assert (en[0]["quantity"], en[0]["cost"]) == (10.5, 180.25)


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([["Ativo", "Quantidade"], ["PETR4.SA", 0]], "Linha 2"),
        ([["Ativo", "Quantidade"], ["PETR4.SA", "muito"]], "Linha 2"),
        ([["Ativo", "Quantidade", "Comprado em"], ["X", 1, "31/02/2024"]], "data de compra"),
        ([["Nome", "Valor"], ["X", 1]], "cabeçalho"),
        ([["Ativo", "Quantidade"]], "nenhuma posição"),
    ],
)
def test_bad_sheets_name_the_problem(rows: list[list[Any]], message: str) -> None:
    with pytest.raises(WorkbookError) as error:
        portfolio_from_file(_xlsx(rows), "x.xlsx")

    assert message in error.value.pt


def test_bad_transaction_rows_are_refused() -> None:
    book = Workbook()
    first = book.active
    assert first is not None
    first.append(["Ativo", "Quantidade"])
    first.append(["PETR4.SA", 10])
    log = book.create_sheet("Operações")
    log.append(["Data", "Ativo", "Lado", "Quantidade", "Preço"])
    log.append(["2024-01-02", "PETR4.SA", "talvez", 10, 30])
    out = io.BytesIO()
    book.save(out)

    with pytest.raises(WorkbookError) as error:
        portfolio_from_file(out.getvalue(), "x.xlsx")

    assert "Operações, linha 2" in error.value.pt


def test_other_files_are_refused() -> None:
    with pytest.raises(WorkbookError):
        portfolio_from_file(b"not a zip", "x.xlsx")
    with pytest.raises(WorkbookError):
        portfolio_from_file(b"%PDF", "x.pdf")


def test_base64_of_an_export_is_what_the_page_sends() -> None:
    # The page reads the file as a data URL and sends the part after the comma.
    content = base64.b64encode(portfolio_to_xlsx(POSITIONS, TRADES)).decode()

    positions, trades = portfolio_from_file(base64.b64decode(content), "x.xlsx")

    assert len(positions) == 2 and len(trades) == 1
