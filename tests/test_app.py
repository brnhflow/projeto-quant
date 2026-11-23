import http.client
import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from quant.app import AppConfig, BadRequestError, make_server, parse_positions
from quant.holdings import load_holdings

FIXTURES = Path(__file__).parent / "fixtures"
NOW = pd.Timestamp("2026-11-23 21:00", tz="UTC")


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def fake_fetch(url: str) -> Any:
    if "/v1/finance/search" in url:
        return _fixture("yahoo_search_petrobras")
    if "/v1/finance/lookup" in url:
        return _fixture("yahoo_lookup_petrobras")
    if "ASML.AS" in url:
        return _fixture("yahoo_asml_quote")
    if "PETR4.SA" in url:
        return _fixture("yahoo_petr4")
    if "frankfurter" in url:
        return _fixture("frankfurter")
    raise ConnectionError(f"HTTP 404 from {url}")


@pytest.fixture
def app(tmp_path: Path) -> Iterator[tuple[AppConfig, int]]:
    config = AppConfig(
        holdings_path=tmp_path / "private" / "holdings.csv",
        cache_dir=tmp_path / "cache",
        report_path=tmp_path / "reports" / "carteira.html",
        fetch=fake_fetch,
        now=lambda: NOW,
        pause=0,
    )
    server = make_server(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield config, server.server_address[1]  # type: ignore[misc]
    server.shutdown()
    server.server_close()


def _request(
    port: int,
    method: str,
    path: str,
    body: Any = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = json.dumps(body).encode() if body is not None else None
    all_headers = {"X-Quant-App": "1"}
    if data:
        all_headers["Content-Type"] = "application/json"
    all_headers.update(headers or {})
    conn.request(method, path, body=data, headers=all_headers)
    response = conn.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    conn.close()
    return result


POSITIONS = [
    {"symbol": "PETR4.SA", "quantity": 100, "currency": "BRL"},
    {"symbol": "ASML.AS", "quantity": 2.5, "currency": "EUR"},
]


# ---------------------------------------------------------------- pages


def test_editor_page_and_assets_are_served(app: tuple[AppConfig, int]) -> None:
    _, port = app

    status, headers, body = _request(port, "GET", "/")
    assert status == 200
    assert "Minha carteira" in body.decode()
    assert headers["Content-Type"].startswith("text/html")
    for asset in ("/base.css", "/editor.css", "/editor.js"):
        assert _request(port, "GET", asset)[0] == 200


def test_report_redirects_to_editor_before_first_analysis(app: tuple[AppConfig, int]) -> None:
    _, port = app

    status, headers, _ = _request(port, "GET", "/report")

    assert status == 302
    assert headers["Location"] == "/"


def test_unknown_path_is_404(app: tuple[AppConfig, int]) -> None:
    assert _request(app[1], "GET", "/nope")[0] == 404


# ---------------------------------------------------------------- search and quote


def test_search_returns_holdable_instruments(app: tuple[AppConfig, int]) -> None:
    status, _, body = _request(app[1], "GET", "/api/search?q=petrobras")

    assert status == 200
    results = json.loads(body)["results"]
    assert "PETR4.SA" in [r["symbol"] for r in results]


def test_empty_search_returns_nothing_without_network(app: tuple[AppConfig, int]) -> None:
    status, _, body = _request(app[1], "GET", "/api/search?q=")

    assert status == 200
    assert json.loads(body) == {"results": [], "next": None}


def test_search_lists_every_match_and_pages(app: tuple[AppConfig, int]) -> None:
    status, _, body = _request(app[1], "GET", "/api/search?q=petrobras")

    data = json.loads(body)
    symbols = [r["symbol"] for r in data["results"]]
    assert status == 200
    assert len(symbols) > 7  # more than the search API alone ever returns
    assert len(symbols) == len(set(symbols))
    assert {"PETR3.SA", "PETR4.SA", "PBR"} <= set(symbols)
    assert data["next"] == 25  # 44 matches, 25 per page

    _, _, body = _request(app[1], "GET", "/api/search?q=petrobras&start=25")
    assert json.loads(body)["next"] is None


def test_search_survives_one_source_down(app: tuple[AppConfig, int]) -> None:
    def lookup_down(url: str) -> Any:
        if "/v1/finance/lookup" in url:
            raise ConnectionError("HTTP 503")
        return fake_fetch(url)

    app[0].fetch = lookup_down
    status, _, body = _request(app[1], "GET", "/api/search?q=petrobras")

    assert status == 200
    assert "PETR4.SA" in [r["symbol"] for r in json.loads(body)["results"]]


def test_search_with_every_source_down_is_a_gateway_error(app: tuple[AppConfig, int]) -> None:
    def down(url: str) -> Any:
        raise ConnectionError("HTTP 503")

    app[0].fetch = down
    status, _, body = _request(app[1], "GET", "/api/search?q=petrobras")

    assert status == 502
    assert "indisponível" in json.loads(body)["error"]


@pytest.mark.parametrize("start", ["-1", "abc", "5000"])
def test_search_rejects_bad_page(app: tuple[AppConfig, int], start: str) -> None:
    status, _, body = _request(app[1], "GET", f"/api/search?q=petr&start={start}")

    assert status == 200
    assert json.loads(body)["results"] == []


def test_quote_gives_currency_and_price(app: tuple[AppConfig, int]) -> None:
    status, _, body = _request(app[1], "GET", "/api/quote?symbol=ASML.AS")

    assert status == 200
    quote = json.loads(body)
    assert quote["currency"] == "EUR"
    assert quote["price"] > 0


@pytest.mark.parametrize(("symbol", "status"), [("../etc", 400), ("NOPE.XX", 502)])
def test_quote_rejects_bad_or_unknown_symbols(
    app: tuple[AppConfig, int], symbol: str, status: int
) -> None:
    code, _, body = _request(app[1], "GET", f"/api/quote?symbol={symbol}")

    assert code == status
    assert "error" in json.loads(body)


# ---------------------------------------------------------------- analysis


def test_analysis_saves_portfolio_and_serves_report(app: tuple[AppConfig, int]) -> None:
    config, port = app

    status, _, body = _request(port, "POST", "/api/report", {"years": 1, "positions": POSITIONS})

    assert status == 200, body
    assert json.loads(body)["url"] == "/report"
    saved = load_holdings(config.holdings_path)
    assert saved["symbol"].tolist() == ["PETR4.SA", "ASML.AS"]
    assert saved.index.tolist() == ["PETR4", "ASML"]
    page_status, _, page = _request(port, "GET", "/report")
    assert page_status == 200
    assert '"editUrl": "/"' in page.decode()
    assert config.report_path.exists()
    holdings_status, _, holdings = _request(port, "GET", "/api/holdings")
    assert holdings_status == 200
    assert json.loads(holdings)["positions"][1] == {
        "symbol": "ASML.AS",
        "quantity": 2.5,
        "currency": "EUR",
        "kind": "instrument",
    }


def test_cash_is_analysed_saved_and_restored(app: tuple[AppConfig, int]) -> None:
    config, port = app
    positions = [
        *POSITIONS,
        {"symbol": "BRL", "quantity": 5000, "currency": "BRL", "kind": "cash"},
        {"symbol": "EUR", "quantity": 1000, "currency": "EUR", "kind": "cash"},
    ]

    status, _, body = _request(port, "POST", "/api/report", {"years": 1, "positions": positions})

    assert status == 200, body
    saved = load_holdings(config.holdings_path)
    assert saved.index.tolist() == ["PETR4", "ASML", "Caixa BRL", "Caixa EUR"]
    assert saved.loc["Caixa BRL", "source"] == "cash"
    _, _, holdings = _request(port, "GET", "/api/holdings")
    assert json.loads(holdings)["positions"][2] == {
        "symbol": "BRL",
        "quantity": 5000.0,
        "currency": "BRL",
        "kind": "cash",
    }


def test_cash_and_a_ticker_with_the_same_code_can_coexist() -> None:
    holdings, _ = parse_positions(
        {
            "positions": [
                {"symbol": "USD", "quantity": 3, "currency": "USD"},
                {"symbol": "USD", "quantity": 100, "currency": "USD", "kind": "cash"},
            ]
        }
    )

    assert holdings.index.tolist() == ["USD", "Caixa USD"]
    assert holdings["source"].tolist() == ["yahoo", "cash"]


def test_cash_in_another_currency_than_its_code_is_refused() -> None:
    with pytest.raises(BadRequestError, match="moeda precisa ser BRL"):
        parse_positions(
            {"positions": [{"symbol": "BRL", "quantity": 1, "currency": "EUR", "kind": "cash"}]}
        )


def test_wrong_currency_is_reported_to_the_page(app: tuple[AppConfig, int]) -> None:
    wrong = [{"symbol": "ASML.AS", "quantity": 1, "currency": "USD"}]

    status, _, body = _request(app[1], "POST", "/api/report", {"years": 1, "positions": wrong})

    assert status == 422
    assert "EUR" in json.loads(body)["error"]


def test_post_requires_json(app: tuple[AppConfig, int]) -> None:
    status, _, _ = _request(
        app[1], "POST", "/api/report", {"positions": POSITIONS}, {"Content-Type": "text/plain"}
    )

    assert status == 415


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_foreign_host_header_is_refused(app: tuple[AppConfig, int], method: str) -> None:
    body = {"positions": POSITIONS} if method == "POST" else None

    status, _, _ = _request(
        app[1],
        method,
        "/api/holdings" if method == "GET" else "/api/report",
        body,
        {"Host": "evil.example:80"},
    )

    assert status == 403


def test_invalid_positions_return_a_message(app: tuple[AppConfig, int]) -> None:
    bad = [{"symbol": "PETR4.SA", "quantity": 0, "currency": "BRL"}]

    status, _, body = _request(app[1], "POST", "/api/report", {"years": 1, "positions": bad})

    assert status == 400
    assert "maior que zero" in json.loads(body)["error"]


# ---------------------------------------------------------------- parse_positions


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ([], "inválido"),
        ({"positions": []}, "pelo menos um"),
        ({"positions": POSITIONS, "years": 4}, "histórico"),
        ({"positions": [POSITIONS[0], POSITIONS[0]]}, "duas vezes"),
        ({"positions": [{"symbol": "A", "quantity": True, "currency": "EUR"}]}, "maior que zero"),
        ({"positions": [{"symbol": "A", "quantity": "5", "currency": "EUR"}]}, "maior que zero"),
        ({"positions": [{"symbol": "A b", "quantity": 1, "currency": "EUR"}]}, "Código"),
        ({"positions": [{"symbol": "A", "quantity": 1, "currency": "euro"}]}, "Moeda"),
        (
            {"positions": [{"symbol": "A", "quantity": float("inf"), "currency": "EUR"}]},
            "maior que zero",
        ),
        (
            {"positions": [{"symbol": "A", "quantity": 10**400, "currency": "EUR"}]},
            "maior que zero",
        ),
        ({"positions": [{"symbol": "A", "quantity": 1e13, "currency": "EUR"}]}, "maior que zero"),
        (
            {
                "positions": [
                    {"symbol": "abc", "quantity": 1, "currency": "EUR"},
                    {"symbol": "ABC", "quantity": 1, "currency": "EUR"},
                ]
            },
            "duas vezes",
        ),
        (
            {
                "positions": [
                    {"symbol": f"A{i}", "quantity": 1, "currency": "EUR"} for i in range(101)
                ]
            },
            "máximo",
        ),
    ],
)
def test_parse_positions_rejects(body: Any, message: str) -> None:
    with pytest.raises(BadRequestError, match=message):
        parse_positions(body)


