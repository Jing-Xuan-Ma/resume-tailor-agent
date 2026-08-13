"""Wave 18 gates."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path(r"d:\resume-agent\artifacts\funnel\week")
CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


auth = Path(r"d:\resume-agent\frontend\lib\auth-user.ts").read_text(encoding="utf-8")
jobs = Path(r"d:\resume-agent\frontend\components\ranked-jobs-table.tsx").read_text(encoding="utf-8")
detail = Path(r"d:\resume-agent\frontend\app\jobs\[id]\page.tsx").read_text(encoding="utf-8")
ws = Path(r"d:\resume-agent\frontend\components\resume-workspace.tsx").read_text(encoding="utf-8")
ok("w57_shared_auth_util", "getAuthUserId" in auth and "from \"@/lib/auth-user\"" in jobs)
ok("w57_detail_passes_user", "getAuthUserId" in detail and "user_id=" in detail)
ok("w58_pdf_pending_boot_notice", "master PDF rendering" in ws)

API = "http://127.0.0.1:8000"
auth_json = json.loads(
    urlopen(
        Request(
            f"{API}/api/v1/auth/login",
            data=json.dumps({"email": "demo@resume-agent.local", "password": "demo-pass-1234"}).encode(),
            headers={"Content-Type": "application/json"},
        ),
        timeout=30,
    ).read()
)
uid = auth_json["user"]["id"]
jobs_json = json.loads(
    urlopen(f"{API}/api/v1/jobs/list?user_id={uid}&threshold=0&sort_by=score", timeout=60).read()
)
jid = (jobs_json.get("jobs") or [{}])[0].get("id")
summary = json.loads(urlopen(f"{API}/api/v1/jobs/{jid}/summary?user_id={uid}", timeout=60).read())
ok("w57_summary_scored_for_user", bool(summary.get("scoredForUser")), str(summary.get("scoredForUser")))

report = {
    "wave": 18,
    "passed": all(c for _, c, _ in CHECKS),
    "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
}
(OUT / "w18-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
