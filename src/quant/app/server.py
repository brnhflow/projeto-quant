"""Local web app: build the portfolio in the browser, analyse it with live data.

Runs only on this computer (127.0.0.1). The portfolio is saved to a local CSV; market data
is fetched from the public sources in :mod:`quant.data` when the user asks for an analysis.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import math
import re
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import pandas as pd

from quant.data import DataConfigError
from quant.data.http import fetch_bytes, fetch_json
from quant.data.market import Fetch
from quant.data.sources import (
    CASH,
    YAHOO,
    LiveQuote,
    SearchHit,
    merge_hits,
    parse_yahoo_live,
    parse_yahoo_lookup,
    parse_yahoo_search,
    parse_yahoo_snapshot,
    yahoo_live_url,
    yahoo_lookup_url,
    yahoo_search_url,
    yahoo_snapshot_url,
)
from quant.holdings import asset_labels, load_holdings, save_holdings
from quant.ledger import check_against_holdings, load_transactions, parse_transactions
from quant.pipeline import analyse_portfolio
from quant.workbook import WorkbookError, portfolio_from_file, portfolio_to_xlsx

SYMBOL = re.compile(r"^[A-Za-z0-9.\-=^&]{1,24}$")  # & appears in real tickers (M&M.NS)
CURRENCY = re.compile(r"^[A-Z]{3}$")
YEARS = (1, 2, 3, 5)
PAGE = 25  # lookup results per page
MAX_BODY = 512 * 1024
MAX_FILE = 256 * 1024  # an imported spreadsheet; base64 makes it a third larger in the body
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_POSITIONS = 100
MAX_TRANSACTIONS = 5000
MAX_QUANTITY = 1e12
API_HEADER = "X-Quant-App"
MAX_LIVE = 150  # symbols per live request
LIVE_TTL = 15.0  # seconds a live quote is reused, so many open tabs do not multiply requests
STATIC = {
    "/": ("quant.app", "static/editor.html", "text/html; charset=utf-8"),
    "/editor.css": ("quant.app", "static/editor.css", "text/css; charset=utf-8"),
    "/editor.js": ("quant.app", "static/editor.js", "text/javascript; charset=utf-8"),
    "/quantity.js": ("quant.app", "static/quantity.js", "text/javascript; charset=utf-8"),
    "/assets.js": ("quant.app", "static/assets.js", "text/javascript; charset=utf-8"),
    "/lang.js": ("quant.app", "static/lang.js", "text/javascript; charset=utf-8"),
    "/base.css": ("quant.report", "report.css", "text/css; charset=utf-8"),
}


@dataclass
class AppConfig:
    """Where the app keeps its files and how it reaches the network."""

    holdings_path: Path
    cache_dir: Path
    report_path: Path
    title: str = ""  # empty: the page shows "My portfolio" in its own language
    fetch: Fetch = fetch_json
    fetch_text: Callable[[str], bytes] = fetch_bytes  # news feeds and official rate files
    now: Callable[[], pd.Timestamp] = lambda: pd.Timestamp.now(tz="UTC")
    pause: float = 0.2
    report_html: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    live: dict[str, tuple[float, LiveQuote]] = field(default_factory=lambda: {})
    live_lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def transactions_path(self) -> Path:
        """The transaction log, saved next to the holdings."""
        return self.holdings_path.parent / "transactions.csv"


class BadRequestError(ValueError):
    """Input from the page that cannot be used; the message is shown to the user.

    Carries the message in English (``str(error)``) and in Portuguese (``error.pt``), so the
    page can show the one it is in.
    """

    def __init__(self, en: str, pt: str) -> None:
        super().__init__(en)
        self.pt = pt


def _labels(symbols: list[str], sources: list[str]) -> list[str]:
    """Report names: short tickers for instruments, "Cash BRL" for cash."""
    tickers = iter(
        asset_labels([s for s, src in zip(symbols, sources, strict=True) if src != CASH])
    )
    return [
        f"Cash {s}" if src == CASH else next(tickers)
        for s, src in zip(symbols, sources, strict=True)
    ]


def _cost(raw: Any, symbol: str) -> float:
    """Average price paid per unit, or NaN when not given."""
    if raw is None or raw == "":
        return math.nan
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise BadRequestError(
            f"The average cost of {symbol} must be a number.",
            f"Preço médio de {symbol} precisa ser um número.",
        )
    value = float(raw)
    if not math.isfinite(value) or not 0 < value <= MAX_QUANTITY:
        raise BadRequestError(
            f"The average cost of {symbol} must be above zero.",
            f"Preço médio de {symbol} precisa ser maior que zero.",
        )
    return value


def _since(raw: Any, symbol: str) -> pd.Timestamp | None:
    """Date of the first purchase (YYYY-MM-DD), not in the future, or None."""
    if raw is None or raw == "":
        return None
    try:
        date = pd.Timestamp(str(raw))
    except ValueError as error:
        raise BadRequestError(
            f"Invalid purchase date for {symbol}.", f"Data de compra de {symbol} inválida."
        ) from error
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw)) or not (
        pd.Timestamp("1990-01-01") <= date <= pd.Timestamp.now().normalize()
    ):
        raise BadRequestError(
            f"Invalid purchase date for {symbol}.", f"Data de compra de {symbol} inválida."
        )
    return date


def parse_positions(body: Any) -> tuple[pd.DataFrame, int]:
    """Validate the analysis request and turn it into holdings plus years of history.

    Parameters
    ----------
    body : Any
        Decoded JSON: ``{"positions": [{"symbol", "quantity", "currency", "kind"}],
        "years": int}``. ``kind`` is ``"cash"`` for money held in ``currency`` (then
        ``symbol`` is the currency code); anything else is an instrument on Yahoo.

    Returns
    -------
    tuple
        Holdings DataFrame (as :func:`quant.holdings.load_holdings` returns) and years.

    Raises
    ------
    BadRequestError
        With a message in English and Portuguese, for the page to show.

    """
    if not isinstance(body, dict):
        raise BadRequestError("Invalid request.", "Pedido inválido.")
    request = cast(dict[str, Any], body)
    raw = request.get("positions")
    if not isinstance(raw, list) or not raw:
        raise BadRequestError("Add at least one asset.", "Adicione pelo menos um ativo.")
    positions = cast(list[Any], raw)
    if len(positions) > MAX_POSITIONS:
        raise BadRequestError(
            f"At most {MAX_POSITIONS} assets.", f"No máximo {MAX_POSITIONS} ativos."
        )
    years = request.get("years", 2)
    if years not in YEARS:
        raise BadRequestError("Invalid history length.", "Período de histórico inválido.")

    symbols: list[str] = []
    quantities: list[float] = []
    currencies: list[str] = []
    sources: list[str] = []
    seen: set[tuple[bool, str]] = set()
    costs: list[float] = []
    dates: list[pd.Timestamp | None] = []
    for raw_item in positions:
        item = cast(dict[str, Any], raw_item) if isinstance(raw_item, dict) else {}
        symbol = str(item.get("symbol", ""))
        if not SYMBOL.match(symbol):
            raise BadRequestError(
                f"Invalid ticker: {symbol or '(empty)'}.",
                f"Código inválido: {symbol or '(vazio)'}.",
            )
        cash = item.get("kind") == "cash"
        key = (cash, symbol.upper())
        if key in seen:
            raise BadRequestError(f"{symbol} appears twice.", f"{symbol} aparece duas vezes.")
        seen.add(key)
        quantity: Any = item.get("quantity")
        bad_quantity = BadRequestError(
            f"The quantity of {symbol} must be a number above zero.",
            f"Quantidade de {symbol} precisa ser um número maior que zero.",
        )
        if isinstance(quantity, bool) or not isinstance(quantity, int | float):
            raise bad_quantity
        try:
            quantity = float(quantity)
        except OverflowError:
            quantity = math.inf
        if not math.isfinite(quantity) or not 0 < quantity <= MAX_QUANTITY:
            raise bad_quantity
        currency = str(item.get("currency", ""))
        if not CURRENCY.match(currency):
            raise BadRequestError(
                f"Unknown currency for {symbol}; remove the asset and add it again.",
                f"Moeda de {symbol} desconhecida; remova e adicione o ativo de novo.",
            )
        if cash and symbol != currency:
            raise BadRequestError(
                f"Cash in {symbol}: the currency must be {symbol}.",
                f"Caixa em {symbol}: a moeda precisa ser {symbol}.",
            )
        symbols.append(symbol)
        quantities.append(float(quantity))
        currencies.append(currency)
        sources.append(CASH if cash else YAHOO)
        costs.append(_cost(item.get("cost"), symbol))
        dates.append(_since(item.get("since"), symbol))

    if all(src == CASH for src in sources):
        raise BadRequestError(
            "Add at least one asset besides cash.", "Adicione pelo menos um ativo além do caixa."
        )
    holdings = pd.DataFrame(
        {
            "quantity": quantities,
            "currency": currencies,
            "source": sources,
            "symbol": symbols,
        },
        index=pd.Index(_labels(symbols, sources), name="asset"),
    )
    if any(math.isfinite(c) for c in costs):
        holdings["cost"] = costs
        holdings["since"] = pd.to_datetime(pd.Series(dates, index=holdings.index, dtype=object))
    return holdings, int(years)


def parse_transactions_request(body: Any, holdings: pd.DataFrame) -> pd.DataFrame | None:
    """Validate the optional transaction log sent with an analysis.

    ``body["transactions"]`` is a list of ``{"date", "symbol", "side", "quantity", "price",
    "fee"}``; absent or empty means no log. The log must end with the same units as the
    positions, so the two describe the same portfolio.
    """
    raw = cast(dict[str, Any], body).get("transactions") if isinstance(body, dict) else None
    if not raw:
        return None
    if not isinstance(raw, list) or len(cast(list[Any], raw)) > MAX_TRANSACTIONS:
        raise BadRequestError(
            f"The transaction log must be a list of at most {MAX_TRANSACTIONS} rows.",
            f"O registro de operações deve ter no máximo {MAX_TRANSACTIONS} linhas.",
        )
    columns = ("date", "symbol", "side", "quantity", "price", "fee")
    rows = [
        {c: str(cast(dict[str, Any], r).get(c, "") or "") for c in columns}
        if isinstance(r, dict)
        else {}
        for r in cast(list[Any], raw)
    ]
    try:
        trades = parse_transactions(pd.DataFrame(rows, columns=list(columns)))
        problems = check_against_holdings(trades, holdings)
    except ValueError as error:
        raise BadRequestError(
            f"Transaction log: {error}.", f"Registro de operações: {error}."
        ) from error
    if problems:
        listed = "; ".join(problems[:5])
        raise BadRequestError(
            f"The transaction log does not end with the positions' quantities: {listed}.",
            f"O registro de operações não termina nas quantidades das posições: {listed}.",
        )
    return trades


def save_transactions(trades: pd.DataFrame | None, path: Path) -> None:
    """Write the log as CSV, or delete the saved one when there is no log."""
    if trades is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    out = trades.assign(date=trades["date"].dt.strftime("%Y-%m-%d"))
    out.to_csv(path, index=False, lineterminator="\n")


def saved_transactions(config: AppConfig) -> list[dict[str, Any]]:
    """Return the saved transaction log, or an empty list."""
    if not config.transactions_path.exists():
        return []
    trades = load_transactions(config.transactions_path)
    return [
        {
            "date": f"{d:%Y-%m-%d}",
            "symbol": str(s),
            "side": str(side),
            "quantity": float(q),
            "price": float(p),
            "fee": float(f),
        }
        for d, s, side, q, p, f in zip(
            trades["date"],
            trades["symbol"],
            trades["side"],
            trades["quantity"],
            trades["price"],
            trades["fee"],
            strict=True,
        )
    ]


def analyse(
    config: AppConfig,
    holdings: pd.DataFrame,
    years: int,
    transactions: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Save the portfolio, fetch fresh data, build the report; returns the API response."""
    save_holdings(holdings, config.holdings_path)
    save_transactions(transactions, config.transactions_path)
    result = analyse_portfolio(
        holdings,
        years,
        config.cache_dir,
        title=config.title,
        fetch=config.fetch,
        now=config.now(),
        pause=config.pause,
        edit_url="/",
        fetch_text=config.fetch_text,
        transactions=transactions,
    )
    page = result.page
    config.report_html = page
    config.report_path.parent.mkdir(parents=True, exist_ok=True)
    config.report_path.write_text(page, encoding="utf-8")
    return {"url": "/report", "status": [asdict(s) for s in result.status]}


