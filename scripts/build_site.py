"""Build the public demo: the full report for the example portfolio, with live data.

Run: uv run python scripts/build_site.py  ->  docs/index.html (served by GitHub Pages)

The example holdings and trades are made up (data/holdings.example.csv and
data/transactions.example.csv); prices, exchange rates,
dividends and headlines are downloaded at build time, so the page is a dated snapshot.
"""

from __future__ import annotations

import sys
from pathlib import Path

from quant.holdings import load_holdings
from quant.ledger import load_transactions
from quant.pipeline import analyse_portfolio

ROOT = Path(__file__).parents[1]
OUT = ROOT / "docs" / "index.html"
SITE = "https://brnhflow.github.io/projeto-quant/"
DESCRIPTION = (
    "Portfolio risk lab by Bernardo Bordignon: tearsheet, VaR models backtested, Brinson "
    "attribution and rule backtests, with a C++20 core. Every number comes with its test."
)
# Link previews (LinkedIn, Slack, X) read these; the local app's pages do not need them.
PREVIEW = f"""
<meta name="description" content="{DESCRIPTION}">
<meta name="author" content="Bernardo Bordignon">
<meta property="og:type" content="website">
<meta property="og:title" content="projeto-quant: a portfolio risk lab that checks its own numbers">
<meta property="og:description" content="{DESCRIPTION}">
<meta property="og:url" content="{SITE}">
<meta property="og:image" content="{SITE}images/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="{SITE}">"""


def with_preview(page: str) -> str:
    """Add the link-preview tags after the viewport tag."""
    anchor = '<meta name="viewport" content="width=device-width, initial-scale=1">'
    if anchor not in page:
        raise ValueError("viewport tag not found in the report template")
    return page.replace(anchor, anchor + PREVIEW, 1)


def main() -> int:
    """Download, analyse and write the demo page; non-zero if a series came from cache."""
    holdings = load_holdings(ROOT / "data" / "holdings.example.csv")
    analysis = analyse_portfolio(
        holdings,
        3,
        ROOT / "data" / "cache",
        title="",
        demo_url="https://github.com/brnhflow/projeto-quant",
        transactions=load_transactions(ROOT / "data" / "transactions.example.csv"),
        rates_wait=300,  # a fresh machine has no cached rates: wait for the official files
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    page = with_preview(analysis.page)
    OUT.write_bytes(page.encode("utf-8"))  # LF endings on every OS
    print(f"wrote {OUT} ({len(page) / 1e6:.1f} MB)")
    for problem in analysis.problems:
        print(f"warning: {problem.name} came from the cache ({problem.error})")
    return 1 if analysis.problems else 0


if __name__ == "__main__":
    sys.exit(main())
