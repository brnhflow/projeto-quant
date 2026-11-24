import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from quant.data.market import MarketData
from quant.data.news import google_news_url, news_query, parse_google_news
from quant.data.sources import Quote, parse_yahoo_chart
from quant.pipeline import fetch_news
from quant.report.data import dividend_income, unusual_moves

FIXTURES = Path(__file__).parent / "fixtures"
NOW = pd.Timestamp("2026-11-23 21:00", tz="UTC")


# ---------------------------------------------------------------- queries and feed


@pytest.mark.parametrize(
    ("symbol", "name", "query", "language"),
    [
        ("PETR4.SA", "PETROBRAS PN N2", '"PETR4"', "pt"),
        ("ASML.AS", "ASML Holding N.V.", '"ASML" (stock OR shares OR earnings)', "en"),
        (
            "VOD.L",
            "Vodafone Group Public Limited Company",
            '"Vodafone" (stock OR shares OR earnings)',
            "en",
        ),
        ("BTC-USD", "Bitcoin USD", '"Bitcoin" (price OR crypto)', "en"),
        ("XYZ", "", '"XYZ" (stock OR shares OR earnings)', "en"),
    ],
)
def test_news_query_uses_ticker_on_b3_and_clean_name_elsewhere(
    symbol: str, name: str, query: str, language: str
) -> None:
    assert news_query(symbol, name) == (query, language)


def test_news_url_is_a_recent_search_in_the_right_edition() -> None:
    url = google_news_url('"PETR4"', "pt")

    assert url.startswith("https://news.google.com/rss/search?")
    assert "when%3A14d" in url
    assert "hl=pt-BR" in url


def test_feed_gives_newest_first_with_source_removed_from_title() -> None:
    headlines = parse_google_news((FIXTURES / "google_news_petr4.xml").read_bytes())

    assert len(headlines) == 5
    assert all(h.url.startswith("https://") for h in headlines)
    assert [h.published for h in headlines] == sorted(
        (h.published for h in headlines), reverse=True
    )
    assert all(not h.title.endswith(f" - {h.source}") for h in headlines)


def test_feed_skips_items_without_safe_link_or_date() -> None:
    rss = b"""<rss><channel>
      <item><title>Ok - Src</title><link>https://a.b/c</link><source>Src</source>
        <pubDate>Mon, 23 Nov 2026 12:00:00 GMT</pubDate></item>
      <item><title>Script</title><link>javascript:alert(1)</link>
        <pubDate>Mon, 23 Nov 2026 12:00:00 GMT</pubDate></item>
      <item><title>No date</title><link>https://a.b/d</link></item>
    </channel></rss>"""

    (only,) = parse_google_news(rss)

    assert only.title == "Ok"
    assert only.source == "Src"


def test_feed_that_is_not_xml_is_an_error() -> None:
    with pytest.raises(ValueError):
        parse_google_news(b"<html>nope")


# ---------------------------------------------------------------- dividends


def test_chart_dividends_are_read_in_major_units() -> None:
    payload = json.loads((FIXTURES / "yahoo_vod_dividends.json").read_text(encoding="utf-8"))

    quote = parse_yahoo_chart(payload, NOW)

    assert quote.name == "Vodafone Group Public Limited Company"
    assert quote.kind == "EQUITY"
    assert quote.dividends is not None
    assert quote.dividends.loc["2025-06-05"] == pytest.approx(0.019542)  # 1.9542 pence


def _quote(dividends: dict[str, float]) -> Quote:
    paid = pd.Series({pd.Timestamp(k): v for k, v in dividends.items()}, dtype=float)
    return Quote(pd.Series(dtype=float), "BRL", False, NOW, dividends=paid)


def test_income_counts_the_last_twelve_months_in_euro() -> None:
    details = {"A": _quote({"2025-11-01": 9.0, "2026-03-10": 1.0, "2026-09-10": 0.5})}

    income = dividend_income(
        details,
        pd.Series({"A": 100.0}),
        pd.Series({"BRL": 0.16}),
        pd.Series({"A": 3200.0}),
        pd.Series({"A": "BRL"}),
        pd.Timestamp("2026-11-20"),
        "EUR",
    )

    assert income is not None
    (row,) = income["rows"]
    assert row["payments"] == 2  # November 2025 is more than a year ago
    assert row["amount"] == pytest.approx(1.5 * 100 * 0.16)
    assert row["yield"] == pytest.approx(24 / 3200)
    assert income["total"] == pytest.approx(24.0)


