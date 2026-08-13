"""W10 score anti-inflation — use live jobs list + synthetic thin/rich."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, r"d:\resume-agent\backend")
from app.modules.job_discovery.scorer import score_job_detailed

OUT = Path(r"d:\resume-agent\artifacts\funnel\week")
API = "http://127.0.0.1:8000"
UID = "00000000-0000-0000-0000-0000000000a1"

thin = score_job_detailed(
    {
        "raw_text": "Label images. Click boxes. Microtask survey.",
        "title": "Data Labeling Specialist",
        "required_skills": ["labeling"],
        "preferred_skills": [],
        "ats_keywords": ["labeling"],
        "key_responsibilities": ["label data"],
    },
    "data labeling",
    "SQL Tableau Python dashboards stakeholder analytics A/B testing",
)
rich = score_job_detailed(
    {
        "raw_text": (
            "Data Analyst. Build SQL pipelines, Tableau dashboards, Python analyses, "
            "A/B testing, stakeholder reporting, warehouse ETL, Power BI."
        ),
        "title": "Data Analyst",
        "required_skills": ["sql", "tableau", "python", "power bi"],
        "preferred_skills": ["etl", "a/b testing"],
        "ats_keywords": ["sql", "tableau", "python", "dashboard"],
        "key_responsibilities": [
            "build dashboards",
            "analyze experiments",
            "stakeholder reporting",
        ],
    },
    "data analyst sql tableau",
    "Jingxuan Ma Data Analyst SQL Tableau Python Power BI A/B testing dashboards "
    "stakeholder reporting warehouse ETL analytics experiments",
)

with urlopen(
    f"{API}/api/v1/jobs/list?user_id={UID}&threshold=0&category=Data%20Analysis&sort_by=score",
    timeout=60,
) as r:
    jobs = json.loads(r.read().decode())["jobs"]
live = [int(j["stage3Result"]["finalScore"] * 100) for j in jobs[:40] if j.get("stage3Result")]
stuck35 = sum(1 for s in live if s == 35) / max(1, len(live))

out = {
    "thin": round(float(thin["match_score"]), 1),
    "rich": round(float(rich["match_score"]), 1),
    "live_unique": len(set(live)),
    "live_stuck_at_35_share": round(stuck35, 3),
    "live_sample": live[:12],
}
(OUT / "w10-score.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))
assert out["thin"] < out["rich"], out
assert out["thin"] < 25, out
assert out["live_stuck_at_35_share"] < 0.15, out
assert out["live_unique"] >= 5, out
print("W10 PASS")
