"""Human-click gate for Apply workspace (Iter 1–4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(r"d:\resume-agent")
sys.path.insert(0, str(ROOT / "backend"))

from app import db

OUT = ROOT / "artifacts" / "funnel" / "apply-page"
OUT.mkdir(parents=True, exist_ok=True)
FE = "http://127.0.0.1:3000"
CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


def main() -> int:
    db.init_db()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, user_id, is_confirmed FROM resume_versions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        ok("has_version", False, "no resume_versions")
        _write(False)
        return 1

    version_id = row["id"]
    user_id = row["user_id"]
    # Ensure confirmed for Manual/Auto path (local gate only)
    with db.connect() as conn:
        conn.execute(
            "UPDATE resume_versions SET is_confirmed = 1, confirmed_at = COALESCE(confirmed_at, datetime('now')) WHERE id = ?",
            (version_id,),
        )
        conn.commit()

    apply_url = f"{FE}/apply?versionId={version_id}&company=TestCo&position=Data+Analyst"
    tailor_url = f"{FE}/?view=resume&step=apply"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Auth if needed
        page.goto(FE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1200)
        if page.locator("[data-testid=auth-gate]").count():
            page.locator("[data-testid=auth-demo]").click()
            page.wait_for_timeout(1500)

        # Apply workspace page
        page.goto(apply_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT / "01-apply-workspace.png"), full_page=False)
        ok("apply_page_loaded", page.locator("[data-testid=apply-workspace-page]").count() > 0, page.url)
        ok(
            "confirm_gate_visible",
            page.locator("[data-testid=apply-confirm-gate]").count() > 0
            or page.locator("[data-testid=apply-confirmed-badge]").count() > 0,
            "",
        )
        # Refresh confirmation state
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        confirmed = page.locator("[data-testid=apply-confirmed-badge]").count() > 0
        if not confirmed and page.locator("[data-testid=apply-page-confirm]").count():
            page.locator("[data-testid=apply-page-confirm]").click()
            page.wait_for_timeout(2500)
            confirmed = page.locator("[data-testid=apply-confirmed-badge]").count() > 0
        ok("version_confirmed_ui", confirmed, "")

        page.screenshot(path=str(OUT / "02-confirmed.png"), full_page=False)

        # Manual
        manual = page.locator("[data-testid=apply-manual]")
        ok("manual_enabled", manual.count() > 0 and manual.is_enabled(), "")
        if manual.is_enabled():
            manual.click()
            page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT / "03-manual.png"), full_page=False)
        ok(
            "manual_status",
            page.locator("[data-testid=apply-status]").count() > 0
            or "ready_for_manual" in page.inner_text("body").lower()
            or page.locator("[data-testid=manual-apply-guide]").count() > 0,
            "",
        )

        # Auto
        page.goto(apply_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        auto = page.locator("[data-testid=apply-auto]")
        if auto.count() and auto.is_enabled():
            auto.click()
            page.wait_for_timeout(4000)
        page.screenshot(path=str(OUT / "04-auto-review.png"), full_page=False)
        ok("auto_review_steps", page.locator("[data-testid=apply-review-steps]").count() > 0, "")
        ok("paused_or_checklist", page.locator("[data-testid=paused-before-submit]").count() > 0 or page.locator("[data-testid=apply-review-fields]").count() > 0, "")

        # Flip review steps
        if page.locator("[data-testid=apply-review-step-ats]").count():
            page.locator("[data-testid=apply-review-step-ats]").click()
            page.wait_for_timeout(400)
            page.locator("[data-testid=apply-review-step-resume]").click()
            page.wait_for_timeout(400)
            page.locator("[data-testid=apply-review-step-pause]").click()
            page.wait_for_timeout(400)
            page.screenshot(path=str(OUT / "05-review-pause.png"), full_page=False)
            ok("review_navigation", True, "flipped profile→ats→resume→pause")
        else:
            ok("review_navigation", False, "no review steps")

        # Tailor panel: force Tailor view so Apply panel is mounted
        page.goto(f"{FE}/?view=resume&step=tailor", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        if page.locator("[data-testid=auth-gate]").count():
            page.locator("[data-testid=auth-demo]").click()
            page.wait_for_timeout(2000)
            page.goto(f"{FE}/?view=resume&step=tailor", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
        # Prefer Tailor panel over JD empty state
        if page.locator("text=Go to Tailor").count():
            page.locator("text=Go to Tailor").first.click()
            page.wait_for_timeout(1000)
        page.evaluate(
            """() => {
              const el = document.querySelector('[data-testid=right-scroll-column]');
              if (el) el.scrollTop = el.scrollHeight;
              const panel = document.querySelector('[data-testid=apply-mode-panel]');
              if (panel) panel.scrollIntoView({block:'center'});
            }"""
        )
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT / "06-tailor-apply-panel.png"), full_page=False)
        ok(
            "tailor_apply_panel",
            page.locator("[data-testid=apply-mode-panel]").count() > 0
            or page.locator("[data-testid=open-apply-workspace]").count() > 0
            or "Step 5" in page.inner_text("body"),
            "",
        )

        # Unconfirmed gate: clear confirm flag and show Confirm CTA on apply page
        with db.connect() as conn:
            conn.execute("UPDATE resume_versions SET is_confirmed = 0 WHERE id = ?", (version_id,))
            conn.commit()
        page.goto(apply_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT / "07-need-confirm.png"), full_page=False)
        ok(
            "unconfirmed_shows_confirm_cta",
            page.locator("[data-testid=apply-page-confirm]").count() > 0
            or page.locator("[data-testid=apply-need-confirm-hint]").count() > 0,
            "",
        )
        # Restore confirmed for other tests
        with db.connect() as conn:
            conn.execute("UPDATE resume_versions SET is_confirmed = 1 WHERE id = ?", (version_id,))
            conn.commit()

        browser.close()

    passed = all(c for _, c, _ in CHECKS)
    _write(passed, version_id=version_id, user_id=user_id)
    return 0 if passed else 1


def _write(passed: bool, **extra) -> None:
    report = {
        "passed": passed,
        "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
        **extra,
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Apply workspace gate",
        "",
        f"**Status: {'PASS' if passed else 'FAIL'}**",
        "",
        "## Checks",
        "",
        *[f"- {'PASS' if c else 'FAIL'}: `{n}` {d}" for n, c, d in CHECKS],
        "",
        "## Screenshots",
        "",
        "- `artifacts/funnel/apply-page/01-apply-workspace.png`",
        "- `artifacts/funnel/apply-page/02-confirmed.png`",
        "- `artifacts/funnel/apply-page/03-manual.png`",
        "- `artifacts/funnel/apply-page/04-auto-review.png`",
        "- `artifacts/funnel/apply-page/05-review-pause.png`",
        "- `artifacts/funnel/apply-page/06-tailor-apply-panel.png`",
        "",
    ]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
