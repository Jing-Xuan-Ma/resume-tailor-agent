"""Human-click gate: Manual/Auto apply must open Indeed (not dead Workday /FRS)."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(r"d:\resume-agent")
sys.path.insert(0, str(ROOT / "backend"))

from app import db  # noqa: E402

OUT = ROOT / "artifacts" / "ui" / "apply-url-fix"
OUT.mkdir(parents=True, exist_ok=True)
FE = "http://127.0.0.1:3000"
API = "http://127.0.0.1:8000"
JOB_ID = "7c2247db-96f2-4402-8983-b7f052aa139a"
EXPECTED_HOST = "indeed.com"
FORBIDDEN = ("myworkdayjobs.com", "rb.wd5", "\\")
DEMO_EMAIL = "demo@resume-agent.local"
DEMO_PASSWORD = "demo-pass-1234"

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


def http_json(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        API + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode())


def demo_auth() -> dict:
    try:
        return http_json("POST", "/api/v1/auth/login", {"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    except urllib.error.HTTPError:
        return http_json(
            "POST",
            "/api/v1/auth/register",
            {"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "full_name": "Demo User"},
        )


def seed_confirmed_version(user_id: str) -> str:
    db.init_db()
    session = db.create_jd_session(
        user_id=user_id,
        job_id=JOB_ID,
        jd_text="Regulatory Data Analyst at Federal Reserve Bank of New York. SQL Python.",
    )
    version_id = db.create_resume_version(
        session_id=session["id"],
        user_id=user_id,
        version_index=1,
        content_delta={},
        full_resume={
            "candidate_name": "Jingxuan Ma",
            "email": "jma107@jh.edu",
            "phone": "+1 (410) 240-4366",
            "target_title": "Regulatory Data Analyst",
            "company": "Federal Reserve Bank of New York",
        },
        markdown="# Jingxuan Ma\nRegulatory Data Analyst",
    )
    db.confirm_resume_version(version_id, user_id)
    return version_id


def url_ok(u: str) -> bool:
    low = (u or "").lower()
    if not u.startswith("http"):
        return False
    if any(f in low or f in u for f in FORBIDDEN):
        return False
    return EXPECTED_HOST in low


def main() -> int:
    auth = demo_auth()
    user_id = str(auth["user"]["id"])
    token = str(auth.get("access_token") or auth.get("token") or "")
    version_id = seed_confirmed_version(user_id)

    # API-level check first
    for mode in ("manual", "auto"):
        payload = http_json(
            "POST",
            f"/api/v1/resume-workspace/resume-version/{version_id}/start-apply",
            {
                "user_id": user_id,
                "mode": mode,
                "job_id": JOB_ID,
                "company": "Federal Reserve Bank of New York",
                "position": "Regulatory Data Analyst",
            },
        )
        src = str(payload.get("source_url") or "")
        ok(f"api_{mode}_indeed", url_ok(src), src)

    from playwright.sync_api import sync_playwright

    opened: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context()
        page = context.new_page()

        def on_popup(popup) -> None:
            try:
                popup.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            opened.append(popup.url)

        page.on("popup", on_popup)

        # Login via demo button or inject stored auth
        page.goto(FE, wait_until="domcontentloaded", timeout=60000)
        if page.locator("[data-testid=auth-demo]").count():
            page.locator("[data-testid=auth-demo]").click()
            page.wait_for_timeout(1200)
        else:
            page.evaluate(
                """([token, user]) => {
                  localStorage.setItem('resume-agent-auth', JSON.stringify({ token, user }));
                }""",
                [token or auth.get("access_token"), auth["user"]],
            )
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(800)

        apply_url = (
            f"{FE}/apply?versionId={version_id}&jobId={JOB_ID}"
            f"&company=Federal%20Reserve%20Bank%20of%20New%20York"
            f"&position=Regulatory%20Data%20Analyst"
        )
        page.goto(apply_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "01-apply-workspace.png"), full_page=True)

        # If still on auth gate
        if page.locator("[data-testid=auth-demo]").count():
            page.locator("[data-testid=auth-demo]").click()
            page.wait_for_timeout(1000)
            page.goto(apply_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)

        manual = page.locator("[data-testid=apply-manual]")
        manual.first.wait_for(state="visible", timeout=15000)
        # Unlock if confirm gate still showing
        confirm_btn = page.locator("[data-testid=apply-page-confirm], [data-testid=apply-inline-confirm]")
        if confirm_btn.count() and confirm_btn.first.is_enabled():
            confirm_btn.first.click()
            page.wait_for_timeout(1200)
        page.locator("[data-testid=apply-manual]").first.wait_for(state="visible", timeout=10000)
        ok("manual_btn_visible", page.locator("[data-testid=apply-manual]").count() > 0)
        opened.clear()
        with page.expect_popup(timeout=15000) as pop_info:
            manual.first.click()
        popup = pop_info.value
        try:
            popup.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass
        manual_url = popup.url
        opened.append(manual_url)
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT / "02-after-manual.png"), full_page=True)
        ok("manual_opens_indeed", url_ok(manual_url), manual_url)
        ok("manual_not_workday", "myworkday" not in manual_url.lower() and "\\" not in manual_url, manual_url)

        # Check live page is not Chrome connection-error
        body_text = ""
        try:
            body_text = popup.inner_text("body")[:500]
        except Exception as e:
            body_text = str(e)
        ok(
            "manual_page_not_connection_closed",
            "ERR_CONNECTION_CLOSED" not in body_text and "无法访问此网站" not in body_text,
            body_text[:120],
        )
        try:
            popup.close()
        except Exception:
            pass

        # Auto apply
        auto = page.locator("[data-testid=apply-auto]")
        ok("auto_btn_visible", auto.count() > 0 and auto.first.is_enabled())
        with page.expect_popup(timeout=20000) as pop_info2:
            auto.first.click()
        popup2 = pop_info2.value
        try:
            popup2.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass
        auto_url = popup2.url
        page.wait_for_timeout(2500)
        page.screenshot(path=str(OUT / "03-after-auto.png"), full_page=True)
        ok("auto_opens_indeed", url_ok(auto_url), auto_url)
        ok("auto_not_workday", "myworkday" not in auto_url.lower() and "\\" not in auto_url, auto_url)
        body2 = ""
        try:
            body2 = popup2.inner_text("body")[:500]
        except Exception as e:
            body2 = str(e)
        ok(
            "auto_page_not_connection_closed",
            "ERR_CONNECTION_CLOSED" not in body2 and "无法访问此网站" not in body2,
            body2[:120],
        )

        # Status panel link (apply workspace uses apply-open-official)
        link = page.locator("[data-testid=apply-open-official], [data-testid=apply-source-url]")
        if link.count():
            href = link.first.get_attribute("href") or ""
            ok("panel_link_indeed", url_ok(href), href)
        else:
            ok("panel_link_indeed", False, "missing apply-open-official / apply-source-url")

        browser.close()

    report = {
        "job_id": JOB_ID,
        "version_id": version_id,
        "checks": [{"name": n, "pass": p, "detail": d} for n, p, d in CHECKS],
        "passed": all(p for _, p, _ in CHECKS),
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Apply URL fix — human click gate", ""]
    for n, p, d in CHECKS:
        lines.append(f"- {'PASS' if p else 'FAIL'} `{n}` — {d}")
    lines.append("")
    lines.append(f"**Overall:** {'PASS' if report['passed'] else 'FAIL'}")
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("OVERALL", "PASS" if report["passed"] else "FAIL")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
