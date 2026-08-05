"""JR-3: scoring uses JD body + skills; ranking bench on 5 fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.modules.job_discovery.scorer import score_job_detailed

RESUME = """
Jingxuan Data Analyst
Skills: SQL, Python, Tableau, Excel, A/B testing, dashboards, statistics
Experience building ETL pipelines and BI dashboards for product analytics.
"""

FIXTURES = [
    {
        "id": "da_sql_tableau",
        "title": "Data Analyst",
        "raw_text": (
            "About the role: Product analytics for growth. "
            "Responsibilities: build dashboards, run A/B tests, partner with PMs. "
            "Requirements: SQL, Tableau, Python, experimentation, statistics, Excel. "
            "Preferred: dbt, Snowflake, Looker. "
            + ("Dashboards and KPI reporting with SQL and Tableau. " * 6)
        ),
        "expect_rank_bucket": "high",
    },
    {
        "id": "bi_powerbi",
        "title": "Business Intelligence Analyst",
        "raw_text": (
            "Requirements: Power BI, SQL, Excel, visualization, dashboards required. "
            "Responsibilities: semantic models, DAX measures, stakeholder reporting. "
            + ("Power BI SQL Excel visualization dashboards. " * 6)
        ),
        "expect_rank_bucket": "high",
    },
    {
        "id": "de_spark",
        "title": "Data Engineer",
        "raw_text": (
            "Spark, Kafka, Java, Scala, Airflow, heavy pipeline ownership. "
            "Requirements: distributed systems, ETL at scale. "
            + ("Spark Kafka Airflow Scala pipelines. " * 6)
        ),
        "expect_rank_bucket": "mid",
    },
    {
        "id": "pm_generic",
        "title": "Product Manager",
        "raw_text": (
            "Roadmaps, stakeholders, agile ceremonies, no SQL required. "
            "Own discovery and delivery with design and engineering partners. "
            + ("Product roadmap stakeholder agile ceremonies. " * 6)
        ),
        "expect_rank_bucket": "low",
    },
    {
        "id": "nurse",
        "title": "Registered Nurse",
        "raw_text": (
            "Patient care, clinical shifts, hospital ward duties. "
            "Licensed RN required. No analytics tooling. "
            + ("Patient care clinical hospital ward nursing. " * 6)
        ),
        "expect_rank_bucket": "low",
    },
]


def main() -> int:
    query = "data analyst SQL Tableau"
    scored = []
    for fx in FIXTURES:
        detail = score_job_detailed(
            {"title": fx["title"], "raw_text": fx["raw_text"]},
            query,
            resume_text=RESUME,
        )
        scored.append({**fx, **detail})

    scored_sorted = sorted(scored, key=lambda x: x["match_score"], reverse=True)
    order = [x["id"] for x in scored_sorted]

    # High bucket must beat low bucket
    high_scores = [x["match_score"] for x in scored if x["expect_rank_bucket"] == "high"]
    low_scores = [x["match_score"] for x in scored if x["expect_rank_bucket"] == "low"]
    mid_scores = [x["match_score"] for x in scored if x["expect_rank_bucket"] == "mid"]

    checks = {
        "has_breakdown": all("score_breakdown" in x for x in scored),
        "has_matched_or_missing": all(
            ("matched_skills" in x and "missing_skills" in x) for x in scored
        ),
        "high_beat_low": min(high_scores) > max(low_scores),
        "da_before_nurse": order.index("da_sql_tableau") < order.index("nurse"),
        "pm_not_top": order[0] != "pm_generic" and order[0] != "nurse",
        "body_matters": (
            score_job_detailed(
                {"title": "Specialist", "raw_text": "SQL Tableau Python dashboards"},
                query,
                resume_text=RESUME,
            )["match_score"]
            >
            score_job_detailed(
                {"title": "Specialist", "raw_text": "unrelated hospital logistics"},
                query,
                resume_text=RESUME,
            )["match_score"]
        ),
    }

    report = {
        "order": order,
        "scores": {x["id"]: x["match_score"] for x in scored_sorted},
        "sample_breakdown": scored_sorted[0]["score_breakdown"],
        "sample_matched_skills": scored_sorted[0]["matched_skills"],
        "mid_scores": mid_scores,
        "pass_criteria": checks,
        "all_pass": all(checks.values()),
    }
    out = ROOT / "artifacts" / "jr-score-bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
