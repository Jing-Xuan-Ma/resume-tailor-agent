"""Print RG HTML previews to PDF via Playwright Chromium/Chrome."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main(round_id: str = "round-3") -> int:
    round_dir = ROOT / "artifacts" / "rg" / round_id
    gallery = round_dir / "_pdf_preview"
    gallery.mkdir(exist_ok=True)

    html_files = sorted(round_dir.glob("*/preview.html"))
    if not html_files:
        print("NO_HTML")
        return 1

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=True, channel="msedge")
        page = browser.new_page()
        for html in html_files:
            pdf = html.with_name("resume.pdf")
            page.goto(html.as_uri(), wait_until="load")
            page.pdf(
                path=str(pdf),
                format="Letter",
                print_background=True,
                margin={"top": "0.4in", "bottom": "0.4in", "left": "0.5in", "right": "0.5in"},
            )
            dest = gallery / f"{html.parent.name}.pdf"
            dest.write_bytes(pdf.read_bytes())
            print(f"OK {html.parent.name}")
        browser.close()

    print(f"gallery={gallery}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "round-3"))
