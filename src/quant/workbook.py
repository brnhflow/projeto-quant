"""The portfolio as a spreadsheet: export it to Excel, and read it back from Excel or CSV.

The exported workbook has a "Portfolio" sheet (one row per position) and, when there is one, a
"Transactions" sheet with the log. Headers are written in the page's language and read in
either language, so a file saved in Portuguese opens in English and the other way round.
Columns the reader does not know (name, exchange, last price, value) are for the person reading
the file and are ignored on import, as are blank rows.

Import only checks the shape of each row and points at the row that is wrong; the server
validates the portfolio again, in full, before it is analysed.
"""

from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

MAX_ROWS = 5000


class WorkbookError(ValueError):
    """A file that cannot be read as a portfolio; carries the message in English and Portuguese."""

    def __init__(self, en: str, pt: str) -> None:
        super().__init__(en)
        self.pt = pt


@dataclass(frozen=True)
class Column:
    """One column: its key in the API, and its header in each language."""

    key: str
    pt: str
    en: str
    width: float
    number_format: str = "General"


POSITION_COLUMNS = (
    Column("symbol", "Ativo", "Asset", 16),
    Column("kind", "Tipo", "Type", 10),
    Column("quantity", "Quantidade", "Quantity", 14, "#,##0.########"),
    Column("currency", "Moeda", "Currency", 9),
    Column("cost", "Preço médio", "Average cost", 14, "#,##0.00######"),
    Column("since", "Comprado em", "Bought on", 13, "yyyy-mm-dd"),
)
# Written for the reader, ignored when the file comes back.
INFO_COLUMNS = (
    Column("name", "Nome", "Name", 34),
    Column("exchange", "Bolsa", "Exchange", 14),
    Column("price", "Último preço", "Last price", 14, "#,##0.00######"),
    Column("value", "Valor", "Value", 16, "#,##0.00"),
)
TRADE_COLUMNS = (
    Column("date", "Data", "Date", 13, "yyyy-mm-dd"),
    Column("symbol", "Ativo", "Asset", 16),
    Column("side", "Lado", "Side", 9),
    Column("quantity", "Quantidade", "Quantity", 14, "#,##0.########"),
    Column("price", "Preço", "Price", 14, "#,##0.00######"),
    Column("fee", "Taxa", "Fee", 11, "#,##0.00"),
)
SHEETS = {"positions": ("Carteira", "Portfolio"), "trades": ("Operações", "Transactions")}
KINDS = {"pt": ("Ativo", "Caixa"), "en": ("Instrument", "Cash")}
SIDES = {"pt": ("compra", "venda"), "en": ("buy", "sell")}

HELP = {
    "pt": (
        "Como editar esta planilha",
        "Uma linha por posição. Ativo é o código como no Yahoo Finance: PETR4.SA, "
        "MXRF11.SA, AAPL, IWDA.AS, BTC-USD.",
        "Tipo: Ativo para ações, fundos, ETFs e cripto; Caixa para dinheiro parado, com a moeda "
        "no lugar do código (BRL, EUR, USD).",
        "Quantidade é obrigatória. Moeda pode ficar em branco: o app descobre pela cotação.",
        "Preço médio e Comprado em são opcionais e servem para calcular o seu resultado.",
        "As colunas em cinza (nome, bolsa, último preço, valor) são só para leitura e não "
        "são importadas.",
        "A aba Operações, se existir, é o registro de compras e vendas (lado: compra ou "
        "venda) e precisa terminar nas quantidades da carteira.",
        "Depois de editar, salve e use Importar Excel no app.",
    ),
    "en": (
        "How to edit this sheet",
        "One row per position. Asset is the ticker as on Yahoo Finance: AAPL, IWDA.AS, "
        "PETR4.SA, BTC-USD.",
        "Type: Instrument for stocks, funds, ETFs and crypto; Cash for money held, with the "
        "currency in place of the ticker (EUR, USD, BRL).",
        "Quantity is required. Currency can be left blank: the app reads it from the quote.",
        "Average cost and Bought on are optional and are used to compute your result.",
        "Grey columns (name, exchange, last price, value) are for reading only and are not "
        "imported.",
        "The Transactions sheet, if present, is the log of buys and sells (side: buy or sell) "
        "and must end with the portfolio's quantities.",
        "After editing, save and use Import Excel in the app.",
    ),
}