def search(config: AppConfig, text: str, start: int = 0) -> dict[str, Any]:
    """Instruments matching ``text``: the best-ranked first, then every other match.

    The first page joins the search API (well ranked, at most 7 results) with the
    lookup API (every match, poorly ranked); later pages come from the lookup alone.
    ``next`` is the ``start`` of the following page, or None when there is no more.

    Raises
    ------
    ConnectionError
        If neither source answers.

    """
    groups: list[list[SearchHit]] = []
    errors: list[str] = []
    if start == 0:
        try:
            groups.append(parse_yahoo_search(config.fetch(yahoo_search_url(text))))
        except (ConnectionError, ValueError) as error:
            errors.append(str(error))
    total = 0
    try:
        page, total = parse_yahoo_lookup(config.fetch(yahoo_lookup_url(text, start, PAGE)))
        groups.append(page)
    except (ConnectionError, ValueError) as error:
        errors.append(str(error))
    if not groups:
        raise ConnectionError("; ".join(errors))
    hits = [h for h in merge_hits(text, *groups) if SYMBOL.match(h.symbol)]
    following = start + PAGE
    return {
        "results": [asdict(h) for h in hits],
        "next": following if following < total else None,
    }


def saved_positions(config: AppConfig) -> list[dict[str, Any]]:
    """Return the last saved portfolio, or an empty list when there is none yet."""
    if not config.holdings_path.exists():
        return []
    holdings = load_holdings(config.holdings_path)
    return [
        {
            "symbol": str(row["symbol"]),
            "quantity": float(row["quantity"]),
            "currency": str(row["currency"]),
            "kind": "cash" if row["source"] == CASH else "instrument",
            "cost": float(row["cost"]) if "cost" in row and pd.notna(row["cost"]) else None,
            "since": f"{row['since']:%Y-%m-%d}"
            if "since" in row and pd.notna(row["since"])
            else None,
        }
        for _, row in holdings.iterrows()
        if row["source"] in (YAHOO, CASH)
    ]


