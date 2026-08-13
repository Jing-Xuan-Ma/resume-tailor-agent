"""SQLite persistence into data/app.db."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

DEFAULT_DB_PATH = Path(__file__).resolve().parents[4] / "data" / "app.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS intern_list_jobs (
    job_id TEXT NOT NULL,
    category TEXT NOT NULL,
    slug TEXT NOT NULL,
    country TEXT NOT NULL DEFAULT 'us',
    title TEXT,
    company TEXT,
    location TEXT,
    salary TEXT,
    work_model TEXT,
    industry_json TEXT NOT NULL DEFAULT '[]',
    posted_at INTEGER,
    list_json TEXT NOT NULL,
    scraped_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (job_id, category)
);
CREATE INDEX IF NOT EXISTS idx_intern_list_jobs_slug
    ON intern_list_jobs(slug, scraped_at);
CREATE INDEX IF NOT EXISTS idx_intern_list_jobs_company
    ON intern_list_jobs(company);

CREATE TABLE IF NOT EXISTS intern_list_job_details (
    job_id TEXT PRIMARY KEY,
    title TEXT,
    company TEXT,
    location TEXT,
    work_model TEXT,
    employment_type TEXT,
    publish_time TEXT,
    job_summary TEXT,
    detail_url TEXT,
    apply_url TEXT,
    data_source_json TEXT NOT NULL,
    sections_json TEXT NOT NULL DEFAULT '{}',
    scraped_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intern_list_details_company
    ON intern_list_job_details(company);

CREATE TABLE IF NOT EXISTS intern_list_scrape_state (
    category TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    last_posted_at INTEGER,
    last_run_at TEXT,
    last_fetched INTEGER NOT NULL DEFAULT 0,
    last_new INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA_SQL)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(intern_list_job_details)").fetchall()}
    if cols and "sections_json" not in cols:
        conn.execute(
            "ALTER TABLE intern_list_job_details ADD COLUMN sections_json TEXT NOT NULL DEFAULT '{}'"
        )
        conn.commit()
    return conn


def _props(item: dict[str, Any]) -> dict[str, Any]:
    props = item.get("properties") or {}
    return props if isinstance(props, dict) else {}


def upsert_list_job(
    conn: sqlite3.Connection,
    item: dict[str, Any],
    *,
    category: str,
    slug: str,
    country: str = "us",
    also_job_listings: bool = True,
) -> tuple[str, bool]:
    """Upsert list row by (job_id, category). Optionally mirror into job_listings."""
    job_id = str(item.get("jobId") or "").strip()
    if not job_id:
        raise ValueError("list item missing jobId")
    props = _props(item)
    title = str(props.get("title") or "").strip() or "(untitled)"
    company = str(props.get("company") or "").strip() or None
    location = str(props.get("location") or "").strip() or None
    salary = str(props.get("salary") or "").strip() or None
    work_model = str(props.get("workModel") or "").strip() or None
    industry = props.get("industry") or []
    if not isinstance(industry, list):
        industry = [industry]
    posted_at = item.get("postedAt")
    try:
        posted_at_i = int(posted_at) if posted_at is not None else None
    except (TypeError, ValueError):
        posted_at_i = None
    now = utcnow()
    existing = conn.execute(
        "SELECT job_id FROM intern_list_jobs WHERE job_id = ? AND category = ?",
        (job_id, category),
    ).fetchone()
    created = existing is None
    conn.execute(
        """
        INSERT INTO intern_list_jobs (
            job_id, category, slug, country, title, company, location, salary,
            work_model, industry_json, posted_at, list_json, scraped_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id, category) DO UPDATE SET
            slug=excluded.slug,
            country=excluded.country,
            title=excluded.title,
            company=excluded.company,
            location=excluded.location,
            salary=excluded.salary,
            work_model=excluded.work_model,
            industry_json=excluded.industry_json,
            posted_at=excluded.posted_at,
            list_json=excluded.list_json,
            scraped_at=excluded.scraped_at,
            updated_at=excluded.updated_at
        """,
        (
            job_id,
            category,
            slug,
            country,
            title,
            company,
            location,
            salary,
            work_model,
            json.dumps(industry, ensure_ascii=False),
            posted_at_i,
            json.dumps(item, ensure_ascii=False),
            now,
            now,
        ),
    )

    if also_job_listings:
        _mirror_to_job_listings(
            conn,
            job_id=job_id,
            title=title,
            company=company,
            location=location,
            work_model=work_model or "unknown",
            category=slug,
            source_url=f"https://jobright.ai/jobs/info/{job_id}",
            raw_text=_list_raw_text(title, company, location, props),
            metadata={
                "jobright_job_id": job_id,
                "intern_list_category": category,
                "salary": salary,
                "industry": industry,
                "posted_at": posted_at_i,
                "source": "intern_list",
            },
        )
    return job_id, created


def upsert_detail(
    conn: sqlite3.Connection,
    detail: dict[str, Any],
    *,
    also_job_listings: bool = True,
) -> tuple[str, bool]:
    from app.modules.intern_list_scraper.jd_sections import parse_jd_sections

    job_id = str(detail.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("detail missing job_id")
    data_source = detail.get("data_source") or {}
    sections = parse_jd_sections(data_source if isinstance(data_source, dict) else {})
    job_result = data_source.get("jobResult") or {}
    title = sections.get("title")
    company = sections.get("company")
    location = sections.get("location")
    work_model = sections.get("work_model")
    employment_type = sections.get("employment_type")
    publish_time = str(job_result.get("publishTime") or "").strip() or None
    job_summary = sections.get("summary")
    detail_url = str(detail.get("detail_url") or f"https://jobright.ai/jobs/info/{job_id}")
    apply_url = (
        str(job_result.get("jobCompanySiteUrl") or "").strip()
        or str(job_result.get("externalApplyUrl") or "").strip()
        or str(job_result.get("applyUrl") or "").strip()
        or None
    )
    now = utcnow()
    existing = conn.execute(
        "SELECT job_id FROM intern_list_job_details WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    created = existing is None
    conn.execute(
        """
        INSERT INTO intern_list_job_details (
            job_id, title, company, location, work_model, employment_type,
            publish_time, job_summary, detail_url, apply_url, data_source_json,
            sections_json, scraped_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            title=excluded.title,
            company=excluded.company,
            location=excluded.location,
            work_model=excluded.work_model,
            employment_type=excluded.employment_type,
            publish_time=excluded.publish_time,
            job_summary=excluded.job_summary,
            detail_url=excluded.detail_url,
            apply_url=excluded.apply_url,
            data_source_json=excluded.data_source_json,
            sections_json=excluded.sections_json,
            scraped_at=excluded.scraped_at,
            updated_at=excluded.updated_at
        """,
        (
            job_id,
            title,
            company,
            location,
            work_model,
            employment_type,
            publish_time,
            job_summary,
            detail_url,
            apply_url,
            json.dumps(data_source, ensure_ascii=False),
            json.dumps(sections, ensure_ascii=False),
            now,
            now,
        ),
    )

    if also_job_listings:
        raw_parts = [
            title or "",
            f"Company: {company}" if company else "",
            f"Location: {location}" if location else "",
            job_summary or "",
            "Responsibilities:",
            *[f"- {x}" for x in (sections.get("responsibilities") or [])],
            "Qualification:",
            *[f"- {x}" for x in (sections.get("qualification") or [])],
            "Required:",
            *[f"- {x}" for x in (sections.get("required") or [])],
            "Preferred:",
            *[f"- {x}" for x in (sections.get("preferred") or [])],
        ]
        raw_text = "\n".join(p for p in raw_parts if p).strip() or (title or job_id)
        list_row = conn.execute(
            "SELECT slug FROM intern_list_jobs WHERE job_id = ? ORDER BY updated_at DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        category = list_row["slug"] if list_row else "other"
        _mirror_to_job_listings(
            conn,
            job_id=job_id,
            title=title or "(untitled)",
            company=company,
            location=location,
            work_model=work_model or "unknown",
            category=category,
            source_url=apply_url or detail_url,
            raw_text=raw_text,
            metadata={
                "jobright_job_id": job_id,
                "detail_url": detail_url,
                "apply_url": apply_url,
                "employment_type": employment_type,
                "publish_time": publish_time,
                "sections": sections,
                "source": "intern_list_detail",
            },
        )
    return job_id, created


def list_job_ids_missing_details(
    conn: sqlite3.Connection, *, slugs: list[str] | None = None
) -> list[str]:
    if slugs:
        placeholders = ",".join("?" for _ in slugs)
        rows = conn.execute(
            f"""
            SELECT DISTINCT j.job_id
            FROM intern_list_jobs j
            LEFT JOIN intern_list_job_details d ON d.job_id = j.job_id
            WHERE j.slug IN ({placeholders})
              AND (d.job_id IS NULL OR d.sections_json IS NULL OR d.sections_json = '{{}}'
                   OR d.sections_json = '')
            ORDER BY j.posted_at DESC
            """,
            slugs,
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT DISTINCT j.job_id
            FROM intern_list_jobs j
            LEFT JOIN intern_list_job_details d ON d.job_id = j.job_id
            WHERE d.job_id IS NULL OR d.sections_json IS NULL OR d.sections_json = '{}'
               OR d.sections_json = ''
            ORDER BY j.posted_at DESC
            """
        ).fetchall()
    return [r["job_id"] for r in rows]


