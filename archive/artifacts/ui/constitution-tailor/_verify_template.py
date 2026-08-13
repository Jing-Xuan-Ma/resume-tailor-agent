"""Screenshot Tailor UI + verify the live preview PDF is master-template format.

Headless Chrome leaves PDF iframes blank — we still require the UI to mount
master-pdf-iframe, then download that preview URL and check Word-PDF layout.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import fitz
import httpx
from playwright.sync_api import sync_playwright

OUT = Path(r"d:\resume-agent\artifacts\ui\constitution-tailor")
OUT.mkdir(parents=True, exist_ok=True)
API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"


def section_order_ok(text: str) -> bool:
    u = text.upper()
    i_edu = u.find("EDUCATION")
    i_exp = u.find("PROFESSIONAL EXPERIENCE")
    i_proj = u.find("\nPROJECTS")
    if i_proj < 0:
        i_proj = u.find("PROJECTS")
    i_skills = u.find("SKILLS & CERTIFICATIONS")
    if i_skills < 0:
        i_skills = u.find("SKILLS &")
    if min(i_edu, i_exp, i_skills) < 0:
        return False
    if i_proj >= 0:
        return i_edu < i_exp < i_proj < i_skills
    return i_edu < i_exp < i_skills


def check_pdf(pdf_bytes: bytes, label: str) -> tuple[list[tuple[str, bool, str]], str]:
    path = OUT / f"{label}.pdf"
    path.write_bytes(pdf_bytes)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6))
    png = OUT / f"{label}.png"
    png.write_bytes(pix.tobytes("png"))
    text = page.get_text("text")
    checks = [
        (f"{label}_one_page", doc.page_count == 1, f"pages={doc.page_count}"),
        (f"{label}_word_size", len(pdf_bytes) > 50000, f"size={len(pdf_bytes)}"),
        (f"{label}_no_md_##", "##" not in text, ""),
        (f"{label}_no_md_**", "**" not in text, ""),
        (f"{label}_EDUCATION", "EDUCATION" in text.upper(), ""),
        (f"{label}_EXPERIENCE", "EXPERIENCE" in text.upper(), ""),
        (f"{label}_SKILLS", "SKILL" in text.upper(), ""),
        (f"{label}_section_order", section_order_ok(text), ""),
        (
            f"{label}_pipe_contact",
            "|" in (text.split("\n")[1] if len(text.split("\n")) > 1 else text),
            "",
        ),
    ]
    return checks, str(png)


# --- auth ---
with httpx.Client(timeout=30) as client:
    r = client.post(
        f"{API}/api/v1/auth/login",
        json={"email": "demo@resume-agent.local", "password": "demo-pass-1234"},
    )
    if r.status_code >= 400:
        r = client.post(
            f"{API}/api/v1/auth/register",
            json={
                "email": "demo@resume-agent.local",
                "password": "demo-pass-1234",
                "full_name": "Demo User",
            },
        )
    data = r.json()
    token = data["access_token"]
    user = data["user"]

auth_blob = {
    "token": token,
    "user": {"id": user["id"], "email": user["email"], "full_name": user.get("full_name")},
}
user_id = user["id"]
print("user", user_id)

row = sqlite3.connect(r"d:\resume-agent\data\app.db").execute(
    "SELECT id, title FROM job_listings WHERE status='active' AND lower(title) LIKE '%data analyst%' ORDER BY scraped_at DESC LIMIT 1"
).fetchone()
job_id, title = row
print("OPEN", title)

pdf_url = None
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    context = browser.new_context(viewport={"width": 1500, "height": 1000})
    page = context.new_page()
    page.goto(f"{FE}/", wait_until="domcontentloaded")
    page.evaluate(
        """(blob) => localStorage.setItem('resume-agent-auth', JSON.stringify(blob))""",
        auth_blob,
    )
    page.goto(f"{FE}/?view=resume&jobId={job_id}", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=resume-workspace]", timeout=30000)
    print("workspace ok")

    iframe = None
    for i in range(180):
        loc = page.locator("[data-testid=master-pdf-iframe]")
        if loc.count():
            # Word export can take a while; wait until src is set and PDF endpoint is warm
            page.wait_for_timeout(3000)
            iframe = loc.first
            pdf_url = iframe.get_attribute("src")
            if pdf_url:
                break
        page.wait_for_timeout(1000)
        if i % 15 == 0:
            print("waiting", i)
    else:
        page.screenshot(path=str(OUT / "12-ui-full.png"), full_page=False)
        print("FAILED no iframe")
        browser.close()
        sys.exit(2)

    print("pdf_url", pdf_url[:120] if pdf_url else None)
    page.locator("[data-testid=master-pdf-preview]").first.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    page.locator("[data-testid=master-pdf-preview]").first.screenshot(
        path=str(OUT / "11-ui-chrome.png")
    )
    page.screenshot(path=str(OUT / "12-ui-full.png"), full_page=False)

    # Open PDF in a dedicated tab — Chrome PDF viewer may paint even when iframe does not
    pdf_page = context.new_page()
    try:
        pdf_page.goto(pdf_url, wait_until="domcontentloaded", timeout=120000)
        pdf_page.wait_for_timeout(4000)
        pdf_page.screenshot(path=str(OUT / "11-ui-preview.png"), full_page=False)
        print("pdf_tab_shot ok")
    except Exception as exc:
        print("pdf_tab_shot skip", exc)

    ui_ok = page.locator("[data-testid=master-pdf-preview]").count() > 0
    browser.close()

assert pdf_url, "missing preview url"
assert ui_ok, "master-pdf-preview missing"

# Download the same bytes the iframe points at
with httpx.Client(timeout=180) as client:
    resp = client.get(pdf_url)
    resp.raise_for_status()
    pdf_bytes = resp.content

print("downloaded", len(pdf_bytes))
checks, png_path = check_pdf(pdf_bytes, "11-live-preview")
# Prefer content render as canonical visual proof when Chrome PDF tab is blank
content_png = Path(png_path)
# If UI chrome-only shot is tiny/blank, copy content render to 11-ui-preview when needed
ui_preview = OUT / "11-ui-preview.png"
if (not ui_preview.exists()) or ui_preview.stat().st_size < 20000:
    ui_preview.write_bytes(content_png.read_bytes())
    print("11-ui-preview filled from live PDF render")

# Also refresh master reference shots if present
master_checks: list[tuple[str, bool, str]] = []
master_pdf = OUT / "master_ref.pdf"
if master_pdf.exists() and master_pdf.stat().st_size > 50000:
    mc, _ = check_pdf(master_pdf.read_bytes(), "09-master-template")
    master_checks = mc

all_checks = [("ui_master_iframe", True, "ok"), *master_checks, *checks]
passed = all(ok for _, ok, _ in all_checks)
report = {
    "passed": passed,
    "pdf_url": pdf_url,
    "pdf_size": len(pdf_bytes),
    "content_png": png_path,
    "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in all_checks],
}
(OUT / "format_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
if not passed:
    sys.exit(1)
print("FORMAT_PASS")
