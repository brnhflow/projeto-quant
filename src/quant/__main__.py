"""Command line: ``python -m quant report`` downloads fresh data and writes the report."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from collections.abc import Sequence
from pathlib import Path

from quant.app import AppConfig, make_server
from quant.data import DataConfigError
from quant.holdings import load_holdings
from quant.pipeline import analyse_portfolio


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

    app = commands.add_parser("app", help="open the portfolio editor in the browser")
    app.add_argument("--port", type=int, default=8750, help="local port (default: 8750)")
    app.add_argument(
        "--holdings",
        type=Path,
        default=Path("data/private/holdings.csv"),
        help="where the portfolio is saved (default: data/private/holdings.csv)",
    )
    app.add_argument(
        "--cache", type=Path, default=Path("data/cache"), help="folder for downloaded data"
    )
    app.add_argument("--no-browser", action="store_true", help="do not open the browser")
    return parser


def run_app(port: int, holdings: Path, cache: Path, open_browser: bool) -> int:
    """Serve the editor on 127.0.0.1 until Ctrl+C."""
    config = AppConfig(
        holdings_path=holdings, cache_dir=cache, report_path=Path("reports/carteira.html")
    )
    try:
        server = make_server(config, port)
    except OSError as error:
        print(f"error: port {port} unavailable ({error}); try --port 8751", file=sys.stderr)
        return 2
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Portfolio editor at {url}  (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the process exit code.

    0: report written and every series refreshed. 1: report written, but some series came
    from the cache after a failed download. 2: no report (bad input or no data at all).
    """
    args = _parser().parse_args(argv)
    if args.command == "app":
        return run_app(args.port, args.holdings, args.cache, not args.no_browser)
    try:
        holdings = load_holdings(args.holdings)
        market = analyse_portfolio(
            holdings, args.years, args.cache, title=args.title, offline=args.offline
        )
        page = market.page
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