INK = "141413"
PAPER = "F7F6F2"
RULE = "D9D7CE"
MUTED = "8A897F"


def _fold(text: Any) -> str:
    """Lower case, no accents, single spaces: how headers and words are compared."""
    plain = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_]+", " ", plain).strip().lower()


def _aliases(columns: Iterable[Column]) -> dict[str, str]:
    """Every accepted header, folded, to its column key."""
    out: dict[str, str] = {}
    for c in columns:
        for name in (c.key, c.pt, c.en):
            out[_fold(name)] = c.key
    return out


POSITION_HEADERS = _aliases(POSITION_COLUMNS) | {
    "codigo": "symbol",
    "ticker": "symbol",
    "simbolo": "symbol",
    "qtd": "quantity",
    "quantidade de cotas": "quantity",
    "preco medio pago": "cost",
    "custo medio": "cost",
    "data de compra": "since",
}
TRADE_HEADERS = _aliases(TRADE_COLUMNS) | {
    "operacao": "side",
    "tipo": "side",
    "codigo": "symbol",
    "ticker": "symbol",
    "qtd": "quantity",
    "preco unitario": "price",
    "taxas": "fee",
    "custos": "fee",
}


# ---------------------------------------------------------------- export
def _style_header(sheet: Worksheet, columns: Sequence[Column], lang: str, info_from: int) -> None:
    head_font = Font(name="Segoe UI", bold=True, color=PAPER, size=10)
    info_font = Font(name="Segoe UI", bold=True, color=INK, size=10)
    head_fill = PatternFill("solid", fgColor=INK)
    info_fill = PatternFill("solid", fgColor=RULE)
    for i, c in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=i, value=c.pt if lang == "pt" else c.en)
        info = i > info_from
        cell.font = info_font if info else head_font
        cell.fill = info_fill if info else head_fill
        cell.alignment = Alignment(
            horizontal="left" if c.number_format == "General" else "right", vertical="center"
        )
        sheet.column_dimensions[get_column_letter(i)].width = c.width
    sheet.row_dimensions[1].height = 22
    sheet.freeze_panes = "A2"


def _write_rows(
    sheet: Worksheet, columns: Sequence[Column], rows: Sequence[dict[str, Any]], muted_from: int
) -> None:
    body = Font(name="Segoe UI", size=10, color=INK)
    muted = Font(name="Segoe UI", size=10, color=MUTED)
    line = Border(bottom=Side(style="thin", color=RULE))
    for r, row in enumerate(rows, start=2):
        for i, c in enumerate(columns, start=1):
            value = row.get(c.key)
            if isinstance(value, float) and not math.isfinite(value):
                value = None
            cell = sheet.cell(row=r, column=i, value=value)
            cell.number_format = c.number_format
            cell.font = muted if i > muted_from else body
            cell.border = line


