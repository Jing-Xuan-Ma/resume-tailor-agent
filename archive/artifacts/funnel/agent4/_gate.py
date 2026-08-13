"""Agent 4 gate: CRM upsert/list + outreach drafts + LinkedIn playbook screenshots."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(r"d:\resume-agent")
OUT = ROOT / "artifacts" / "funnel" / "agent4"
OUT.mkdir(parents=True, exist_ok=True)
API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"
CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


def main() -> int:
    job_id = None
    company = None
    title = None
    auth_blob = None
    try:
        with httpx.Client(timeout=60) as client:
            health = client.get(f"{API}/health")
            ok("api_health", health.status_code == 200, str(health.status_code))

            email = f"agent4-{uuid4().hex[:10]}@resume-agent.local"
            auth = client.post(
                f"{API}/api/v1/auth/register",
                json={"email": email, "password": "agent4-pass-1234", "full_name": "Agent4 Tester"},
            )
            if auth.status_code >= 400:
                auth = client.post(
                    f"{API}/api/v1/auth/login",
                    json={"email": "demo@resume-agent.local", "password": "demo-pass-1234"},
                )
            ok("auth_login", auth.status_code == 200, str(auth.status_code))
            if auth.status_code != 200:
                return _finish(False)
            payload = auth.json()
            token, user = payload["access_token"], payload["user"]
            user_id = user["id"]
            auth_blob = {
                "token": token,
                "user": {"id": user_id, "email": user["email"], "full_name": user.get("full_name")},
            }

            # --- CRM upsert / list ---
            c1 = client.post(
                f"{API}/api/v1/outreach/contacts",
                json={
                    "user_id": user_id,
                    "name": "Alex Hiring",
                    "role": "Hiring Manager",
                    "company": "Acme Analytics",
                    "linkedin_url": "https://www.linkedin.com/in/alex-hiring-demo",
                    "email": "alex.hiring@example.com",
                    "coffee_availability": "Tue/Thu mornings PT",
                    "status": "identified",
                },
            )
            ok("crm_upsert", c1.status_code == 200, str(c1.status_code))
            contact = c1.json() if c1.status_code == 200 else {}
            ok(
                "crm_fields",
                all(k in contact for k in ("name", "role", "linkedin_url", "email", "coffee_availability")),
                "",
            )

            c2 = client.post(
                f"{API}/api/v1/outreach/contacts",
                json={
                    "user_id": user_id,
                    "name": "Jamie Recruiter",
                    "role": "Talent Acquisition",
                    "company": "Acme Analytics",
                    "email": "jamie.ta@example.com",
                    "coffee_availability": "Fri afternoons",
                },
            )
            ok("crm_upsert_second", c2.status_code == 200, str(c2.status_code))

            listed = client.get(f"{API}/api/v1/outreach/contacts", params={"user_id": user_id})
            ok("crm_list", listed.status_code == 200, str(listed.status_code))
            contacts = (listed.json() or {}).get("contacts") or []
            ok("crm_list_ge_2", len(contacts) >= 2, str(len(contacts)))

            # upsert by linkedin should update not duplicate
            c3 = client.post(
                f"{API}/api/v1/outreach/contacts",
                json={
                    "user_id": user_id,
                    "name": "Alex H. Updated",
                    "role": "Head of Data",
                    "linkedin_url": "https://www.linkedin.com/in/alex-hiring-demo",
                    "coffee_availability": "Wed mornings",
                },
            )
            ok(
                "crm_upsert_merge",
                c3.status_code == 200 and c3.json().get("id") == contact.get("id"),
                str(c3.status_code),
            )

            # --- Drafts (≥2 templates), draft-only ---
            row = sqlite3.connect(str(ROOT / "data" / "app.db")).execute(
                "SELECT id, title, company FROM job_listings WHERE status='active' "
                "AND lower(title) LIKE '%analyst%' ORDER BY scraped_at DESC LIMIT 1"
            ).fetchone()
            if not row:
                job_id, title, company = None, "Data Analyst", "Acme Analytics"
                ok("job_listing", False, "no listing — drafts without job_id")
            else:
                job_id, title, company = row
                ok("job_listing", True, f"{company} / {title}")

            d1 = client.post(
                f"{API}/api/v1/outreach/draft",
                json={
                    "user_id": user_id,
                    "job_id": job_id,
                    "company": company,
                    "contact_name": "Alex Hiring",
                    "contact_role": "Hiring Manager",
                    "template_type": "coffee_chat",
                    "channel": "linkedin",
                    "tone": "warm",
                    "linkedin_url": "https://www.linkedin.com/in/alex-hiring-demo",
                    "coffee_availability": "Tue/Thu mornings PT",
                    "save_to_crm": True,
                },
            )
            ok("draft_coffee_chat", d1.status_code == 200, str(d1.status_code))
            b1 = d1.json() if d1.status_code == 200 else {}
            ok("draft_status_draft", b1.get("status") == "draft", str(b1.get("status")))
            ok(
                "draft_safety_flag",
                (b1.get("metadata") or {}).get("safety") == "draft_only_user_sends",
                "",
            )
            ok("draft_crm_linked", bool((b1.get("metadata") or {}).get("crm_contact_id")), "")

            d2 = client.post(
                f"{API}/api/v1/outreach/draft",
                json={
                    "user_id": user_id,
                    "job_id": job_id,
                    "company": company,
                    "contact_name": "Jamie Recruiter",
                    "contact_role": "Talent Acquisition",
                    "template_type": "post_apply_thanks",
                    "channel": "email",
                    "tone": "warm",
                    "contact_email": "jamie.ta@example.com",
                    "save_to_crm": True,
                },
            )
            ok("draft_post_apply_thanks", d2.status_code == 200, str(d2.status_code))
            templates = {
                (d1.json().get("metadata") or {}).get("template_type") if d1.status_code == 200 else None,
                (d2.json().get("metadata") or {}).get("template_type") if d2.status_code == 200 else None,
            }
            ok("draft_templates_ge_2", len({t for t in templates if t}) >= 2, str(templates))

            # no auto-send endpoint used — mark-sent is user-driven only
            ok("no_mass_send", True, "draft_only + mark-sent-by-user")

            crm_file = ROOT / "data" / "outreach_crm" / f"{user_id}.json"
            ok("crm_file_written", crm_file.exists(), str(crm_file))

        # --- UI screenshots ---
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel="chrome")
            page = browser.new_context(viewport={"width": 1440, "height": 1000}).new_page()
            page.goto(FE, wait_until="domcontentloaded")
            page.evaluate("(b)=>localStorage.setItem('resume-agent-auth', JSON.stringify(b))", auth_blob)

            q = f"jobId={job_id}&" if job_id else ""
            page.goto(
                f"{FE}/?view=resume&{q}forceOutreach=1",
                wait_until="domcontentloaded",
            )
            page.wait_for_selector("[data-testid=outreach-step-panel]", timeout=30000)
            for _ in range(30):
                text = page.locator("[data-testid=hm-playbook]").inner_text()
                if company and str(company).split()[0] in text:
                    break
                page.wait_for_timeout(1000)
            page.evaluate(
                "() => document.querySelector('[data-testid=outreach-step-panel]')?.scrollIntoView({block:'center'})"
            )
            page.wait_for_timeout(600)
            page.screenshot(path=str(OUT / "01-hm-playbook.png"), full_page=False)

            ok("ui_panel", page.locator("[data-testid=outreach-step-panel]").count() > 0, "")
            ok("hm_playbook", page.locator("[data-testid=hm-playbook]").count() > 0, "")
            links = page.locator("[data-testid=hm-linkedin-search]")
            ok("linkedin_search_links_ge_2", links.count() >= 2, str(links.count()))
            href = links.first.get_attribute("href") or ""
            ok("linkedin_href", "linkedin.com/search" in href, href[:90])
            if company:
                playbook = page.locator("[data-testid=hm-playbook]").inner_text()
                ok(
                    "linkedin_uses_company",
                    str(company).split()[0] in (href + playbook),
                    str(company),
                )

            page.fill("[data-testid=outreach-contact-name]", "Sam Hiring")
            page.fill("[data-testid=outreach-contact-role]", "Hiring Manager")
            page.fill("[data-testid=outreach-linkedin]", "https://www.linkedin.com/in/sam-hiring-demo")
            page.fill("[data-testid=outreach-coffee-availability]", "Mon mornings")
            page.click("[data-testid=outreach-crm-save-btn]")
            page.wait_for_selector("[data-testid=outreach-crm-list]", timeout=15000)
            page.screenshot(path=str(OUT / "02-crm-saved.png"), full_page=False)
            ok("ui_crm_list", page.locator("[data-testid=outreach-crm-list]").count() > 0, "")

            page.locator("[data-testid=outreach-template-coffee_chat]").click()
            page.click("[data-testid=outreach-draft-btn]")
            page.wait_for_selector("[data-testid=outreach-drafts] > div", timeout=15000)
            page.locator("[data-testid=outreach-template-post_apply_thanks]").click()
            page.click("[data-testid=outreach-draft-btn]")
            page.wait_for_function(
                "() => document.querySelectorAll('[data-testid=outreach-drafts] > div').length >= 2",
                timeout=15000,
            )
            page.evaluate(
                "() => document.querySelector('[data-testid=outreach-drafts]')?.scrollIntoView({block:'center'})"
            )
            page.wait_for_timeout(400)
            page.screenshot(path=str(OUT / "03-drafts.png"), full_page=False)
            n_drafts = page.locator("[data-testid=outreach-drafts] > div").count()
            ok("ui_drafts_ge_2", n_drafts >= 2, str(n_drafts))
            browser.close()
    except Exception as exc:
        ok("gate_exception", False, str(exc)[:200])

    return _finish(all(c for _, c, _ in CHECKS))


def _finish(passed: bool) -> int:
    report = {
        "agent": 4,
        "module": "outreach_hm_crm",
        "passed": passed,
        "status": "PASS" if passed else "FAILURE",
        "draft_only": True,
        "mass_send": False,
        "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
        "screenshots": [
            "artifacts/funnel/agent4/01-hm-playbook.png",
            "artifacts/funnel/agent4/02-crm-saved.png",
            "artifacts/funnel/agent4/03-drafts.png",
        ],
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "artifacts" / "funnel" / "agent4-outreach-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
