"""Self-contained HTML report of a portfolio: one file, no network access needed to open it."""

from __future__ import annotations

import html
import json
from importlib import resources
from typing import Any

import pandas as pd

from quant.data.market import Series, SeriesStatus
from quant.data.news import Headline
from quant.data.rates import RatesData
from quant.data.sources import Quote
from quant.report.data import PERIODS, Period, build_report_data, period_start

__all__ = [
    "PERIODS",
    "Period",
    "build_report",
    "build_report_data",
    "period_start",
    "render_html",
    "report_script",
]


def report_script() -> str:
    """Assemble the page script: shared libraries, then the page parts in ``js/ORDER``.

    The libraries (tested with Node) define global functions; the page parts run inside
    one function, so the names they share stay out of the global scope.
    """
    assets = resources.files("quant.report")
    static = resources.files("quant.app") / "static"
    libraries = [
        static / "lang.js",
        static / "quantity.js",
        static / "assets.js",
        assets / "maths.js",
    ]
    parts = (assets / "js" / "ORDER").read_text(encoding="utf-8").split()
    page = "\n".join((assets / "js" / name).read_text(encoding="utf-8") for name in parts)
    js = "\n".join(f.read_text(encoding="utf-8") for f in libraries)
    js += "\n(() => {\n" + page + "\n})();\n"
    return js


def render_html(data: dict[str, Any]) -> str:
    """Turn the data from :func:`build_report_data` into a standalone HTML page.

    Parameters
    ----------
    data : dict
        Output of :func:`quant.report.data.build_report_data`.

    Returns
    -------
    str
        Complete HTML document with styles, script and data inlined.

    """
    assets = resources.files("quant.report")
    template = (assets / "template.html").read_text(encoding="utf-8")
    css = (assets / "report.css").read_text(encoding="utf-8")
    js = report_script()
    # "</" inside the JSON would close the <script> tag early.
    payload = (
        json.dumps(data, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\u0021--")
    )
    return (
        template.replace("{{TITLE}}", html.escape(str(data["title"])))
        .replace("{{CSS}}", css)
        .replace("{{JS}}", js)
        .replace("{{DATA}}", payload)
    )


def build_report(
    holdings: pd.DataFrame,
    local_prices: pd.DataFrame,
    fx_rates: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    *,
    title: str,
    base: str = "EUR",
    synthetic: bool = False,
    status: list[SeriesStatus] | None = None,
    edit_url: str | None = None,
    proxy_prices: pd.DataFrame | None = None,
    details: dict[str, Quote] | None = None,
    news: dict[str, list[Headline] | None] | None = None,
    demo_url: str | None = None,
    transactions: pd.DataFrame | None = None,
    market: dict[str, Series] | None = None,
    sentiment: dict[str, Series] | None = None,
    bonds: RatesData | None = None,
) -> str:
    """Compute the report data and render it; see :func:`build_report_data` for arguments."""
    data = build_report_data(
        holdings,
        local_prices,
        fx_rates,
        calendar,
        title=title,
        base=base,
        synthetic=synthetic,
        status=status,
        edit_url=edit_url,
        proxy_prices=proxy_prices,
        details=details,
        news=news,
        demo_url=demo_url,
        transactions=transactions,
        market=market,
        sentiment=sentiment,
        bonds=bonds,
    )
    return render_html(data)
