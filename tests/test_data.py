import io
import json
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from quant.data import DataConfigError, update_market_data
from quant.data.http import fetch_json
from quant.data.sources import (
    parse_frankfurter,
    parse_kraken_ohlc,
    parse_yahoo_chart,
    parse_yahoo_search,
    parse_yahoo_snapshot,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _utc(ts: int) -> pd.Timestamp:
    return pd.Timestamp(ts, unit="s", tz="UTC")


# ---------------------------------------------------------------- parsers (saved real responses)


def test_yahoo_b3_prices_dates_and_live_session() -> None:
    payload = _fixture("yahoo_petr4")
    meta = payload["chart"]["result"][0]["meta"]
    session = meta["currentTradingPeriod"]["regular"]

    during = parse_yahoo_chart(payload, now=_utc(session["start"] + 3600))
    after = parse_yahoo_chart(payload, now=_utc(session["end"] + 60))

    assert during.currency == "BRL"
    assert len(during.prices) == 5
    assert during.prices.index.is_monotonic_increasing
    # Bars are dated in São Paulo time: the session that opens 23 Nov is 23 Nov.
    assert during.prices.index[-1] == pd.Timestamp("2026-11-23")
    assert during.prices.iloc[-1] == pytest.approx(
        payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"][-1]
    )
    assert during.in_progress
    assert not after.in_progress


def test_yahoo_pence_are_converted_to_pounds() -> None:
    payload = _fixture("yahoo_vod_gbp")
    raw = payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"]

    quote = parse_yahoo_chart(payload, now=pd.Timestamp("2026-12-01", tz="UTC"))

    assert quote.currency == "GBP"
    assert quote.prices.iloc[0] == pytest.approx(raw[0] / 100)


def test_yahoo_error_and_empty_responses_raise() -> None:
    with pytest.raises(ValueError, match="Yahoo error"):
        parse_yahoo_chart(
            {"chart": {"error": {"code": "Not Found"}}}, now=pd.Timestamp.now(tz="UTC")
        )
    with pytest.raises(ValueError, match="no prices"):
        parse_yahoo_chart({"chart": {"result": []}}, now=pd.Timestamp.now(tz="UTC"))


def test_kraken_candles_and_open_day() -> None:
    payload = _fixture("kraken_xbtusd")
    candles = payload["result"]["XXBTZUSD"]
    last_day = pd.Timestamp(candles[-1][0], unit="s")

    open_day = parse_kraken_ohlc(
        payload, "USD", now=pd.Timestamp(last_day, tz="UTC") + pd.Timedelta(hours=10)
    )
    closed = parse_kraken_ohlc(
        payload, "USD", now=pd.Timestamp(last_day, tz="UTC") + pd.Timedelta(days=2)
    )

    assert open_day.prices.index[-1] == last_day
    assert open_day.prices.iloc[-1] == float(candles[-1][4])
    assert open_day.in_progress
    assert not closed.in_progress


def test_kraken_error_raises() -> None:
    with pytest.raises(ValueError, match="Kraken error"):
        parse_kraken_ohlc(
            {"error": ["EQuery:Unknown asset pair"]}, "USD", now=pd.Timestamp.now(tz="UTC")
        )


def test_frankfurter_rates_are_inverted_to_euros_per_unit() -> None:
    # The API says 1 EUR = 6.2838 BRL on 16 Nov, so 1 BRL = 1 / 6.2838 EUR.
    fx = parse_frankfurter(_fixture("frankfurter"))

    assert fx.loc["2026-11-16", "BRL"] == pytest.approx(1 / 6.2838)
    assert fx.loc["2026-11-20", "USD"] == pytest.approx(1 / 1.099)
    assert fx.index.is_monotonic_increasing


def test_frankfurter_empty_raises() -> None:
    with pytest.raises(ValueError, match="no rates"):
        parse_frankfurter({"rates": {}})


# ---------------------------------------------------------------- http retries


class _Response(io.BytesIO):
    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", Message(), io.BytesIO(b""))


def test_fetch_retries_rate_limits_then_succeeds() -> None:
    outcomes: list[Any] = [
        _http_error(429),
        urllib.error.URLError("timeout"),
        _Response(b'{"ok": 1}'),
    ]
    waits: list[float] = []

    def opener(request: Any, timeout: float) -> Any:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    assert fetch_json("https://x", opener=opener, sleep=waits.append, backoff=1.0) == {"ok": 1}
    assert waits == [1.0, 2.0]


def test_fetch_does_not_retry_client_errors() -> None:
    calls: list[int] = []

    def opener(request: Any, timeout: float) -> Any:
        calls.append(1)
        raise _http_error(404)

    with pytest.raises(ConnectionError, match="404"):
        fetch_json("https://x", opener=opener, sleep=lambda _: None)
    assert len(calls) == 1


def test_fetch_gives_up_after_retries() -> None:
    def opener(request: Any, timeout: float) -> Any:
        raise _http_error(503)

    with pytest.raises(ConnectionError, match="4 attempts"):
        fetch_json("https://x", opener=opener, sleep=lambda _: None, retries=3)


# ---------------------------------------------------------------- update with cache


def _holdings(rows: list[tuple[str, str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "quantity": [1.0] * len(rows),
            "currency": [r[1] for r in rows],
            "source": [r[2] for r in rows],
            "symbol": [r[3] for r in rows],
        },
        index=pd.Index([r[0] for r in rows], name="asset"),
    )


def _fake_fetch(fail: set[str]) -> Any:
    def fetch(url: str) -> Any:
        for key in fail:
            if key in url:
                raise ConnectionError(f"simulated outage for {key}")
        if "yahoo" in url:
            return _fixture("yahoo_petr4")
        if "kraken" in url:
            return _fixture("kraken_xbtusd")
        return _fixture("frankfurter")

    return fetch


START = pd.Timestamp("2026-11-01")
NOW = pd.Timestamp("2026-11-23 21:00", tz="UTC")


def test_update_downloads_caches_and_reports_status(tmp_path: Path) -> None:
    holdings = _holdings(
        [("PETR4", "BRL", "yahoo", "PETR4.SA"), ("BTC", "USD", "kraken", "XBTUSD")]
    )

    data = update_market_data(holdings, START, tmp_path, fetch=_fake_fetch(set()), now=NOW, pause=0)

    assert list(data.prices.columns) == ["PETR4", "BTC"]
    assert set(data.fx.columns) == {"BRL", "USD"}
    assert data.problems == []
    assert {s.name for s in data.status} == {"PETR4", "BTC", "FX"}
    assert (tmp_path / "yahoo_PETR4.SA.csv").exists()
    assert (tmp_path / "fx_EUR.csv").exists()


def test_failed_source_falls_back_to_cache_and_says_so(tmp_path: Path) -> None:
    holdings = _holdings([("PETR4", "BRL", "yahoo", "PETR4.SA")])
    first = update_market_data(
        holdings, START, tmp_path, fetch=_fake_fetch(set()), now=NOW, pause=0
    )

    second = update_market_data(
        holdings, START, tmp_path, fetch=_fake_fetch({"yahoo"}), now=NOW, pause=0
    )

    pd.testing.assert_series_equal(
        second.prices["PETR4"], first.prices["PETR4"], check_freq=False, check_names=False
    )
    (problem,) = second.problems
    assert problem.name == "PETR4"
    assert problem.from_cache
    assert "simulated outage" in str(problem.error)


def test_failure_without_cache_raises(tmp_path: Path) -> None:
    holdings = _holdings([("PETR4", "BRL", "yahoo", "PETR4.SA")])

    with pytest.raises(ConnectionError, match="no cached copy"):
        update_market_data(
            holdings, START, tmp_path, fetch=_fake_fetch({"yahoo"}), now=NOW, pause=0
        )


def test_currency_mismatch_is_a_configuration_error(tmp_path: Path) -> None:
    holdings = _holdings([("PETR4", "EUR", "yahoo", "PETR4.SA")])  # really BRL

    with pytest.raises(DataConfigError, match="BRL"):
        update_market_data(holdings, START, tmp_path, fetch=_fake_fetch(set()), now=NOW, pause=0)


def test_offline_uses_cache_without_network(tmp_path: Path) -> None:
    holdings = _holdings([("PETR4", "BRL", "yahoo", "PETR4.SA")])
    update_market_data(holdings, START, tmp_path, fetch=_fake_fetch(set()), now=NOW, pause=0)

    def no_network(url: str) -> Any:
        raise AssertionError("network used in offline mode")

    data = update_market_data(holdings, START, tmp_path, fetch=no_network, now=NOW, offline=True)

    assert data.problems == []
    assert all(s.from_cache for s in data.status)


# ---------------------------------------------------------------- search and snapshot


def test_search_keeps_holdable_instruments_in_rank_order() -> None:
    hits = parse_yahoo_search(_fixture("yahoo_search_petrobras"))

    symbols = [h.symbol for h in hits]
    assert "PETR4.SA" in symbols
    assert symbols.index("PBR") < symbols.index("PETR4.SA")  # source ranking preserved
    petr4 = next(h for h in hits if h.symbol == "PETR4.SA")
    assert petr4.exchange == "São Paulo"
    assert petr4.kind == "EQUITY"
    assert "  " not in petr4.name  # padded names are cleaned
    assert petr4.detail == "PETROBRAS PN N2"  # tells PN (PETR4) from ON (PETR3)
    petr3 = next(h for h in hits if h.symbol == "PETR3.SA")
    assert petr3.detail == "PETROBRAS ON N2"


def test_search_drops_futures() -> None:
    hits = parse_yahoo_search(_fixture("yahoo_search_bitcoin"))

    assert "BTC-USD" in [h.symbol for h in hits]
    assert next(h for h in hits if h.symbol == "BTC-USD").exchange == "Cripto"
    assert all(h.kind != "FUTURE" for h in hits)
    assert all(not h.symbol.endswith("=F") for h in hits)


def test_search_without_results() -> None:
    assert parse_yahoo_search({"quotes": []}) == []
    assert parse_yahoo_search({}) == []


def test_snapshot_has_name_exchange_currency_and_price() -> None:
    payload = _fixture("yahoo_asml_quote")

    snap = parse_yahoo_snapshot(payload, now=pd.Timestamp("2026-12-01", tz="UTC"))

    assert snap.symbol == "ASML.AS"
    assert snap.name == "ASML Holding N.V."
    assert snap.exchange == "Amsterdam"
    assert snap.currency == "EUR"
    assert snap.price == pytest.approx(
        payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"][-1]
    )
    assert not snap.in_progress


# ---------------------------------------------------------------- robustness of the review fixes


EMPTY_META: dict[str, Any] = {}
MISSING_META: dict[str, Any] = {"chart": {"result": [{"timestamp": [1], "meta": EMPTY_META}]}}


@pytest.mark.parametrize(
    "payload",
    [
        MISSING_META,  # meta keys missing
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [1],
                        "meta": {"exchangeTimezoneName": "UTC", "currency": "EUR"},
                        "indicators": {},
                    }
                ]
            }
        },
        {"chart": "nonsense"},
    ],
)
def test_malformed_yahoo_responses_become_value_errors(payload: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        parse_yahoo_chart(payload, now=NOW)


def test_malformed_response_falls_back_to_cache(tmp_path: Path) -> None:
    holdings = _holdings([("PETR4", "BRL", "yahoo", "PETR4.SA")])
    update_market_data(holdings, START, tmp_path, fetch=_fake_fetch(set()), now=NOW, pause=0)

    def malformed(url: str) -> Any:
        return MISSING_META if "yahoo" in url else _fixture("frankfurter")

    data = update_market_data(holdings, START, tmp_path, fetch=malformed, now=NOW, pause=0)

    (problem,) = data.problems
    assert problem.from_cache
    assert "unexpected response format" in str(problem.error)


def test_cache_in_another_currency_is_not_used(tmp_path: Path) -> None:
    update_market_data(
        _holdings([("PETR4", "BRL", "yahoo", "PETR4.SA")]),
        START,
        tmp_path,
        fetch=_fake_fetch(set()),
        now=NOW,
        pause=0,
    )
    # Same ticker, but now the holdings say USD: the BRL cache must not be reused as USD.
    holdings_usd = _holdings([("PETR4", "USD", "yahoo", "PETR4.SA")])

    with pytest.raises(ConnectionError, match="no cached copy in USD"):
        update_market_data(
            holdings_usd, START, tmp_path, fetch=_fake_fetch({"yahoo"}), now=NOW, pause=0
        )


def test_fx_cache_keeps_currencies_from_earlier_runs(tmp_path: Path) -> None:
    both = _holdings([("PETR4", "BRL", "yahoo", "PETR4.SA"), ("BTC", "USD", "kraken", "XBTUSD")])
    update_market_data(both, START, tmp_path, fetch=_fake_fetch(set()), now=NOW, pause=0)

    def only_brl(url: str) -> Any:
        payload = _fixture("frankfurter")
        payload["rates"] = {d: {"BRL": r["BRL"]} for d, r in payload["rates"].items()}
        return payload if "frankfurter" in url else _fake_fetch(set())(url)

    update_market_data(
        _holdings([("PETR4", "BRL", "yahoo", "PETR4.SA")]),
        START,
        tmp_path,
        fetch=only_brl,
        now=NOW,
        pause=0,
    )
    offline = update_market_data(
        both, START, tmp_path, fetch=_fake_fetch(set()), now=NOW, offline=True
    )

    assert set(offline.fx.columns) == {"BRL", "USD"}
