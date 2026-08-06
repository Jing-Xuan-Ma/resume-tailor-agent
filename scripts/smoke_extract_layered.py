"""Smoke: layered extract.js against Jobright mock fixture (no Chrome extension)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "extensions" / "jobright-bridge" / "content" / "extract.js"
MOCK = ROOT / "frontend" / "public" / "fixtures" / "jobright-mock.html"
OUT = ROOT / "artifacts" / "ui" / "extract-layered"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    if not EXTRACT.is_file() or not MOCK.is_file():
        print("missing extract or mock")
        return 2

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(MOCK.as_uri())
        page.add_script_tag(path=str(EXTRACT))
        page.wait_for_function("() => typeof window.__RA_EXTRACT_READY__ === 'function'")
        job = page.evaluate(
            """async () => {
              const j = await window.__RA_EXTRACT_READY__();
              return j;
            }"""
        )
        browser.close()

    report = {
        "ok": bool(job and (job.get("raw_text") or "").strip()),
        "body_len": job.get("body_len") if job else 0,
        "extract_layer": job.get("extract_layer") if job else None,
        "title": job.get("title") if job else None,
        "company": job.get("company") if job else None,
        "diagnostics": job.get("diagnostics") if job else None,
        "raw_preview": ((job.get("raw_text") or "")[:240] if job else ""),
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    checks = [
        ("has_job", report["ok"]),
        ("body_len_ge_120", (report["body_len"] or 0) >= 120),
        ("layer_not_none", report["extract_layer"] not in (None, "none")),
        ("prefer_l1_or_l2", report["extract_layer"] in ("layer1_score", "layer2_containers")),
        ("company_northwind", "Northwind" in str(report.get("company") or "")),
        ("title_da", "Data Analyst" in str(report.get("title") or "")),
        ("diag_present", isinstance(report.get("diagnostics"), dict)),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'} {n}")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
