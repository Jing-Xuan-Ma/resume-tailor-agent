"""Paginated intern-list job search (dedupe by job_id)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.modules.intern_list_scraper.categories import normalize_slug
from app.modules.intern_list_scraper.db import connect
from app.modules.intern_list_scraper.jd_sections import parse_jd_sections

JOBRIGHT_DETAIL = "https://jobright.ai/jobs/info/{job_id}"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

_LIST_COLS = (
    "r.job_id, r.title, r.company, r.location, r.salary, r.work_model, "
    "r.slug, r.category, r.country, r.posted_at, r.updated_at, s.slugs, "
    "CASE WHEN d.job_id IS NULL THEN 0 ELSE 1 END AS has_detail, "
    "d.apply_url, d.detail_url, d.job_summary"
)


def _has_table(conn: Any, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _split_slugs(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [s.strip() for s in str(raw).split(",") if s.strip()]


def _item(row: Any) -> dict[str, Any]:
    job_id = row["job_id"]
    keys = row.keys()
    return {
        "job_id": job_id,
        "title": row["title"],
        "company": row["company"],
        "location": row["location"],
        "salary": row["salary"],
        "work_model": row["work_model"],
        "slug": row["slug"],
        "slugs": _split_slugs(row["slugs"] if "slugs" in keys else row["slug"]),
        "country": row["country"] if "country" in keys else "us",
        "posted_at": row["posted_at"],
        "has_detail": bool(row["has_detail"]),
        "apply_url": row["apply_url"] if "apply_url" in keys else None,
        "detail_url": (row["detail_url"] if "detail_url" in keys else None)
        or JOBRIGHT_DETAIL.format(job_id=job_id),
        "job_summary": row["job_summary"] if "job_summary" in keys else None,
    }


def _filters(q: str | None, slug: str | None) -> tuple[str, list[Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if slug and slug.strip():
        clauses.append("j.slug = ?")
        params.append(normalize_slug(slug.strip()))
    if q and q.strip():
        like = f"%{q.strip()}%"
        clauses.append("(j.title LIKE ? OR j.company LIKE ? OR j.location LIKE ?)")
        params.extend([like, like, like])
    return " AND ".join(clauses), params


def search_jobs(
    *,
    q: str | None = None,
    slug: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    page = max(1, int(page))
    page_size = min(MAX_PAGE_SIZE, max(1, int(page_size)))
    offset = (page - 1) * page_size
    where, params = _filters(q, slug)

    conn = connect(db_path)
    try:
        if not _has_table(conn, "intern_list_jobs"):
            return {
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
                "items": [],
            }
        total = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM (
              SELECT j.job_id FROM intern_list_jobs j
              WHERE {where}
              GROUP BY j.job_id
            )
            """,
            params,
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            WITH filtered AS (
              SELECT j.* FROM intern_list_jobs j WHERE {where}
            ),
            ranked AS (
              SELECT f.*, ROW_NUMBER() OVER (
                PARTITION BY f.job_id
                ORDER BY COALESCE(f.posted_at, 0) DESC, f.updated_at DESC
              ) AS rn
              FROM filtered f
            ),
            slug_agg AS (
              SELECT job_id, GROUP_CONCAT(DISTINCT slug) AS slugs
              FROM filtered GROUP BY job_id
            )
            SELECT {_LIST_COLS}
            FROM ranked r
            JOIN slug_agg s ON s.job_id = r.job_id
            LEFT JOIN intern_list_job_details d ON d.job_id = r.job_id
            WHERE r.rn = 1
            ORDER BY COALESCE(r.posted_at, 0) DESC, r.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "items": [_item(r) for r in rows],
        }
    finally:
        conn.close()


def _jd_text(sections: dict[str, Any], summary: str | None) -> str:
    blocks: list[str] = []
    head = " — ".join(x for x in (sections.get("title"), sections.get("company")) if x)
    if head:
        blocks.append(head)
    blurb = sections.get("summary") or summary
    if blurb:
        blocks.append(str(blurb))
    for label, key in (
        ("Responsibilities", "responsibilities"),
        ("Required", "required"),
        ("Preferred", "preferred"),
        ("Qualification", "qualification"),
    ):
        items = sections.get(key) or []
        if items:
            blocks.append(label + ":\n" + "\n".join(f"- {x}" for x in items))
    return "\n\n".join(blocks).strip()


def get_job(job_id: str, *, db_path: Path | str | None = None) -> dict[str, Any] | None:
    job_id = (job_id or "").strip()
    if not job_id:
        return None
    conn = connect(db_path)
    try:
        if not _has_table(conn, "intern_list_jobs"):
            return None
        row = conn.execute(
            """
            WITH filtered AS (
              SELECT j.* FROM intern_list_jobs j WHERE j.job_id = ?
            ),
            ranked AS (
              SELECT f.*, ROW_NUMBER() OVER (
                PARTITION BY f.job_id
                ORDER BY COALESCE(f.posted_at, 0) DESC, f.updated_at DESC
              ) AS rn
              FROM filtered f
            ),
            slug_agg AS (
              SELECT job_id, GROUP_CONCAT(DISTINCT slug) AS slugs
              FROM intern_list_jobs WHERE job_id = ? GROUP BY job_id
            )
            SELECT {cols}
            FROM ranked r
            JOIN slug_agg s ON s.job_id = r.job_id
            LEFT JOIN intern_list_job_details d ON d.job_id = r.job_id
            WHERE r.rn = 1
            LIMIT 1
            """.format(cols=_LIST_COLS),
            (job_id, job_id),
        ).fetchone()
        detail = None
        if _has_table(conn, "intern_list_job_details"):
            detail = conn.execute(
                "SELECT * FROM intern_list_job_details WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if not row and not detail:
            return None
        if row:
            item = _item(row)
        else:
            item = {
                "job_id": job_id,
                "title": detail["title"],
                "company": detail["company"],
                "location": detail["location"],
                "salary": None,
                "work_model": detail["work_model"],
                "slug": None,
                "slugs": [],
                "country": "us",
                "posted_at": None,
                "has_detail": True,
                "apply_url": detail["apply_url"],
                "detail_url": detail["detail_url"] or JOBRIGHT_DETAIL.format(job_id=job_id),
                "job_summary": detail["job_summary"],
            }
        sections: dict[str, Any] = {}
        if detail:
            try:
                sections = json.loads(detail["sections_json"] or "{}")
            except json.JSONDecodeError:
                sections = {}
            if not sections:
                try:
                    ds = json.loads(detail["data_source_json"] or "{}")
                    sections = parse_jd_sections(ds) if isinstance(ds, dict) else {}
                except Exception:  # noqa: BLE001
                    sections = {}
        item["sections"] = sections or None
        item["jd_text"] = _jd_text(sections, item.get("job_summary"))
        return item
    finally:
        conn.close()
