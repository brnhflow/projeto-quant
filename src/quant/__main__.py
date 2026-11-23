"""Command line: ``python -m quant report`` downloads fresh data and writes the report."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from quant.data import DataConfigError, update_market_data
from quant.holdings import load_holdings
from quant.report import build_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m quant", description="Portfolio analysis.")
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="update market data and write the HTML report")
    report.add_argument(
        "--holdings",
        type=Path,
        default=Path("data/private/holdings.csv"),
        help="holdings CSV (default: data/private/holdings.csv)",
    )
    report.add_argument(
        "--out",
        type=Path,
        default=Path("reports/carteira.html"),
        help="HTML file to write (default: reports/carteira.html)",
    )
    report.add_argument(
        "--years", type=float, default=2.0, help="years of history to use (default: 2)"
    )
    report.add_argument(
        "--cache", type=Path, default=Path("data/cache"), help="folder for downloaded data"
    )
    report.add_argument("--title", default="Minha carteira", help="report title")
    report.add_argument("--offline", action="store_true", help="use only cached data, no network")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the process exit code.

    0: report written and every series refreshed. 1: report written, but some series came
    from the cache after a failed download. 2: no report (bad input or no data at all).
    """
    args = _parser().parse_args(argv)
    try:
        holdings = load_holdings(args.holdings)
        now = pd.Timestamp.now(tz="UTC")
        start = (now - pd.Timedelta(days=round(args.years * 365.25))).tz_convert(None).normalize()
        market = update_market_data(holdings, start, args.cache, now=now, offline=args.offline)
        last = pd.Timestamp(market.prices.index.max())
        calendar = pd.bdate_range(start, last)
        page = build_report(
            holdings, market.prices, market.fx, calendar, title=args.title, status=market.status
        )
    except (FileNotFoundError, ValueError, ConnectionError, DataConfigError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")
    for s in market.status:
        state = (
            f"FAILED, using cache ({s.error})"
            if s.error
            else (
                "cache (offline)" if s.from_cache else ("live session" if s.in_progress else "ok")
            )
        )
        print(f"{s.name:<10} {s.source:<7} {s.symbol:<12} last {s.last_date}  {state}")
    print(f"wrote {args.out}")
    return 1 if market.problems else 0


if __name__ == "__main__":
    sys.exit(main())