def _date(text: Any) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def portfolio_to_xlsx(
    positions: Sequence[dict[str, Any]], trades: Sequence[dict[str, Any]], lang: str = "pt"
) -> bytes:
    """Write the positions (and the transaction log, if any) as an Excel workbook.

    ``positions`` use the API's fields (symbol, kind, quantity, currency, cost, since) plus,
    optionally, name, exchange and price, which are written for the reader only.
    """
    lang = "pt" if lang == "pt" else "en"
    instrument, cash = KINDS[lang]
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = SHEETS["positions"][0 if lang == "pt" else 1]
    columns = POSITION_COLUMNS + INFO_COLUMNS
    _style_header(sheet, columns, lang, len(POSITION_COLUMNS))
    rows: list[dict[str, Any]] = []
    for p in positions:
        is_cash = p.get("kind") == "cash"
        price = p.get("price")
        quantity = p.get("quantity")
        number = isinstance(price, int | float) and isinstance(quantity, int | float)
        rows.append(
            {
                "symbol": p.get("symbol"),
                "kind": cash if is_cash else instrument,
                "quantity": quantity,
                "currency": p.get("currency") or None,
                "cost": None if is_cash else p.get("cost"),
                "since": None if is_cash else _date(p.get("since")),
                "name": p.get("name") or None,
                "exchange": p.get("exchange") or None,
                "price": None if is_cash else price,
                "value": float(price) * float(quantity) if number else None,  # type: ignore[arg-type]
            }
        )
    _write_rows(sheet, columns, rows, len(POSITION_COLUMNS))
    kinds = DataValidation(
        type="list",
        formula1=f'"{instrument},{cash}"',
        allow_blank=False,
        sqref=f"B2:B{len(rows) + 200}",
    )
    sheet.add_data_validation(kinds)
    if trades:
        log = book.create_sheet(SHEETS["trades"][0 if lang == "pt" else 1])
        _style_header(log, TRADE_COLUMNS, lang, len(TRADE_COLUMNS))
        buy, sell = SIDES[lang]
        _write_rows(
            log,
            TRADE_COLUMNS,
            [
                {
                    "date": _date(t.get("date")),
                    "symbol": t.get("symbol"),
                    "side": buy if t.get("side") == "buy" else sell,
                    "quantity": _number(t.get("quantity")),
                    "price": _number(t.get("price")),
                    "fee": _number(t.get("fee")) or 0.0,
                }
                for t in trades
            ],
            len(TRADE_COLUMNS),
        )
        sides = DataValidation(
            type="list",
            formula1=f'"{buy},{sell}"',
            allow_blank=False,
            sqref=f"C2:C{len(trades) + 200}",
        )
        log.add_data_validation(sides)

    help_sheet = book.create_sheet("Como usar" if lang == "pt" else "How to use")
    help_sheet.column_dimensions["A"].width = 96
    lines = HELP[lang]
    for r, line in enumerate(lines, start=1):
        cell = help_sheet.cell(row=r, column=1, value=line)
        cell.font = Font(name="Segoe UI", size=11 if r == 1 else 10, bold=r == 1, color=INK)
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    book.properties.creator = "projeto-quant"
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# ---------------------------------------------------------------- import
def _number(value: Any) -> float | None:
    """Read a number from a cell: numbers as they are, text as 1,234.5 or 1.234,5."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = re.sub(r"[^\d,.\-]", "", str(value))
    if not text or text in {"-", ".", ","}:
        return None
    if "," in text and "." in text:
        # The separator that comes last is the decimal one.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        # One kind of separator: repeated, or followed by exactly three digits after a
        # non-zero head (1,234 / 1.234), it groups thousands; otherwise it is the decimal.
        for mark in ",.":
            if mark not in text:
                continue
            head, _, tail = text.rpartition(mark)
            grouping = text.count(mark) > 1 or (
                len(tail) == 3 and head.lstrip("-") not in {"", "0"}
            )
            text = text.replace(mark, "") if grouping else text.replace(mark, ".")
    try:
        return float(text)
    except ValueError:
        return None


def _iso_date(value: Any) -> str | None:
    """Read a date cell or text (2024-03-01, 01/03/2024) as YYYY-MM-DD, or None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return f"{value:%Y-%m-%d}"
    if isinstance(value, date):
        return f"{value:%Y-%m-%d}"
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}( .*)?", text):
        return text[:10]
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if match:  # day first, as written in Brazil and Europe
        day, month, year = (int(g) for g in match.groups())
        try:
            return f"{date(year, month, day):%Y-%m-%d}"
        except ValueError:
            return "invalid"
    return "invalid"


def _table(
    rows: Iterable[Sequence[Any]], aliases: dict[str, str]
) -> list[tuple[int, dict[str, Any]]]:
    """Rows as dicts keyed by column, with their line number; header found in the first rows."""
    found: dict[int, str] | None = None
    out: list[tuple[int, dict[str, Any]]] = []
    for number, row in enumerate(rows, start=1):
        cells = list(row)
        if found is None:
            keys = {i: aliases[_fold(v)] for i, v in enumerate(cells) if v and _fold(v) in aliases}
            if "symbol" in keys.values() and "quantity" in keys.values():
                found = keys
            elif number >= 10:
                break
            continue
        record = {key: cells[i] if i < len(cells) else None for i, key in found.items()}
        if all(v is None or str(v).strip() == "" for v in record.values()):
            continue
        out.append((number, record))
        if len(out) > MAX_ROWS:
            raise WorkbookError(f"At most {MAX_ROWS} rows.", f"No máximo {MAX_ROWS} linhas.")
    if found is None:
        raise WorkbookError(
            "No header with the columns Asset and Quantity was found.",
            "Não encontrei um cabeçalho com as colunas Ativo e Quantidade.",
        )
    return out


