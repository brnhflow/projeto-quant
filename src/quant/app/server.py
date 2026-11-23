"""Local web app: build the portfolio in the browser, analyse it with live data.

Runs only on this computer (127.0.0.1). The portfolio is saved to a local CSV; market data
is fetched from the public sources in :mod:`quant.data` when the user asks for an analysis.
"""

from __future__ import annotations

import contextlib
import json
import math
import re
import sys
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import pandas as pd

from quant.data import DataConfigError
from quant.data.http import fetch_json
from quant.data.market import Fetch
from quant.data.sources import (
    CASH,
    YAHOO,
    SearchHit,
    merge_hits,
    parse_yahoo_lookup,
    parse_yahoo_search,
    parse_yahoo_snapshot,
    yahoo_lookup_url,
    yahoo_search_url,
    yahoo_snapshot_url,
)
from quant.holdings import asset_labels, load_holdings, save_holdings
from quant.pipeline import analyse_portfolio

SYMBOL = re.compile(r"^[A-Za-z0-9.\-=^&]{1,24}$")  # & appears in real tickers (M&M.NS)
CURRENCY = re.compile(r"^[A-Z]{3}$")
YEARS = (1, 2, 3, 5)
PAGE = 25  # lookup results per page
MAX_BODY = 64 * 1024
MAX_POSITIONS = 100
MAX_QUANTITY = 1e12
API_HEADER = "X-Quant-App"
STATIC = {
    "/": ("quant.app", "static/editor.html", "text/html; charset=utf-8"),
    "/editor.css": ("quant.app", "static/editor.css", "text/css; charset=utf-8"),
    "/editor.js": ("quant.app", "static/editor.js", "text/javascript; charset=utf-8"),
    "/quantity.js": ("quant.app", "static/quantity.js", "text/javascript; charset=utf-8"),
    "/base.css": ("quant.report", "report.css", "text/css; charset=utf-8"),
}


@dataclass
class AppConfig:
    """Where the app keeps its files and how it reaches the network."""

    holdings_path: Path
    cache_dir: Path
    report_path: Path
    title: str = "Minha carteira"
    fetch: Fetch = fetch_json
    now: Callable[[], pd.Timestamp] = lambda: pd.Timestamp.now(tz="UTC")
    pause: float = 0.2
    report_html: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class BadRequestError(ValueError):
    """Input from the page that cannot be used; the message is shown to the user."""