def live_quotes(config: AppConfig, symbols: list[str]) -> dict[str, Any]:
    """Latest prices for ``symbols``, each reused for :data:`LIVE_TTL` seconds.

    Symbols that fail are listed in ``failed``; the others still come back.
    """
    now = time.monotonic()
    with config.live_lock:
        fresh = {s: q for s, (t, q) in config.live.items() if s in symbols and now - t < LIVE_TTL}
    missing = [s for s in symbols if s not in fresh]

    def one(symbol: str) -> LiveQuote | None:
        try:
            return parse_yahoo_live(config.fetch(yahoo_live_url(symbol)), config.now())
        except (ConnectionError, ValueError):
            return None

    failed: list[str] = []
    if missing:
        with ThreadPoolExecutor(max_workers=8) as pool:
            got = dict(zip(missing, pool.map(one, missing), strict=True))
        with config.live_lock:
            for symbol, q in got.items():
                if q is None:
                    failed.append(symbol)
                else:
                    config.live[symbol] = (now, q)
                    fresh[symbol] = q
    return {
        "asOf": config.now().isoformat(),
        "quotes": {
            s: {
                "price": q.price,
                "previousClose": q.previous_close,
                "time": q.time,
                "currency": q.currency,
                "open": q.open,
            }
            for s, q in fresh.items()
        },
        "failed": failed,
    }