def _positions(rows: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line, r in rows:
        symbol = str(r.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        kind = _fold(r.get("kind") or "")
        cash = kind in {"caixa", "cash", "dinheiro"}
        quantity = _number(r.get("quantity"))
        if quantity is None or not quantity > 0:
            raise WorkbookError(
                f"Row {line}: the quantity of {symbol} must be a number above zero.",
                f"Linha {line}: a quantidade de {symbol} precisa ser um número maior que zero.",
            )
        currency = str(r.get("currency") or "").strip().upper()
        if cash:
            currency = currency or symbol
        since = None if cash else _iso_date(r.get("since"))
        if since == "invalid":
            raise WorkbookError(
                f"Row {line}: invalid purchase date for {symbol} (use YYYY-MM-DD).",
                f"Linha {line}: data de compra de {symbol} inválida "
                "(use AAAA-MM-DD ou DD/MM/AAAA).",
            )
        cost = None if cash else _number(r.get("cost"))
        out.append(
            {
                "symbol": symbol,
                "kind": "cash" if cash else "instrument",
                "quantity": quantity,
                "currency": currency,
                "cost": cost if cost and cost > 0 else None,
                "since": since,
            }
        )
    if not out:
        raise WorkbookError("The file has no positions.", "O arquivo não tem nenhuma posição.")
    return out


def _trades(rows: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line, r in rows:
        symbol = str(r.get("symbol") or "").strip().upper()
        side = _fold(r.get("side") or "")
        side = {"compra": "buy", "c": "buy", "venda": "sell", "v": "sell"}.get(side, side)
        when = _iso_date(r.get("date"))
        quantity, price = _number(r.get("quantity")), _number(r.get("price"))
        if (
            not symbol
            or side not in {"buy", "sell"}
            or when in {None, "invalid"}
            or not (quantity or 0) > 0
            or not (price or 0) > 0
        ):
            raise WorkbookError(
                f"Transactions, row {line}: needs date, asset, side (buy/sell), "
                "quantity and price.",
                f"Operações, linha {line}: precisa de data, ativo, lado (compra/venda), "
                "quantidade e preço.",
            )
        out.append(
            {
                "date": when,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "fee": _number(r.get("fee")) or 0.0,
            }
        )
    return out


def _csv_rows(data: bytes) -> list[list[str]]:
    text = data.decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    delimiter = ";" if first.count(";") > first.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if delimiter == ",":
        return rows
    # Spreadsheets in Portuguese save ";"-separated files with 1.234,5 numbers.
    number = re.compile(r"-?[\d.]+(,\d+)?")
    return [
        [c.replace(".", "").replace(",", ".") if number.fullmatch(c.strip()) else c for c in row]
        for row in rows
    ]


def portfolio_from_file(
    data: bytes, name: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read positions and transactions from an .xlsx workbook or a .csv file.

    In a workbook, the sheet with the Asset and Quantity headers holds the positions; a sheet
    named Transactions (or Operações) holds the log. A CSV holds positions only.

    Raises
    ------
    WorkbookError
        With a message in English and Portuguese naming the row that is wrong.

    """
    lower = name.lower()
    if lower.endswith(".csv"):
        return _positions(_table(_csv_rows(data), POSITION_HEADERS)), []
    if not lower.endswith((".xlsx", ".xlsm")):
        raise WorkbookError(
            "Use an Excel file (.xlsx) or a CSV.", "Use um arquivo do Excel (.xlsx) ou CSV."
        )
    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError) as error:
        raise WorkbookError(
            "The file could not be opened as an Excel workbook.",
            "Não foi possível abrir o arquivo como planilha do Excel.",
        ) from error
    trade_names = {_fold(n) for n in SHEETS["trades"]}
    positions: list[dict[str, Any]] | None = None
    trades: list[dict[str, Any]] = []
    first_error: WorkbookError | None = None
    try:
        for sheet in book.worksheets:
            rows = sheet.iter_rows(values_only=True)
            if _fold(sheet.title) in trade_names:
                trades = _trades(_table(rows, TRADE_HEADERS))
            elif positions is None:
                try:
                    positions = _positions(_table(rows, POSITION_HEADERS))
                except WorkbookError as error:
                    first_error = first_error or error
    finally:
        book.close()
    if positions is None:
        raise first_error or WorkbookError(
            "The file has no positions.", "O arquivo não tem nenhuma posição."
        )
    return positions, trades