def test_parse_positions_builds_holdings() -> None:
    holdings, years = parse_positions({"positions": POSITIONS, "years": 3})

    assert years == 3
    assert holdings.loc["ASML", "quantity"] == 2.5
    assert holdings["source"].tolist() == ["yahoo", "yahoo"]


@pytest.mark.parametrize(
    "path", ["/api/search?q=petr", "/api/quote?symbol=ASML.AS", "/api/holdings"]
)
def test_api_requires_the_app_header(app: tuple[AppConfig, int], path: str) -> None:
    # A cross-site <img src=...> or link cannot add custom headers.
    status, _, _ = _request(app[1], "GET", path, headers={"X-Quant-App": ""})

    assert status == 403


def test_post_without_app_header_is_refused(app: tuple[AppConfig, int]) -> None:
    status, _, _ = _request(
        app[1], "POST", "/api/report", {"positions": POSITIONS}, {"X-Quant-App": ""}
    )

    assert status == 403


def test_symbols_with_ampersand_are_accepted() -> None:
    holdings, _ = parse_positions(
        {"positions": [{"symbol": "M&M.NS", "quantity": 3, "currency": "INR"}], "years": 1}
    )

    assert holdings["symbol"].tolist() == ["M&M.NS"]


def test_unexpected_error_still_answers(app: tuple[AppConfig, int]) -> None:
    config, port = app

    def broken(url: str) -> object:
        raise RuntimeError("boom")

    config.fetch = broken

    status, _, body = _request(port, "GET", "/api/search?q=petr")

    assert status == 500
    assert "inesperado" in json.loads(body)["error"]


def test_cash_only_portfolio_is_refused_with_a_clear_message() -> None:
    with pytest.raises(BadRequestError, match="além do caixa"):
        parse_positions(
            {"positions": [{"symbol": "EUR", "quantity": 1, "currency": "EUR", "kind": "cash"}]}
        )
