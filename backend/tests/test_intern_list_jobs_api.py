from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.modules.intern_list_scraper.db import connect
from app.modules.intern_list_scraper.query import get_job, search_jobs

client = TestClient(app)

_NOW = "2026-08-13T00:00:00+00:00"


def _seed(db_path: Path, n: int = 25) -> None:
    conn = connect(db_path)
    for i in range(n):
        job_id = f"job-{i:03d}"
        conn.execute(
            """
            INSERT INTO intern_list_jobs (
                job_id, category, slug, country, title, company, location, salary,
                work_model, industry_json, posted_at, list_json, scraped_at, updated_at
            ) VALUES (?, ?, ?, 'us', ?, ?, 'Remote', '', 'Remote', '[]', ?, '{}', ?, ?)
            """,
            (
                job_id,
                "Data Analysis",
                "data_analysis",
                f"Data Analyst {i}",
                f"Acme {i}",
                1_000_000 - i,
                _NOW,
                _NOW,
            ),
        )
    # same job_id, second category — must not double-count
    conn.execute(
        """
        INSERT INTO intern_list_jobs (
            job_id, category, slug, country, title, company, location, salary,
            work_model, industry_json, posted_at, list_json, scraped_at, updated_at
        ) VALUES ('job-000', 'SWE', 'swe', 'us', 'Data Analyst 0', 'Acme 0',
                  'Remote', '', 'Remote', '[]', 1000000, '{}', ?, ?)
        """,
        (_NOW, _NOW),
    )
    conn.execute(
        """
        INSERT INTO intern_list_job_details (
            job_id, title, company, location, work_model, employment_type,
            publish_time, job_summary, detail_url, apply_url, data_source_json,
            sections_json, scraped_at, updated_at
        ) VALUES (
            'job-000', 'Data Analyst 0', 'Acme 0', 'Remote', 'Remote', 'Intern',
            '', 'Clean data and build dashboards.',
            'https://jobright.ai/jobs/info/job-000', '', '{}',
            '{"title":"Data Analyst 0","company":"Acme 0","summary":"Clean data.",
              "responsibilities":["SQL"],"required":["Python"],"preferred":[],
              "qualification":[]}',
            ?, ?
        )
        """,
        (_NOW, _NOW),
    )
    conn.commit()
    conn.close()


def test_search_jobs_default_page_is_20(tmp_path: Path) -> None:
    db = tmp_path / "jobs.db"
    _seed(db, 25)
    page1 = search_jobs(page=1, db_path=db)
    assert page1["page"] == 1
    assert page1["page_size"] == 20
    assert page1["total"] == 25
    assert page1["total_pages"] == 2
    assert len(page1["items"]) == 20
    page2 = search_jobs(page=2, db_path=db)
    assert len(page2["items"]) == 5
    ids = {x["job_id"] for x in page1["items"]} | {x["job_id"] for x in page2["items"]}
    assert len(ids) == 25


def test_search_jobs_q_and_slug(tmp_path: Path) -> None:
    db = tmp_path / "jobs.db"
    _seed(db, 3)
    hit = search_jobs(q="Acme 1", db_path=db)
    assert hit["total"] == 1
    assert hit["items"][0]["company"] == "Acme 1"
    da = search_jobs(slug="da", db_path=db)
    assert da["total"] == 3
    swe = search_jobs(slug="swe", db_path=db)
    assert swe["total"] == 1
    assert swe["items"][0]["job_id"] == "job-000"


def test_get_job_includes_jd_text(tmp_path: Path) -> None:
    db = tmp_path / "jobs.db"
    _seed(db, 1)
    job = get_job("job-000", db_path=db)
    assert job is not None
    assert "Python" in job["jd_text"]
    assert job["has_detail"] is True
    assert get_job("missing", db_path=db) is None


def test_intern_list_jobs_api_default_page_size() -> None:
    res = client.get("/api/v1/intern-list/jobs")
    assert res.status_code == 200
    body = res.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert len(body["items"]) <= 20
    assert "total_pages" in body
