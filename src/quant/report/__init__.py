"""Self-contained HTML report of a portfolio: one file, no network access needed to open it."""

from __future__ import annotations

import html
import json
from importlib import resources
from typing import Any

import pandas as pd

from quant.data.market import SeriesStatus
from quant.data.news import Headline
from quant.data.sources import Quote
from quant.report.data import PERIODS, Period, build_report_data, period_start

__all__ = ["PERIODS", "Period", "build_report", "build_report_data", "period_start", "render_html"]


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
    # Pure functions tested with Node, then the page script that calls them.
    quantity = resources.files("quant.app") / "static" / "quantity.js"
    js = "\n".join(
        f.read_text(encoding="utf-8")
        for f in (quantity, assets / "rebalance.js", assets / "report.js")
    )
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
    )
    return render_html(data)