def list_all_job_ids_for_slugs(
    conn: sqlite3.Connection, *, slugs: list[str] | None = None
) -> list[str]:
    if slugs:
        placeholders = ",".join("?" for _ in slugs)
        rows = conn.execute(
            f"""
            SELECT DISTINCT job_id FROM intern_list_jobs
            WHERE slug IN ({placeholders})
            ORDER BY posted_at DESC
            """,
            slugs,
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT job_id FROM intern_list_jobs ORDER BY posted_at DESC"
        ).fetchall()
    return [r["job_id"] for r in rows]


def _list_raw_text(title: str, company: str | None, location: str | None, props: dict[str, Any]) -> str:
    quals = str(props.get("qualifications") or "").strip()
    parts = [
        title,
        f"Company: {company}" if company else "",
        f"Location: {location}" if location else "",
        f"Salary: {props.get('salary')}" if props.get("salary") else "",
        f"Work model: {props.get('workModel')}" if props.get("workModel") else "",
        quals,
    ]
    return "\n".join(p for p in parts if p).strip()


def _mirror_to_job_listings(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    title: str,
    company: str | None,
    location: str | None,
    work_model: str,
    category: str,
    source_url: str | None,
    raw_text: str,
    metadata: dict[str, Any],
) -> None:
    """Best-effort write into existing job_listings catalog if table exists."""
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "job_listings" not in tables:
        return
    fingerprint = f"jobright:{job_id}"
    now = utcnow()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(job_listings)").fetchall()}
    existing = conn.execute(
        "SELECT id FROM job_listings WHERE fingerprint = ?",
        (fingerprint,),
    ).fetchone()
    meta_json = json.dumps(metadata, ensure_ascii=False)
    if existing:
        listing_id = existing["id"]
        if "work_model" in cols and "category" in cols:
            conn.execute(
                """
                UPDATE job_listings
                SET title=?, company=?, location=?, source_url=?, source_platform=?,
                    raw_text=?, metadata_json=?, status='active', scraped_at=?,
                    updated_at=?, work_model=?, category=?
                WHERE id=?
                """,
                (
                    title,
                    company,
                    location,
                    source_url,
                    "intern_list",
                    raw_text,
                    meta_json,
                    now,
                    now,
                    (work_model or "unknown").lower(),
                    (category or "other").lower(),
                    listing_id,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE job_listings
                SET title=?, company=?, location=?, source_url=?, source_platform=?,
                    raw_text=?, metadata_json=?, status='active', scraped_at=?,
                    updated_at=?
                WHERE id=?
                """,
                (
                    title,
                    company,
                    location,
                    source_url,
                    "intern_list",
                    raw_text,
                    meta_json,
                    now,
                    now,
                    listing_id,
                ),
            )
        return

    listing_id = str(uuid4())
    if "work_model" in cols and "category" in cols:
        conn.execute(
            """
            INSERT INTO job_listings (
                id, fingerprint, title, company, location, source_url,
                source_platform, raw_text, metadata_json, status,
                scraped_at, created_at, updated_at, work_model, category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
            """,
            (
                listing_id,
                fingerprint,
                title,
                company,
                location,
                source_url,
                "intern_list",
                raw_text,
                meta_json,
                now,
                now,
                now,
                (work_model or "unknown").lower(),
                (category or "other").lower(),
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO job_listings (
                id, fingerprint, title, company, location, source_url,
                source_platform, raw_text, metadata_json, status,
                scraped_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                listing_id,
                fingerprint,
                title,
                company,
                location,
                source_url,
                "intern_list",
                raw_text,
                meta_json,
                now,
                now,
                now,
            ),
        )


def known_job_ids(conn: sqlite3.Connection, category: str) -> set[str]:
    rows = conn.execute(
        "SELECT job_id FROM intern_list_jobs WHERE category = ?",
        (category,),
    ).fetchall()
    return {r["job_id"] for r in rows}


def get_watermark(conn: sqlite3.Connection, category: str) -> int | None:
    row = conn.execute(
        "SELECT last_posted_at FROM intern_list_scrape_state WHERE category = ?",
        (category,),
    ).fetchone()
    if not row:
        return None
    val = row["last_posted_at"]
    return int(val) if val is not None else None


def save_scrape_state(
    conn: sqlite3.Connection,
    *,
    category: str,
    slug: str,
    last_posted_at: int | None,
    fetched: int,
    new_count: int,
) -> None:
    now = utcnow()
    conn.execute(
        """
        INSERT INTO intern_list_scrape_state (
            category, slug, last_posted_at, last_run_at, last_fetched, last_new, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(category) DO UPDATE SET
            slug=excluded.slug,
            last_posted_at=COALESCE(excluded.last_posted_at, intern_list_scrape_state.last_posted_at),
            last_run_at=excluded.last_run_at,
            last_fetched=excluded.last_fetched,
            last_new=excluded.last_new,
            updated_at=excluded.updated_at
        """,
        (category, slug, last_posted_at, now, fetched, new_count, now),
    )


def max_posted_at(conn: sqlite3.Connection, category: str) -> int | None:
    row = conn.execute(
        "SELECT MAX(posted_at) AS m FROM intern_list_jobs WHERE category = ?",
        (category,),
    ).fetchone()
    if not row or row["m"] is None:
        return None
    return int(row["m"])


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    list_total = conn.execute("SELECT COUNT(*) AS n FROM intern_list_jobs").fetchone()["n"]
    detail_total = conn.execute(
        "SELECT COUNT(*) AS n FROM intern_list_job_details"
    ).fetchone()["n"]
    by_slug = conn.execute(
        """
        SELECT slug, COUNT(*) AS n
        FROM intern_list_jobs
        GROUP BY slug
        ORDER BY n DESC
        """
    ).fetchall()
    states = conn.execute(
        """
        SELECT category, slug, last_posted_at, last_run_at, last_fetched, last_new
        FROM intern_list_scrape_state
        ORDER BY slug
        """
    ).fetchall()
    return {
        "list_total": list_total,
        "detail_total": detail_total,
        "by_slug": {r["slug"]: r["n"] for r in by_slug},
        "scrape_state": [dict(r) for r in states],
        "db_path": str(Path(conn.execute("PRAGMA database_list").fetchone()["file"])),
    }
