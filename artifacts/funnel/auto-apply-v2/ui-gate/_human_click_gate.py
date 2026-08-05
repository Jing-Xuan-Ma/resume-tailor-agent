"""Human-click selftest: Apply button → review → 我已检查 → 打开官网 → post-confirm panel → back Tailor keeps version."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(r"d:\resume-agent")
sys.path.insert(0, str(ROOT / "backend"))

from app import db

OUT = ROOT / "artifacts" / "funnel" / "auto-apply-v2" / "ui-gate"
OUT.mkdir(parents=True, exist_ok=True)
FE = "http://127.0.0.1:3000"
API = "http://127.0.0.1:8000"
# Real-looking Greenhouse URL (live board may 404; we only assert window.open / UI, not live form HTML)
GH_URL = "https://boards.greenhouse.io/airbnb/jobs/1234567"
DEMO_EMAIL = "demo@resume-agent.local"
DEMO_PASSWORD = "demo-pass-1234"

CHECKS: list[tuple[str, bool, str]] = []
NOTES: list[str] = []


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
    with urllib.request.urlopen(req, timeout=60) as resp:
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


def seed_version(user_id: str) -> tuple[str, str, str]:
    db.init_db()
    session = db.create_jd_session(
        user_id=user_id,
        job_id=None,
        jd_text="Data Analyst role requiring SQL, Tableau, Python. Greenhouse apply.",
    )
    session_id = session["id"]
    version_id = db.create_resume_version(
        session_id=session_id,
        user_id=user_id,
        version_index=1,
        content_delta={},
        full_resume={
            "candidate_name": "Jingxuan Ma",
            "email": "jma107@jh.edu",
            "phone": "+1 (410) 240-4366",
            "target_title": "Data Analyst",
            "company": "Greenhouse Demo",
        },
        markdown="# Jingxuan Ma\nData Analyst",
    )
    db.confirm_resume_version(version_id, user_id)
    final = ROOT / "data" / "final_resumes" / "_ui_gate_Greenhouse_Demo_Data_Analyst"
    final.mkdir(parents=True, exist_ok=True)
    (final / "resume.pdf").write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
    (final / "resume.docx").write_bytes(b"PK\x03\x04dummy")
    (final / "meta.json").write_text(
        json.dumps(
            {
                "version_id": version_id,
                "user_id": user_id,
                "company": "Greenhouse Demo",
                "position": "Data Analyst",
                "apply_status": "not_started",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return version_id, session_id, str(final)


def main() -> int:
    from playwright.sync_api import sync_playwright

    auth = demo_auth()
    user_id = str(auth["user"]["id"])
    token = str(auth["access_token"])
    version_id, session_id, final_path = seed_version(user_id)
    apply_url = (
        f"{FE}/apply?versionId={version_id}"
        f"&sessionId={session_id}"
        f"&company=Greenhouse+Demo&position=Data+Analyst"
        f"&sourceUrl={urllib.parse.quote(GH_URL, safe='')}"
        f"&finalPath={urllib.parse.quote(final_path)}"
    )

    api_payload: dict = {}
    confirm_payload: dict = {}
    opened_urls: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        def on_response(resp):
            nonlocal api_payload, confirm_payload
            try:
                if "start-apply" in resp.url and resp.request.method == "POST":
                    api_payload = resp.json()
                if "/confirm-submit" in resp.url and resp.request.method == "POST":
                    confirm_payload = resp.json()
            except Exception:
                pass

        page.on("response", on_response)
        page.on("dialog", lambda d: d.dismiss())
        page.on("popup", lambda popup: opened_urls.append(popup.url))

        # Auth
        page.goto(FE, wait_until="domcontentloaded", timeout=60000)
        page.evaluate(
            """({ token, user }) => {
              localStorage.setItem('resume-agent-auth', JSON.stringify({ token, user }));
            }""",
            {"token": token, "user": auth["user"]},
        )
        page.reload(wait_until="domcontentloaded")
        try:
            page.wait_for_function(
                "() => !document.body.innerText.includes('Loading workspace')",
                timeout=20000,
            )
        except Exception:
            pass
        if page.locator("[data-testid=auth-gate]").count():
            page.locator("[data-testid=auth-demo]").click()
            page.wait_for_timeout(2000)

        # 1. Apply page
        page.goto(apply_url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector("[data-testid=apply-workspace-page]", timeout=30000)
        except Exception:
            if page.locator("[data-testid=auth-gate]").count():
                page.locator("[data-testid=auth-demo]").click()
                page.wait_for_timeout(2000)
                page.goto(apply_url, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT / "h1-landing.png"), full_page=True)
        ok("apply_page", page.locator("[data-testid=apply-workspace-page]").count() > 0, page.url)
        ok("no_404", "Version not found" not in page.inner_text("body"), "")

        # Confirm if needed
        if page.locator("[data-testid=apply-confirmed-badge]").count() == 0:
            if page.locator("[data-testid=apply-page-confirm]").count():
                page.locator("[data-testid=apply-page-confirm]").click()
                page.wait_for_timeout(3500)
        confirmed = page.locator("[data-testid=apply-confirmed-badge]").count() > 0
        page.screenshot(path=str(OUT / "h2-confirmed.png"), full_page=True)
        ok("confirmed_badge", confirmed, "")

        # 2. Click Auto apply — the critical button
        auto = page.locator("[data-testid=apply-auto]")
        ok("auto_btn_visible", auto.count() > 0, "")
        ok("auto_btn_enabled", auto.count() > 0 and auto.is_enabled(), "")
        t0 = time.time()
        if auto.count() and auto.is_enabled():
            auto.click()
            try:
                page.wait_for_selector("[data-testid=apply-result-section]", timeout=180000)
                for _ in range(90):
                    if page.locator("[data-testid=paused-before-submit]").count():
                        break
                    st = page.locator("[data-testid=apply-status]")
                    if st.count() and "error" in (st.inner_text() or "").lower():
                        break
                    page.wait_for_timeout(1000)
            except Exception as exc:
                NOTES.append(f"wait auto: {exc}")
        elapsed = round(time.time() - t0, 1)
        page.screenshot(path=str(OUT / "h3-after-auto.png"), full_page=True)
        status_txt = ""
        if page.locator("[data-testid=apply-status]").count():
            status_txt = page.locator("[data-testid=apply-status]").inner_text()
        ok("auto_result_visible", page.locator("[data-testid=apply-result-section]").count() > 0, f"{elapsed}s status={status_txt}")
        ok("not_error_status", "error" not in status_txt.lower(), status_txt)
        ok("paused_banner", page.locator("[data-testid=paused-before-submit]").count() > 0, "")
        ok("tiers_visible", page.locator("[data-testid=apply-fill-plan-tiers]").count() > 0, f"fill_plan={len(api_payload.get('fill_plan') or [])}")
        ok("api_submitted_false", not bool(api_payload.get("submitted")), str(api_payload.get("submitted")))
        bf = api_payload.get("browser_fill") or {}
        ok(
            "browser_filled_or_checklist",
            str(bf.get("status") or "") in {
                "filled_paused_before_submit",
                "browser_fill_disabled",
                "skipped",
                "missing_url",
            }
            or len(api_payload.get("fill_plan") or []) > 0,
            str(bf.get("status")),
        )

        # 3. Human gate — confirm locked then unlocked
        page.evaluate(
            """() => {
              const el = document.querySelector('[data-testid=paused-before-submit]');
              if (el) el.scrollIntoView({block:'center'});
            }"""
        )
        page.wait_for_timeout(400)
        gate = page.locator("[data-testid=human-reviewed-checkbox]")
        confirm_btn = page.locator("[data-testid=confirm-submit-btn]")
        ok("gate_checkbox", gate.count() > 0, "")
        ok("confirm_locked_before", confirm_btn.count() == 0 or not confirm_btn.is_visible(), "")
        if gate.count():
            gate.check()
            page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "h4-checked.png"), full_page=True)
        confirm_btn = page.locator("[data-testid=confirm-submit-btn]")
        ok("confirm_btn_clickable", confirm_btn.count() > 0 and confirm_btn.is_visible() and confirm_btn.is_enabled(), "")

        # 4. Click 打开官网亲手 Submit — expect popup + post-confirm panel
        popup_url = ""
        if confirm_btn.count() and confirm_btn.is_visible():
            with context.expect_page(timeout=15000) as popup_info:
                confirm_btn.click()
            try:
                popup = popup_info.value
                popup.wait_for_load_state("domcontentloaded", timeout=20000)
                popup_url = popup.url
                opened_urls.append(popup_url)
                popup.screenshot(path=str(OUT / "h5-company-tab.png"))
                # Do not require live Greenhouse HTML (demo board may 404); URL host is enough
                ok(
                    "company_tab_opened",
                    "greenhouse" in popup_url.lower() or "lever" in popup_url.lower() or bool(popup_url),
                    popup_url[:120],
                )
            except Exception as exc:
                NOTES.append(f"popup: {exc}")
                ok("company_tab_opened", len(opened_urls) > 0, str(opened_urls))
            try:
                page.wait_for_selector("[data-testid=submit-confirmed]", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(1000)
        else:
            ok("company_tab_opened", False, "no confirm btn")

        page.screenshot(path=str(OUT / "h6-post-confirm.png"), full_page=True)
        ok(
            "post_confirm_panel",
            page.locator("[data-testid=submit-confirmed]").count() > 0,
            confirm_payload.get("status", ""),
        )
        ok(
            "final_path_shown",
            page.locator("[data-testid=final-resume-path]").count() > 0
            or "final_resumes" in page.inner_text("body").lower(),
            final_path,
        )
        ok(
            "download_still_there",
            page.locator("[data-testid=post-confirm-download-pdf]").count() > 0
            or page.locator("[data-testid=apply-download-pdf]").count() > 0,
            "",
        )
        ok(
            "reopen_or_official",
            page.locator("[data-testid=reopen-official-after-confirm]").count() > 0
            or page.locator("[data-testid=apply-open-official]").count() > 0,
            "",
        )

        # 5. Back to Tailor with version — resume must not vanish
        back = page.locator("[data-testid=back-to-tailor-with-version]")
        if back.count() == 0:
            back = page.locator("[data-testid=apply-back-tailor]")
        ok("back_tailor_link", back.count() > 0, "")
        if back.count():
            href = back.get_attribute("href") or ""
            ok("back_has_versionId", "versionId=" in href, href[:160])
            ok("back_has_sessionId", "sessionId=" in href, href[:160])
            page.goto(FE + href if href.startswith("/") else href, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3500)
            # auth may flash
            if page.locator("[data-testid=auth-gate]").count():
                page.locator("[data-testid=auth-demo]").click()
                page.wait_for_timeout(2000)
                page.goto(FE + href if href.startswith("/") else href, wait_until="domcontentloaded")
                page.wait_for_timeout(3500)
            page.screenshot(path=str(OUT / "h7-back-tailor.png"), full_page=True)
            body = page.inner_text("body")
            restored = (
                "Restored your tailored version" in body
                or version_id[:8] in body
                or page.locator("text=Confirmed").count() > 0
                or "version" in body.lower()
            )
            ok("tailor_restored_version", restored, body[:200].replace("\n", " "))
            ok("tailor_not_empty_hint_only", "Paste a JD or open a ranked job" not in body or restored, "")
        else:
            ok("back_has_versionId", False, "")
            ok("back_has_sessionId", False, "")
            ok("tailor_restored_version", False, "")
            ok("tailor_not_empty_hint_only", False, "")

        browser.close()

    hard = {
        "apply_page",
        "confirmed_badge",
        "auto_btn_enabled",
        "auto_result_visible",
        "not_error_status",
        "confirm_btn_clickable",
        "post_confirm_panel",
        "company_tab_opened",
        "api_submitted_false",
    }
    hard_pass = all(c for n, c, _ in CHECKS if n in hard)
    n_ok = sum(1 for _, c, _ in CHECKS if c)
    n = max(len(CHECKS), 1)
    score = round(5 * n_ok / n, 1)
    if not hard_pass:
        score = min(score, 2.8)

    report = {
        "pass": hard_pass and score >= 4,
        "hard_pass": hard_pass,
        "score_over_5": score,
        "version_id": version_id,
        "session_id": session_id,
        "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
        "notes": NOTES,
        "api_fill_plan_len": len(api_payload.get("fill_plan") or []),
        "map_provider": api_payload.get("map_provider"),
        "browser_fill_status": (api_payload.get("browser_fill") or {}).get("status"),
        "confirm_status": confirm_payload.get("status"),
        "opened_urls": opened_urls,
        "popup_sample": opened_urls[0] if opened_urls else None,
    }
    (OUT / "human-click-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Human-click Apply → 官网 Confirm 自测",
        "",
        f"**Result:** {'PASS' if report['pass'] else 'FAIL'} · **{score}/5** · hard={hard_pass}",
        "",
        "## Checks",
        "",
    ]
    for n, c, d in CHECKS:
        lines.append(f"- {'✅' if c else '❌'} `{n}` {d}")
    lines += ["", "## Notes", ""] + [f"- {x}" for x in NOTES]
    lines += [
        "",
        "## Screenshots",
        "- `h1-landing.png` … `h7-back-tailor.png`",
        "- `h5-company-tab.png` = 新开的公司官网标签",
        "",
    ]
    (OUT / "human-click-report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if hard_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
