"""Sprint G: full-path E2E polish smoke (jobs → detail → tailor chrome → apply/outreach APIs)."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT = Path(r"d:\resume-agent\artifacts\funnel\sprint-g")
OUT.mkdir(parents=True, exist_ok=True)
API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"
CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


# API spine
with httpx.Client(timeout=60) as client:
    health = client.get(f"{API}/health")
    ok("api_health", health.status_code == 200, "")
    jobs = client.get(
        f"{API}/api/v1/jobs/list",
        params={
            "user_id": "00000000-0000-0000-0000-0000000000a1",
            "threshold": "0",
            "category": "Data Analysis",
            "sort_by": "score",
        },
    )
    ok("jobs_list", jobs.status_code == 200 and len(jobs.json().get("jobs") or []) > 0, str(jobs.status_code))
    jlist = jobs.json().get("jobs") or []
    scores = sorted({int(j["stage3Result"]["finalScore"] * 100) for j in jlist[:12]})
    ok("scores_not_flat_35", len(scores) > 1 and scores != [35], str(scores[:8]))
    job_id = jlist[0]["id"]
    detail = client.get(f"{API}/api/v1/jobs/{job_id}/summary")
    ok("job_summary", detail.status_code == 200, str(detail.status_code))
    consti = client.get(f"{API}/api/v1/resume-workspace/constitution")
    ok("constitution", consti.status_code == 200, "")

auth = httpx.post(
    f"{API}/api/v1/auth/login",
    json={"email": "demo@resume-agent.local", "password": "demo-pass-1234"},
    timeout=30,
).json()
blob = {
    "token": auth["access_token"],
    "user": {"id": auth["user"]["id"], "email": auth["user"]["email"], "full_name": auth["user"].get("full_name")},
}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    page = browser.new_context(viewport={"width": 1440, "height": 960}).new_page()
    page.goto(FE, wait_until="domcontentloaded")
    page.evaluate("(b)=>localStorage.setItem('resume-agent-auth', JSON.stringify(b))", blob)

    page.goto(f"{FE}/jobs", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    page.screenshot(path=str(OUT / "01-jobs.png"), full_page=False)
    ok("ui_jobs", page.locator("[data-testid=jobs-table-body]").count() > 0 or page.locator("[data-testid=ranked-jobs-page]").count() > 0, "")

    page.goto(f"{FE}/jobs/{job_id}", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / "02-detail.png"), full_page=False)
    body = page.inner_text("body")
    ok("ui_detail_score", "%" in body and ("Match" in body or "ATS" in body), "")
    ok("ui_no_fake_semantic_label", "Skill coverage" in body or "ATS keywords" in body or "Heuristic" in body, "")

    page.goto(f"{FE}/?view=resume&jobId={job_id}", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=resume-workspace]", timeout=30000)
    for _ in range(90):
        if page.locator("[data-testid=apply-mode-panel]").count():
            break
        page.wait_for_timeout(1000)
    page.screenshot(path=str(OUT / "03-tailor.png"), full_page=False)
    ok("ui_tailor", page.locator("[data-testid=resume-workspace]").count() > 0, "")
    ok("ui_apply_panel", page.locator("[data-testid=apply-mode-panel]").count() > 0, "")
    # empty/error: paste JD control present
    ok("ui_paste_jd", "Paste JD" in page.inner_text("body"), "")
    browser.close()

# Prior sprint gates still green
for name, path in [
    ("sprint_bc", Path(r"d:\resume-agent\artifacts\funnel\sprint-bc\report.json")),
    ("sprint_d", Path(r"d:\resume-agent\artifacts\funnel\sprint-d\report.json")),
    ("sprint_e", Path(r"d:\resume-agent\artifacts\funnel\sprint-e\report.json")),
    ("sprint_f", Path(r"d:\resume-agent\artifacts\funnel\sprint-f\report.json")),
]:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        ok(f"prior_{name}", bool(data.get("passed")), "")
    else:
        ok(f"prior_{name}", False, "missing")

passed = all(c for _, c, _ in CHECKS)
report = {"sprint": "G", "passed": passed, "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS]}
(OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
sys.exit(0 if passed else 1)
