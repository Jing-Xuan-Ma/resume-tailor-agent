"""Thin CLI / import entry for standalone Playwright apply flow."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Allow `python entrypoints/standalone_app/main.py` from repo root
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


async def _amain(args: argparse.Namespace) -> int:
    from playwright.async_api import async_playwright

    from entrypoints.standalone_app.playwright_driver import run_apply_flow

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8")) if args.profile else {}
    job_info = {"resolved_url": args.url, "id": args.job_id or "local"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headed)
        page = await browser.new_page()
        result = await run_apply_flow(
            page,
            job_info,
            profile,
            in_process=args.in_process,
            engine_url=args.engine_url,
        )
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        await browser.close()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Form-Fill Playwright driver")
    parser.add_argument("--url", required=True, help="Apply form URL")
    parser.add_argument("--profile", help="JSON profile path")
    parser.add_argument("--job-id", default="")
    parser.add_argument("--engine-url", default="http://127.0.0.1:8000/engine/step")
    parser.add_argument("--in-process", action="store_true", default=True)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