def export_workbook(body: Any) -> bytes:
    """Write the editor's current portfolio as an Excel file; nothing is saved on the server."""
    request = cast(dict[str, Any], body) if isinstance(body, dict) else {}
    positions: Any = request.get("positions")
    trades: Any = request.get("transactions") or []
    if not isinstance(positions, list) or not isinstance(trades, list):
        raise BadRequestError("Invalid request.", "Pedido inválido.")
    rows = [cast(dict[str, Any], p) for p in cast(list[Any], positions) if isinstance(p, dict)]
    log = [cast(dict[str, Any], t) for t in cast(list[Any], trades) if isinstance(t, dict)]
    if len(rows) > MAX_POSITIONS or len(log) > MAX_TRANSACTIONS:
        raise BadRequestError("Too many rows.", "Linhas demais.")
    return portfolio_to_xlsx(rows, log, str(request.get("lang", "pt")))


def import_workbook(body: Any) -> dict[str, Any]:
    """Positions and transactions read from an uploaded .xlsx or .csv (sent as base64)."""
    request = cast(dict[str, Any], body) if isinstance(body, dict) else {}
    name, content = str(request.get("name", "")), request.get("content")
    if not isinstance(content, str):
        raise BadRequestError("No file was sent.", "Nenhum arquivo foi enviado.")
    try:
        data = base64.b64decode(content, validate=True)
    except (binascii.Error, ValueError) as error:
        raise BadRequestError(
            "The file did not arrive whole.", "O arquivo chegou incompleto."
        ) from error
    if len(data) > MAX_FILE:
        raise BadRequestError(
            f"The file is larger than {MAX_FILE // 1024} KB.",
            f"O arquivo passa de {MAX_FILE // 1024} KB.",
        )
    try:
        positions, trades = portfolio_from_file(data, name)
    except WorkbookError as error:
        raise BadRequestError(str(error), error.pt) from error
    if len(positions) > MAX_POSITIONS:
        raise BadRequestError(
            f"At most {MAX_POSITIONS} assets.", f"No máximo {MAX_POSITIONS} ativos."
        )
    return {"positions": positions, "transactions": trades}


