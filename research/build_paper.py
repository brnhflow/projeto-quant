"""Print docs/paper/paper.html to docs/paper/projeto-quant-notes.pdf.

Run: uv run --with playwright python research/build_paper.py
(Playwright drives an installed Chrome or Edge; it is not a dependency of the package.)
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "docs" / "paper" / "paper.html"
OUT = ROOT / "docs" / "paper" / "projeto-quant-notes.pdf"


def main() -> None:
    """Render the HTML with the browser's print engine."""
    with sync_playwright() as p:
        for channel in ("chrome", "msedge"):
            try:
                browser = p.chromium.launch(channel=channel)
                break
            except Exception:  # that browser is not installed: try the next one
                continue
        else:
            browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(SOURCE.as_uri())
        page.wait_for_load_state("networkidle")
        page.pdf(path=str(OUT), format="A4", print_background=True, prefer_css_page_size=True)
        browser.close()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
