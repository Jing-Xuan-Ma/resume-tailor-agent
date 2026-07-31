#!/usr/bin/env python3
"""Run the demonstrable golden-path acceptance chain.

Usage (from backend/):

    DATABASE_URL=sqlite:///./data/golden_path.db \\
      python -m scripts.run_golden_path

Or via pytest (CI / offline, provider fallback forced):

    pytest tests/test_golden_path.py -v

Checklist covered
-----------------
[ ] Upload resume
[ ] auto-discover (query derived from resume when omitted)
[ ] Pick 1 job
[ ] Tailor resume
[ ] Generate application package
[ ] Manual confirm submit
[ ] Edge: no resume → 400
[ ] Edge: provider miss → synthetic fallback
[ ] Edge: hung JobSpy → prompt return (see test_jobspy_timeout / test_golden_path)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

# Allow `python -m scripts.run_golden_path` from backend/
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


SAMPLE_RESUME = """Jane Doe
jane@example.com
Data analyst with Python and SQL experience building dashboards.

PROFESSIONAL EXPERIENCE
Data Analyst | Example Analytics | Remote - 2022 - Present
• Built Python and SQL dashboards for weekly business reporting.
• Automated data quality checks and reduced manual review time by 30%.

SKILLS & CERTIFICATIONS
Python, SQL, FastAPI, Tableau
"""


class StepFailure(RuntimeError):
    pass


def _ok(label: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"  ✅ {label}{suffix}")


def _fail(label: str, detail: str) -> None:
    print(f"  ❌ {label} — {detail}")
    raise StepFailure(detail)


def run(force_fallback: bool = True) -> dict:
    from fastapi.testclient import TestClient

    from app.main import app
    import app.modules.job_discovery.router as job_router

    client = TestClient(app)
    user_id = str(uuid4())
    results: dict = {"user_id": user_id, "steps": []}

    # Optionally force provider miss so demos never hang on live job boards.
    original_discover_all = job_router.discover_all
    if force_fallback:

        async def _empty(**kwargs):
            return []

        job_router.discover_all = _empty  # type: ignore[assignment]

    try:
        print("\n=== Golden path acceptance ===\n")

        # Edge: no resume
        bare = client.post(
            "/api/v1/jobs/auto-discover",
            json={"user_id": user_id, "limit": 1},
        )
        if bare.status_code != 400:
            _fail("Edge: no resume → 400", f"got {bare.status_code}: {bare.text}")
        _ok("Edge: no resume → 400")

        # 1) Upload
        upload = client.post(
            "/api/v1/resume-tailor/upload-resume",
            json={"user_id": user_id, "resume_text": SAMPLE_RESUME},
        )
        if upload.status_code != 200:
            _fail("Upload resume", upload.text)
        resume_id = upload.json()["resume_id"]
        _ok("Upload resume", resume_id)
        results["resume_id"] = resume_id

        # 2) Auto-discover
        discovered = client.post(
            "/api/v1/jobs/auto-discover",
            json={"user_id": user_id, "limit": 2},
        )
        if discovered.status_code != 200:
            _fail("auto-discover", discovered.text)
        jobs = discovered.json()["jobs"]
        if not jobs:
            _fail("auto-discover", "returned zero jobs")
        source = jobs[0].get("source_platform")
        _ok("auto-discover", f"{len(jobs)} jobs (source={source})")
        if force_fallback and source != "local_phase2":
            _fail("Edge: provider miss → synthetic fallback", f"source={source}")
        if force_fallback:
            _ok("Edge: provider miss → synthetic fallback")
        results["jobs"] = [{"id": j["id"], "title": j["title"], "source": j["source_platform"]} for j in jobs]

        # 3) Pick one
        job = jobs[0]
        job_id = job["id"]
        _ok("Pick 1 job", f"{job['title']} ({job_id})")
        results["job_id"] = job_id

        # 4) Tailor
        tailored = client.post(
            "/api/v1/resume-tailor/tailor",
            json={
                "user_id": user_id,
                "resume_id": resume_id,
                "jd_text": job["raw_text"],
                "job_id": job_id,
            },
        )
        if tailored.status_code != 200:
            _fail("Tailor resume", tailored.text)
        tailored_id = tailored.json().get("tailored_resume_id")
        if not tailored_id:
            _fail("Tailor resume", "missing tailored_resume_id")
        _ok("Tailor resume", tailored_id)
        results["tailored_resume_id"] = tailored_id

        # 5) Prepare package
        prepared = client.post(
            f"/api/v1/jobs/{job_id}/prepare-application",
            json={
                "user_id": user_id,
                "resume_id": resume_id,
                "include_cover_letter": True,
                "include_application_plan": True,
                "submit_mode": "manual_review",
                "user_profile": {"full_name": "Jane Doe", "email": "jane@example.com"},
            },
        )
        if prepared.status_code != 200:
            _fail("Generate application package", prepared.text)
        package = prepared.json()
        plan = package.get("application_plan") or {}
        run_id = plan.get("application_run_id")
        if not run_id:
            _fail("Generate application package", "missing application_run_id")
        if not package.get("cover_letter", {}).get("id"):
            _fail("Generate application package", "missing cover_letter")
        _ok("Generate application package", run_id)
        results["application_run_id"] = run_id

        # 6) Manual confirm
        confirm = client.post(
            f"/api/v1/applications/{run_id}/confirm-manual-submit",
            json={
                "user_id": user_id,
                "confirmation_note": "Golden-path demo: reviewed and submitted.",
            },
        )
        if confirm.status_code != 200:
            _fail("Manual confirm submit", confirm.text)
        status = confirm.json().get("status")
        if status != "submitted_by_user":
            _fail("Manual confirm submit", f"status={status}")
        _ok("Manual confirm submit", status)
        results["status"] = status

        print("\nAll golden-path steps passed.\n")
        return results
    finally:
        job_router.discover_all = original_discover_all


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-providers",
        action="store_true",
        help="Do not force empty providers; hit real discovery providers (may be slow).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable result JSON at the end.",
    )
    args = parser.parse_args()
    try:
        results = run(force_fallback=not args.live_providers)
    except StepFailure:
        return 1
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"  ❌ Unexpected error — {exc}")
        return 1
    if args.json:
        print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
