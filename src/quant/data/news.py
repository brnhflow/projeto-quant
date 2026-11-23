"""Recent headlines per asset from the Google News RSS feed.

Google News publishes search results as RSS (no key, no login). For a B3 stock the
ticker itself is the best query in Portuguese (``PETR4``); for other markets the company
name in English. Headlines are context for a move, never a signal: the report puts them
next to the moves that were unusual for that asset, which is where they help.

The feed is parsed with the standard library. Python 3.11+ ships an expat version that
refuses entity-expansion attacks, and the parser never fetches external resources.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlparse

import pandas as pd

# Legal forms, share classes and fund words that only add noise to a news search.
_NOISE = re.compile(
    r"\b(nv|sa|inc|corp|corporation|plc|ag|se|holding|holdings|ltd|limited|group|company|"
    r"co|the|public|ord|pn|on|unt|n1|n2|nm|ucits|usd|eur|brl|class|cl|acc|dist)\b",
    re.IGNORECASE,
)
_B3 = re.compile(r"^([A-Z]{4}\d{1,2})\.SA$")


@dataclass(frozen=True)
class Headline:
    """One news item."""

    title: str
    source: str
    url: str
    published: pd.Timestamp


def news_query(symbol: str, name: str) -> tuple[str, str] | None:
    """Search terms and language for an asset, or None when news would not be about it.

    Returns
    -------
    tuple of (query, language) or None
        A Google News query (quoted name plus finance words) and ``"pt"`` for B3
        listings or ``"en"`` otherwise.

    """
    b3 = _B3.match(symbol)
    if b3:
        return f'"{b3.group(1)}"', "pt"
    words = re.sub(r"[.,()/&-]", " ", name.replace("N.V.", "").replace("S.A.", ""))
    clean = " ".join(_NOISE.sub(" ", words).split())
    if len(clean) < 3:
        clean = symbol.split(".")[0].split("-")[0]
    if not clean:
        return None
    # A short name ("Arm", "SAP") is ambiguous: keep only finance news about it.
    context = "(price OR crypto)" if symbol.endswith("-USD") else "(stock OR shares OR earnings)"
    return f'"{clean}" {context}', "en"


def google_news_url(query: str, language: str, days: int = 14) -> str:
    """RSS search URL for ``query`` in the last ``days`` days."""
    edition = (
        {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
        if language == "pt"
        else {"hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    params = {"q": f"{query} when:{days}d", **edition}
    return f"https://news.google.com/rss/search?{urlencode(params)}"


def parse_google_news(body: bytes, limit: int = 5) -> list[Headline]:
    """Newest ``limit`` headlines of a Google News RSS response.

    Titles end with `` - Source`` in this feed; the suffix is removed because the source
    is kept separately. Items without a title, an http(s) link or a date are skipped.

    Raises
    ------
    ValueError
        If the body is not RSS.

    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise ValueError("not an RSS document") from error
    items: list[Headline] = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source = (item.findtext("source") or "").strip()
        date = item.findtext("pubDate") or ""
        if not title or urlparse(link).scheme not in ("http", "https") or not date:
            continue
        try:
            published = pd.Timestamp(parsedate_to_datetime(date)).tz_convert("UTC")
        except (TypeError, ValueError):
            continue
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].rstrip()
        items.append(Headline(title, source, link, published))
    items.sort(key=lambda h: h.published, reverse=True)
    return items[:limit]
