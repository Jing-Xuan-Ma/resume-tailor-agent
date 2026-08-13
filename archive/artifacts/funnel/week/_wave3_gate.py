"""Wave 3 gates: JD plaintext, soft-confirm UX, flow apply step."""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(r"d:\resume-agent\artifacts\funnel\week")
OUT.mkdir(parents=True, exist_ok=True)
CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


sys.path.insert(0, r"d:\resume-agent\backend")
from app.modules.job_discovery.quality import jd_plaintext  # noqa: E402

sample = """
<p class="tw-border-b tw-shadow tw-ring-offset-width">About the role</p>
<p>We need a Data Analyst with SQL.</p>
<ul><li>Tableau dashboards</li><li>Python scripting</li></ul>
<div class="tw-flex tw-gap-2 tw-items-center tw-justify-between">noise</div>
Preferred:
- Stakeholder communication
"""
clean = jd_plaintext(sample)
ok("w13_strips_html_tags", "<p" not in clean.lower() and "<li" not in clean.lower(), clean[:120])
ok("w13_keeps_content", "SQL" in clean and "Tableau" in clean, clean[:160])
ok("w13_drops_tw_noise", "tw-border-b" not in clean and "tw-ring-offset" not in clean, clean[:160])

fe_jd = Path(r"d:\resume-agent\frontend\components\jd-panel.tsx").read_text(encoding="utf-8")
ok("w13_fe_stripJdHtml", "stripJdHtml" in fe_jd and "tw-" in fe_jd)

ws = Path(r"d:\resume-agent\frontend\components\resume-workspace.tsx").read_text(encoding="utf-8")
ok("w14_soft_warnings_banner", "confirm-soft-warnings" in ws)
ok("w14_hard_issues_only_block", "hardEvidenceIssues" in ws and "weak textual support" in ws)
ok("w14_confirm_error_inline", "confirm-error" in ws and "alert(msg)" not in ws)
ok("w15_flow_apply_after_confirm", '? "apply"' in ws and 'activeVersion?.is_confirmed' in ws)

# live handoff sample
from urllib.request import Request, urlopen

API = "http://127.0.0.1:8000"
auth = json.loads(
    urlopen(
        Request(
            f"{API}/api/v1/auth/login",
            data=json.dumps({"email": "demo@resume-agent.local", "password": "demo-pass-1234"}).encode(),
            headers={"Content-Type": "application/json"},
        ),
        timeout=30,
    ).read()
)
uid = auth["user"]["id"]
jobs = json.loads(
    urlopen(
        f"{API}/api/v1/jobs/list?user_id={uid}&threshold=0&category=Data%20Analysis&sort_by=score",
        timeout=60,
    ).read()
)["jobs"]
job_id = jobs[0]["id"] if jobs else None
ok("w13_jobs_for_handoff", bool(job_id), str(job_id))
if job_id:
    handoff = json.loads(
        urlopen(
            Request(
                f"{API}/api/v1/jobs/{job_id}/to-resume-workspace?user_id={uid}",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=60,
        ).read()
    )
    jd = handoff.get("jd_text") or ""
    ok("w13_handoff_no_raw_tags", "<p" not in jd.lower() and "tw-border" not in jd, jd[:100])

passed = all(c for _, c, _ in CHECKS)
report = {
    "wave": 3,
    "passed": passed,
    "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
}
(OUT / "w13-w15-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if passed else 1)
