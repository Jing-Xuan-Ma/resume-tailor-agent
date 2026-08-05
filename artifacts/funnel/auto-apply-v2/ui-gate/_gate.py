"""Seed a confirmed resume version for the demo auth user, then run UI click gate."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(r"d:\resume-agent")
sys.path.insert(0, str(ROOT / "backend"))

from app import db

OUT = ROOT / "artifacts" / "funnel" / "auto-apply-v2" / "ui-gate"
OUT.mkdir(parents=True, exist_ok=True)
FE = "http://127.0.0.1:3000"
API = "http://127.0.0.1:8000"
GH_URL = "https://boards.greenhouse.io/demo/jobs/1"
DEMO_EMAIL = "demo@resume-agent.local"
DEMO_PASSWORD = "demo-pass-1234"

CHECKS: list[tuple[str, bool, str]] = []
NOTES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


def http_json(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
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


def seed_version(user_id: str) -> tuple[str, str]:
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
    # Seed a fake final resume folder so resume_path resolves
    final = ROOT / "data" / "final_resumes" / "_ui_gate_Greenhouse_Demo_Data_Analyst"
    final.mkdir(parents=True, exist_ok=True)
    resume_pdf = final / "resume.pdf"
    if not resume_pdf.exists():
        resume_pdf.write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
    meta = {
        "version_id": version_id,
        "user_id": user_id,
        "company": "Greenhouse Demo",
        "position": "Data Analyst",
    }
    (final / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return version_id, str(final)


def main() -> int:
    from playwright.sync_api import sync_playwright

    auth = demo_auth()
    user_id = str(auth["user"]["id"])
    token = str(auth["access_token"])
    version_id, final_path = seed_version(user_id)
    apply_url = (
        f"{FE}/apply?versionId={version_id}"
        f"&company=Greenhouse+Demo&position=Data+Analyst"
        f"&sourceUrl={GH_URL}"
        f"&finalPath={urllib.parse.quote(final_path)}"
    )

    api_payload: dict = {}
    confirm_payload: dict = {}
    has_tiers = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        confirm_payload.clear()

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

        # Seed auth storage before first navigation
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
                """() => !document.body.innerText.includes('Loading workspace')""",
                timeout=20000,
            )
        except Exception:
            pass
        page.wait_for_timeout(800)
        if page.locator("[data-testid=auth-gate]").count():
            page.locator("[data-testid=auth-demo]").click()
            page.wait_for_timeout(2500)

        page.goto(apply_url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector("[data-testid=apply-workspace-page]", timeout=30000)
        except Exception:
            if page.locator("[data-testid=auth-gate]").count():
                page.locator("[data-testid=auth-demo]").click()
                page.wait_for_timeout(2000)
                page.goto(apply_url, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "01-landing.png"), full_page=True)
        ok("apply_page", page.locator("[data-testid=apply-workspace-page]").count() > 0, page.url)
        ok("no_404", "Version not found" not in page.inner_text("body"), "")

        # Confirm if needed (already confirmed in DB; UI may still call confirm)
        if page.locator("[data-testid=apply-confirmed-badge]").count() == 0:
            if page.locator("[data-testid=apply-page-confirm]").count():
                page.locator("[data-testid=apply-page-confirm]").click()
                page.wait_for_timeout(4000)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
        confirmed = page.locator("[data-testid=apply-confirmed-badge]").count() > 0
        if not confirmed and page.locator("[data-testid=apply-page-confirm]").count():
            page.locator("[data-testid=apply-page-confirm]").click()
            page.wait_for_timeout(4000)
            confirmed = page.locator("[data-testid=apply-confirmed-badge]").count() > 0
        page.screenshot(path=str(OUT / "02-confirmed.png"), full_page=True)
        ok("confirmed", confirmed, "")

        auto = page.locator("[data-testid=apply-auto]")
        ok("auto_enabled", auto.count() > 0 and auto.is_enabled(), "")
        t0 = time.time()
        if auto.count() and auto.is_enabled():
            auto.click()
            try:
                page.wait_for_selector("[data-testid=apply-result-section]", timeout=180000)
                # Prefer success path markers; give browser fill time
                page.wait_for_timeout(500)
                for _ in range(60):
                    if page.locator("[data-testid=paused-before-submit]").count():
                        break
                    if page.locator("[data-testid=apply-status]").count() and "error" in (
                        page.locator("[data-testid=apply-status]").inner_text() or ""
                    ).lower():
                        break
                    page.wait_for_timeout(1000)
            except Exception as exc:
                NOTES.append(f"wait result: {exc}")
            page.wait_for_timeout(800)
        elapsed = round(time.time() - t0, 1)
        page.screenshot(path=str(OUT / "03-auto-result.png"), full_page=True)
        ok("result_section", page.locator("[data-testid=apply-result-section]").count() > 0, f"{elapsed}s")
        ok("paused_banner", page.locator("[data-testid=paused-before-submit]").count() > 0, "")

        has_tiers = page.locator("[data-testid=apply-fill-plan-tiers]").count() > 0
        ok("fill_plan_tiers_ui", has_tiers, f"api_fill_plan={len(api_payload.get('fill_plan') or [])}")
        ok("tier_auto", page.locator("[data-testid=fill-tier-auto]").count() > 0, "")
        ok("tier_review", page.locator("[data-testid=fill-tier-review]").count() > 0, "")
        ok("tier_empty", page.locator("[data-testid=fill-tier-empty]").count() > 0, "")
        if not has_tiers:
            NOTES.append("fill_plan tiers missing in UI.")

        page.evaluate(
            """() => {
              const el = document.querySelector('[data-testid=paused-before-submit]');
              if (el) el.scrollIntoView({block:'center'});
            }"""
        )
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / "04-tiers-and-gate.png"), full_page=True)

        gate = page.locator("[data-testid=human-reviewed-gate]")
        locked = page.locator("[data-testid=confirm-submit-locked]")
        confirm_btn = page.locator("[data-testid=confirm-submit-btn]")
        ok("human_gate_visible", gate.count() > 0 or locked.count() > 0, f"gate={gate.count()} locked={locked.count()} btn={confirm_btn.count()}")
        ok(
            "confirm_locked_before_check",
            confirm_btn.count() == 0 or not confirm_btn.is_visible(),
            f"btn_visible={confirm_btn.count() > 0 and confirm_btn.is_visible()}",
        )
        if gate.count():
            page.locator("[data-testid=human-reviewed-checkbox]").check()
            page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "05-after-reviewed-check.png"), full_page=True)
        ok(
            "confirm_unlocked_after_check",
            page.locator("[data-testid=confirm-submit-btn]").count() > 0
            and page.locator("[data-testid=confirm-submit-btn]").is_visible(),
            "",
        )

        if page.locator("[data-testid=apply-review-step-ats]").count():
            page.locator("[data-testid=apply-review-step-ats]").click()
            page.wait_for_timeout(250)
            page.locator("[data-testid=apply-review-step-resume]").click()
            page.wait_for_timeout(250)
            page.locator("[data-testid=apply-review-step-pause]").click()
            page.wait_for_timeout(250)
            page.screenshot(path=str(OUT / "06-review-steps.png"), full_page=True)
            ok("review_steps", True, "")
        else:
            ok("review_steps", False, "missing")

        if page.locator("[data-testid=confirm-submit-btn]").count():
            page.locator("[data-testid=confirm-submit-btn]").scroll_into_view_if_needed()
            page.locator("[data-testid=confirm-submit-btn]").click()
            try:
                page.wait_for_selector("[data-testid=submit-confirmed]", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "07-after-confirm-submit.png"), full_page=True)
        ok(
            "user_confirm_recorded",
            page.locator("[data-testid=submit-confirmed]").count() > 0
            or "submitted_by_user_confirm" in page.inner_text("body")
            or confirm_payload.get("status") == "submitted_by_user_confirm",
            f"confirm_api={confirm_payload.get('status')}",
        )

        submitted = bool(api_payload.get("submitted"))
        fill_plan = api_payload.get("fill_plan") or []
        ok("api_submitted_false", not submitted, str(submitted))
        ok("api_has_fill_plan", len(fill_plan) >= 1, str(len(fill_plan)))
        empty_left = [m for m in fill_plan if m.get("tier") == "empty" or m.get("action") == "leave_empty"]
        ok("api_unknown_left_empty", len(empty_left) >= 1 or not fill_plan, str(len(empty_left)))
        bf = api_payload.get("browser_fill") or {}
        ok("api_browser_not_submitted", not bool(bf.get("submitted")), str(bf.get("status")))

        (OUT / "api-start-apply.json").write_text(
            json.dumps(
                {
                    "version_id": version_id,
                    "final_path": final_path,
                    "payload": api_payload,
                },
                indent=2,
                ensure_ascii=False,
            )[:250000],
            encoding="utf-8",
        )
        browser.close()

    hard_names = {
        "apply_page",
        "no_404",
        "confirmed",
        "auto_enabled",
        "result_section",
        "paused_banner",
        "confirm_unlocked_after_check",
        "api_submitted_false",
        "user_confirm_recorded",
    }
    hard = [c for c in CHECKS if c[0] in hard_names]
    hard_pass = all(c for _, c, _ in hard) if hard else False
    all_pass = all(c for _, c, _ in CHECKS)
    n_ok = sum(1 for _, c, _ in CHECKS if c)
    n = max(len(CHECKS), 1)
    score = round(5 * n_ok / n, 1)
    if not hard_pass:
        score = min(score, 2.5)
    if not has_tiers:
        score = min(score, 3.5)
        NOTES.append("Tiers missing lowers UX score.")
    if score >= 4:
        NOTES.append("Human-review gate and auto pause look usable.")
    else:
        NOTES.append("Need UX/fill_plan fixes before ≥4/5.")

    report = {
        "pass": all_pass and hard_pass,
        "hard_pass": hard_pass,
        "score_over_5": score,
        "version_id": version_id,
        "user_id": user_id,
        "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
        "notes": NOTES,
        "api_fill_plan_len": len(api_payload.get("fill_plan") or []),
        "map_provider": api_payload.get("map_provider"),
        "browser_fill_status": (api_payload.get("browser_fill") or {}).get("status"),
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Auto Apply v2 — UI human-click gate",
        "",
        f"**Result:** {'PASS' if report['pass'] else 'FAIL'} · self-score **{score}/5**",
        "",
        "## Checks",
        "",
    ]
    for n, c, d in CHECKS:
        lines.append(f"- {'✅' if c else '❌'} `{n}` {d}")
    lines += ["", "## Notes", ""] + [f"- {n}" for n in NOTES] + [
        "",
        "## Screenshots",
        "",
        "- `01-landing.png` … `07-after-confirm-submit.png`",
        "",
    ]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if hard_pass else 1


if __name__ == "__main__":
    # create_jd_session signature check
    raise SystemExit(main())