def _labels(symbols: list[str], sources: list[str]) -> list[str]:
    """Report names: short tickers for instruments, "Caixa BRL" for cash."""
    tickers = iter(
        asset_labels([s for s, src in zip(symbols, sources, strict=True) if src != CASH])
    )
    return [
        f"Caixa {s}" if src == CASH else next(tickers)
        for s, src in zip(symbols, sources, strict=True)
    ]


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
        With a message in Portuguese, for the page to show.

    """
    if not isinstance(body, dict):
        raise BadRequestError("Pedido inválido.")
    request = cast(dict[str, Any], body)
    raw = request.get("positions")
    if not isinstance(raw, list) or not raw:
        raise BadRequestError("Adicione pelo menos um ativo.")
    positions = cast(list[Any], raw)
    if len(positions) > MAX_POSITIONS:
        raise BadRequestError(f"No máximo {MAX_POSITIONS} ativos.")
    years = request.get("years", 2)
    if years not in YEARS:
        raise BadRequestError("Período de histórico inválido.")

    symbols: list[str] = []
    quantities: list[float] = []
    currencies: list[str] = []
    sources: list[str] = []
    seen: set[tuple[bool, str]] = set()
    for raw_item in positions:
        item = cast(dict[str, Any], raw_item) if isinstance(raw_item, dict) else {}
        symbol = str(item.get("symbol", ""))
        if not SYMBOL.match(symbol):
            raise BadRequestError(f"Código inválido: {symbol or '(vazio)'}.")
        cash = item.get("kind") == "cash"
        key = (cash, symbol.upper())
        if key in seen:
            raise BadRequestError(f"{symbol} aparece duas vezes.")
        seen.add(key)
        quantity: Any = item.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int | float):
            raise BadRequestError(f"Quantidade de {symbol} precisa ser um número maior que zero.")
        try:
            quantity = float(quantity)
        except OverflowError:
            quantity = math.inf
        if not math.isfinite(quantity) or not 0 < quantity <= MAX_QUANTITY:
            raise BadRequestError(f"Quantidade de {symbol} precisa ser um número maior que zero.")
        currency = str(item.get("currency", ""))
        if not CURRENCY.match(currency):
            raise BadRequestError(
                f"Moeda de {symbol} desconhecida; remova e adicione o ativo de novo."
            )
        if cash and symbol != currency:
            raise BadRequestError(f"Caixa em {symbol}: a moeda precisa ser {symbol}.")
        symbols.append(symbol)
        quantities.append(float(quantity))
        currencies.append(currency)
        sources.append(CASH if cash else YAHOO)

    if all(src == CASH for src in sources):
        raise BadRequestError("Adicione pelo menos um ativo além do caixa.")
    holdings = pd.DataFrame(
        {
            "quantity": quantities,
            "currency": currencies,
            "source": sources,
            "symbol": symbols,
        },
        index=pd.Index(_labels(symbols, sources), name="asset"),
    )
    return holdings, int(years)


def analyse(config: AppConfig, holdings: pd.DataFrame, years: int) -> dict[str, Any]:
    """Save the portfolio, fetch fresh data, build the report; returns the API response."""
    save_holdings(holdings, config.holdings_path)
    result = analyse_portfolio(
        holdings,
        years,
        config.cache_dir,
        title=config.title,
        fetch=config.fetch,
        now=config.now(),
        pause=config.pause,
        edit_url="/",
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
        }
        for _, row in holdings.iterrows()
        if row["source"] in (YAHOO, CASH)
    ]


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

        def _error(self, status: int, message: str) -> None:
            self._json(status, {"error": message})

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
                        HTTPStatus.INTERNAL_SERVER_ERROR, "Erro inesperado; veja o terminal."
                    )

        def _get(self) -> None:
            if not self._allowed_host():
                self._error(HTTPStatus.FORBIDDEN, "Host não permitido.")
                return
            url = urlparse(self.path)
            if url.path.startswith("/api/") and self.headers.get(API_HEADER) != "1":
                self._error(HTTPStatus.FORBIDDEN, "Pedido fora do aplicativo.")
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
                    self._json(HTTPStatus.OK, {"positions": saved_positions(config)})
                except ValueError as error:
                    self._error(
                        HTTPStatus.UNPROCESSABLE_ENTITY, f"Carteira salva com problema: {error}"
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
                    self._error(HTTPStatus.BAD_GATEWAY, f"Busca indisponível agora ({error}).")
            elif url.path == "/api/quote":
                symbol = (query.get("symbol") or [""])[0]
                if not SYMBOL.match(symbol):
                    self._error(HTTPStatus.BAD_REQUEST, "Código inválido.")
                    return
                try:
                    snap = parse_yahoo_snapshot(
                        config.fetch(yahoo_snapshot_url(symbol)), config.now()
                    )
                except (ConnectionError, ValueError) as error:
                    self._error(HTTPStatus.BAD_GATEWAY, f"Sem cotação para {symbol} ({error}).")
                    return
                self._json(HTTPStatus.OK, asdict(snap))
            else:
                self._error(HTTPStatus.NOT_FOUND, "Página não encontrada.")

        def _post(self) -> None:
            # Read the body before any answer: replying while the client is still sending
            # makes Windows reset the connection and the page sees a network error.
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                self.close_connection = True
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Pedido vazio ou grande demais.")
                return
            raw = self.rfile.read(length)
            if not self._allowed_host():
                self._error(HTTPStatus.FORBIDDEN, "Host não permitido.")
                return
            if urlparse(self.path).path != "/api/report":
                self._error(HTTPStatus.NOT_FOUND, "Página não encontrada.")
                return
            if self.headers.get(API_HEADER) != "1":
                self._error(HTTPStatus.FORBIDDEN, "Pedido fora do aplicativo.")
                return
            # Requiring JSON forces a CORS preflight for cross-site requests, which this
            # server never approves, so other websites cannot trigger an analysis.
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Envie JSON.")
                return
            try:
                holdings, years = parse_positions(json.loads(raw))
            except json.JSONDecodeError:
                self._error(HTTPStatus.BAD_REQUEST, "Pedido inválido.")
                return
            except BadRequestError as error:
                self._error(HTTPStatus.BAD_REQUEST, str(error))
                return
            if not config.lock.acquire(blocking=False):
                self._error(HTTPStatus.CONFLICT, "Já existe uma análise em andamento.")
                return
            try:
                self._json(HTTPStatus.OK, analyse(config, holdings, years))
            except DataConfigError as error:
                self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(error))
            except (ConnectionError, ValueError) as error:
                self._error(HTTPStatus.BAD_GATEWAY, f"Não foi possível obter os dados: {error}")
            finally:
                config.lock.release()

    return Handler


def make_server(config: AppConfig, port: int = 0) -> ThreadingHTTPServer:
    """HTTP server on 127.0.0.1 (``port`` 0 picks a free one)."""
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(config))