def make_handler(config: AppConfig) -> type[BaseHTTPRequestHandler]:
    """Request handler bound to ``config``."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "quant-app"

        def log_message(self, format: str, *args: Any) -> None:
            return  # keep the terminal quiet; errors are returned to the page

        # ---------------------------------------------------------- helpers
        def _allowed_host(self) -> bool:
            # Blocks DNS-rebinding: a page on another site cannot reach us by a name
            # that resolves to 127.0.0.1, because its Host header would not match.
            port = int(getattr(self.server, "server_port", 0))
            return self.headers.get("Host", "") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _error(self, status: int, message: str, message_pt: str | None = None) -> None:
            # English for "error"; the page shows "error_pt" when it is in Portuguese.
            self._json(status, {"error": message, "error_pt": message_pt or message})

        # ---------------------------------------------------------- routes
        def do_GET(self) -> None:
            self._guarded(self._get)

        def do_POST(self) -> None:
            self._guarded(self._post)

        def _guarded(self, route: Callable[[], None]) -> None:
            # Any unexpected failure still answers the page instead of dropping the
            # connection; the details go to the terminal.
            try:
                route()
            except Exception as error:
                print(f"unexpected error on {self.path}: {error!r}", file=sys.stderr)
                with contextlib.suppress(OSError):
                    self._error(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        "Unexpected error; see the terminal.",
                        "Erro inesperado; veja o terminal.",
                    )

        def _get(self) -> None:
            if not self._allowed_host():
                self._error(HTTPStatus.FORBIDDEN, "Host not allowed.", "Host não permitido.")
                return
            url = urlparse(self.path)
            if url.path.startswith("/api/") and self.headers.get(API_HEADER) != "1":
                self._error(
                    HTTPStatus.FORBIDDEN,
                    "Request from outside the app.",
                    "Pedido fora do aplicativo.",
                )
                return
            query = parse_qs(url.query)
            if url.path in STATIC:
                package, name, kind = STATIC[url.path]
                body = resources.files(package).joinpath(name).read_bytes()
                self._send(HTTPStatus.OK, body, kind)
            elif url.path == "/report":
                if config.report_html is None:
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", "/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self._send(
                    HTTPStatus.OK, config.report_html.encode("utf-8"), "text/html; charset=utf-8"
                )
            elif url.path == "/api/holdings":
                try:
                    self._json(
                        HTTPStatus.OK,
                        {
                            "positions": saved_positions(config),
                            "transactions": saved_transactions(config),
                        },
                    )
                except ValueError as error:
                    self._error(
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                        f"The saved portfolio has a problem: {error}",
                        f"Carteira salva com problema: {error}",
                    )
            elif url.path == "/api/search":
                text = (query.get("q") or [""])[0].strip()
                start = (query.get("start") or ["0"])[0]
                if not 1 <= len(text) <= 60 or not start.isdigit() or int(start) > 1000:
                    self._json(HTTPStatus.OK, {"results": [], "next": None})
                    return
                try:
                    self._json(HTTPStatus.OK, search(config, text, int(start)))
                except ConnectionError as error:
                    self._error(
                        HTTPStatus.BAD_GATEWAY,
                        f"Search unavailable right now ({error}).",
                        f"Busca indisponível agora ({error}).",
                    )
            elif url.path == "/api/live":
                raw = (query.get("symbols") or [""])[0]
                symbols = list(dict.fromkeys(x for x in raw.split(",") if x))
                if (
                    not symbols
                    or len(symbols) > MAX_LIVE
                    or not all(SYMBOL.match(x) for x in symbols)
                ):
                    self._error(HTTPStatus.BAD_REQUEST, "Invalid symbols.", "Códigos inválidos.")
                    return
                self._json(HTTPStatus.OK, live_quotes(config, symbols))
            elif url.path == "/api/quote":
                symbol = (query.get("symbol") or [""])[0]
                if not SYMBOL.match(symbol):
                    self._error(HTTPStatus.BAD_REQUEST, "Invalid ticker.", "Código inválido.")
                    return
                try:
                    snap = parse_yahoo_snapshot(
                        config.fetch(yahoo_snapshot_url(symbol)), config.now()
                    )
                except (ConnectionError, ValueError) as error:
                    self._error(
                        HTTPStatus.BAD_GATEWAY,
                        f"No quote for {symbol} ({error}).",
                        f"Sem cotação para {symbol} ({error}).",
                    )
                    return
                self._json(HTTPStatus.OK, asdict(snap))
            else:
                self._error(HTTPStatus.NOT_FOUND, "Page not found.", "Página não encontrada.")

        def _post(self) -> None:
            # Read the body before any answer: replying while the client is still sending
            # makes Windows reset the connection and the page sees a network error.
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                self.close_connection = True
                self._error(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    "Empty or oversized request.",
                    "Pedido vazio ou grande demais.",
                )
                return
            raw = self.rfile.read(length)
            if not self._allowed_host():
                self._error(HTTPStatus.FORBIDDEN, "Host not allowed.", "Host não permitido.")
                return
            path = urlparse(self.path).path
            if path not in {"/api/report", "/api/export", "/api/import"}:
                self._error(HTTPStatus.NOT_FOUND, "Page not found.", "Página não encontrada.")
                return
            if self.headers.get(API_HEADER) != "1":
                self._error(
                    HTTPStatus.FORBIDDEN,
                    "Request from outside the app.",
                    "Pedido fora do aplicativo.",
                )
                return
            # Requiring JSON forces a CORS preflight for cross-site requests, which this
            # server never approves, so other websites cannot trigger an analysis.
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send JSON.", "Envie JSON.")
                return
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                self._error(HTTPStatus.BAD_REQUEST, "Invalid request.", "Pedido inválido.")
                return
            if path == "/api/export":
                try:
                    self._send(HTTPStatus.OK, export_workbook(body), XLSX)
                except BadRequestError as error:
                    self._error(HTTPStatus.BAD_REQUEST, str(error), error.pt)
                return
            if path == "/api/import":
                try:
                    self._json(HTTPStatus.OK, import_workbook(body))
                except BadRequestError as error:
                    self._error(HTTPStatus.BAD_REQUEST, str(error), error.pt)
                return
            try:
                holdings, years = parse_positions(body)
                transactions = parse_transactions_request(body, holdings)
            except BadRequestError as error:
                self._error(HTTPStatus.BAD_REQUEST, str(error), error.pt)
                return
            if not config.lock.acquire(blocking=False):
                self._error(
                    HTTPStatus.CONFLICT,
                    "An analysis is already running.",
                    "Já existe uma análise em andamento.",
                )
                return
            try:
                self._json(HTTPStatus.OK, analyse(config, holdings, years, transactions))
            except DataConfigError as error:
                self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(error))
            except (ConnectionError, ValueError) as error:
                self._error(
                    HTTPStatus.BAD_GATEWAY,
                    f"Could not get the data: {error}",
                    f"Não foi possível obter os dados: {error}",
                )
            finally:
                config.lock.release()

    return Handler


def make_server(config: AppConfig, port: int = 0) -> ThreadingHTTPServer:
    """HTTP server on 127.0.0.1 (``port`` 0 picks a free one)."""
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(config))
