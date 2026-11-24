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
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(analysis.page.encode("utf-8"))  # LF endings on every OS
    print(f"wrote {OUT} ({len(analysis.page) / 1e6:.1f} MB)")
    for problem in analysis.problems:
        print(f"warning: {problem.name} came from the cache ({problem.error})")
    return 1 if analysis.problems else 0


if __name__ == "__main__":
    sys.exit(main())
