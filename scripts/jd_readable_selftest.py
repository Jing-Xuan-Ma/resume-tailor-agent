"""Screenshot JD panel redesign (JobRight-style scannable layout)."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "ui" / "jd-readable"
OUT.mkdir(parents=True, exist_ok=True)
FE = "http://localhost:3000"
JOB_ID = "c957ed55-7632-4846-8514-c34362a361ee"

results: dict = {"checks": [], "ok": True}


def check(name: str, cond: bool, detail: str = "") -> None:
    results["checks"].append({"name": name, "ok": bool(cond), "detail": detail})
    if not cond:
        results["ok"] = False
        print(f"FAIL {name}: {detail}")
    else:
        print(f"PASS {name}")


def main() -> int:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=True, channel="msedge")
        page = browser.new_page(viewport={"width": 1440, "height": 1100})

        # Auth gate
        page.goto(FE, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(800)
        if page.locator("[data-testid=auth-demo]").count():
            page.locator("[data-testid=auth-demo]").click()
            page.wait_for_timeout(1500)
        elif page.get_by_role("button", name=re.compile(r"demo", re.I)).count():
            page.get_by_role("button", name=re.compile(r"demo", re.I)).first.click()
            page.wait_for_timeout(1500)

        url = f"{FE}/?view=resume&jobId={JOB_ID}&step=jd"
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        try:
            page.wait_for_selector("[data-testid=jd-panel]", timeout=90000)
        except Exception as exc:
            page.screenshot(path=str(OUT / "00-fail.png"), full_page=True)
            check("jd_panel_loaded", False, str(exc))
            (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            browser.close()
            return 1

        # Wait for content parse / job handoff
        for _ in range(40):
            if page.locator("[data-testid=jd-title]").count() and page.locator(
                "[data-testid=jd-section-responsibilities], [data-testid=jd-skill-tags], [data-testid=jd-meta-row]"
            ).count():
                break
            page.wait_for_timeout(500)

        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "01-jd-top.png"), full_page=False)
        page.screenshot(path=str(OUT / "01-jd-full.png"), full_page=True)

        title = page.locator("[data-testid=jd-title]").inner_text() if page.locator("[data-testid=jd-title]").count() else ""
        check("has_title", "Analytics" in title or "Admin" in title or len(title) > 3, title)

        check("meta_row", page.locator("[data-testid=jd-meta-row]").count() > 0)
        pay = page.locator("[data-testid=jd-meta-pay]")
        if pay.count():
            pay_t = pay.inner_text()
            check("pay_chip", "$" in pay_t or "26" in pay_t, pay_t)
        else:
            check("pay_chip", False, "missing pay chip")

        check("responsibilities_section", page.locator("[data-testid=jd-responsibilities]").count() > 0)
        check("qualification_section", page.locator("[data-testid=jd-section-qualification]").count() > 0)
        skills = page.locator("[data-testid=jd-skill-tag]")
        check("skill_tags", skills.count() >= 2, f"count={skills.count()}")
        if skills.count():
            tags = [skills.nth(i).inner_text().strip() for i in range(min(skills.count(), 10))]
            check("skill_has_excel_or_sql", any(t for t in tags if "Excel" in t or "SQL" in t or "Python" in t or "Tableau" in t), str(tags))

        check("benefits_section", page.locator("[data-testid=jd-benefits]").count() > 0)
        check("no_raw_markdown_stars", page.locator("[data-testid=jd-panel]").inner_text().count("**") == 0
              if False else "**" not in page.locator("[data-testid=jd-panel]").inner_text())

        # Scroll to qualification / benefits for second shot
        if page.locator("[data-testid=jd-section-qualification]").count():
            page.locator("[data-testid=jd-section-qualification]").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            page.screenshot(path=str(OUT / "02-qualification.png"), full_page=False)

        if page.locator("[data-testid=jd-benefits]").count():
            page.locator("[data-testid=jd-benefits]").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            page.screenshot(path=str(OUT / "03-benefits.png"), full_page=False)

        # Raw markdown dump should not dominate first viewport text
        body = page.locator("[data-testid=jd-panel]").inner_text()
        check("no_duplicate_url_wall", body.lower().count("https://apply-v3.jobsync") <= 1, str(body.lower().count("https://apply-v3.jobsync")))
        check("no_sms_apply_noise", "text messaging" not in body.lower() and "75000" not in body)

        browser.close()

    (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    md = ["# JD readable redesign selftest", "", f"- ok: {results['ok']}", ""]
    for c in results["checks"]:
        md.append(f"- {'PASS' if c['ok'] else 'FAIL'} `{c['name']}` {c.get('detail','')}")
    (OUT / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("ok" if results["ok"] else "FAILED")
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