def test_no_income_without_dividends() -> None:
    details = {"A": _quote({})}

    assert (
        dividend_income(
            details,
            pd.Series({"A": 1.0}),
            pd.Series(dtype=float),
            pd.Series({"A": 1.0}),
            pd.Series({"A": "EUR"}),
            pd.Timestamp("2026-11-20"),
            "EUR",
        )
        is None
    )


# ---------------------------------------------------------------- unusual moves


def test_a_jump_far_beyond_the_usual_size_is_flagged() -> None:
    days = pd.bdate_range("2025-01-01", periods=300)
    rng = np.random.default_rng(1)
    calm = 100 * np.exp(rng.normal(0, 0.01, 300).cumsum())
    jump = calm.copy()
    jump[-1] = jump[-2] * 0.9  # -10% on a 1% daily-volatility asset
    local = pd.DataFrame({"CALM": calm, "JUMP": jump}, index=days)

    moves = unusual_moves(local)

    assert moves["JUMP"]["unusual"]
    assert moves["JUMP"]["day"] == pytest.approx(-0.1)
    assert moves["JUMP"]["zDay"] < -5
    assert not moves["CALM"]["unusual"]


def test_moves_need_enough_history() -> None:
    days = pd.bdate_range("2025-01-01", periods=30)
    assert unusual_moves(pd.DataFrame({"A": np.linspace(1, 2, 30)}, index=days)) == {}


# ---------------------------------------------------------------- fetching


def test_news_is_fetched_for_stocks_only_and_failures_stay_local() -> None:
    holdings = pd.DataFrame(
        {
            "quantity": 1.0,
            "currency": ["BRL", "EUR", "EUR", "EUR"],
            "source": ["yahoo", "yahoo", "yahoo", "cash"],
            "symbol": ["PETR4.SA", "ASML.AS", "IWDA.AS", "EUR"],
        },
        index=pd.Index(["PETR4", "ASML", "IWDA", "Caixa EUR"], name="asset"),
    )
    empty = pd.Series(dtype=float)
    details = {
        "PETR4": Quote(empty, "BRL", False, NOW, name="PETROBRAS PN N2", kind="EQUITY"),
        "ASML": Quote(empty, "EUR", False, NOW, name="ASML Holding N.V.", kind="EQUITY"),
        "IWDA": Quote(empty, "EUR", False, NOW, name="iShares Core MSCI World", kind="ETF"),
    }
    market = MarketData(pd.DataFrame(), pd.DataFrame(), [], details)
    asked: list[str] = []

    def fetch_text(url: str) -> bytes:
        asked.append(url)
        if "ASML" in url:
            raise ConnectionError("HTTP 503")
        return (FIXTURES / "google_news_petr4.xml").read_bytes()

    news: dict[str, Any] = fetch_news(holdings, market, fetch_text)

    assert set(news) == {"PETR4", "ASML"}  # no ETF, no cash
    assert news["ASML"] is None
    assert len(news["PETR4"]) == 5
    assert len(asked) == 2


def test_two_dividends_on_the_same_date_both_count() -> None:
    payload = json.loads((FIXTURES / "yahoo_vod_dividends.json").read_text(encoding="utf-8"))
    events = payload["chart"]["result"][0]["events"]["dividends"]
    first = next(iter(events.values()))
    events["extra"] = {"amount": 1.0, "date": first["date"]}  # special dividend, same day

    quote = parse_yahoo_chart(payload, NOW)

    assert quote.dividends is not None
    assert quote.dividends.loc["2025-06-05"] == pytest.approx(0.029542)


def test_raw_closes_are_kept_beside_adjusted_prices() -> None:
    payload = json.loads((FIXTURES / "yahoo_vod_dividends.json").read_text(encoding="utf-8"))

    quote = parse_yahoo_chart(payload, NOW)

    assert quote.close is not None
    first = quote.prices.index[0]
    # Adjusted prices are lowered by every later dividend; quoted closes are not.
    assert quote.close.loc[first] > quote.prices.loc[first]
    assert quote.close.iloc[-1] == pytest.approx(quote.prices.iloc[-1], rel=1e-3)
