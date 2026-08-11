"""Shopping cart: batch tailor resume + cover letter for intern-list selections."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db import _DB_PATH

CART_ROOT = Path(__file__).resolve().parents[4] / "data" / "shopping_cart"


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def slugify(value: str, max_len: int = 60) -> str:
    text = (value or "Unknown").strip()
    text = re.sub(r'[\\/:*?"<>|]+', "", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._")
    return (text or "Unknown")[:max_len]


def folder_name(company: str, position: str) -> str:
    return f"{slugify(company)}_{slugify(position)}"


def cart_dir(cart_id: str) -> Path:
    return CART_ROOT / cart_id


def item_dir(cart_id: str, company: str, position: str) -> Path:
    return cart_dir(cart_id) / folder_name(company, position)


def save_cart_meta(cart_id: str, meta: dict[str, Any]) -> None:
    d = cart_dir(cart_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "cart.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cart_meta(cart_id: str) -> dict[str, Any] | None:
    path = cart_dir(cart_id) / "cart.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_item_files(
    *,
    cart_id: str,
    company: str,
    position: str,
    resume_md: str,
    cover_letter_md: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    d = item_dir(cart_id, company, position)
    d.mkdir(parents=True, exist_ok=True)
    resume_path = d / "resume.md"
    cl_path = d / "cover_letter.md"
    meta_path = d / "meta.json"
    resume_path.write_text(resume_md or "", encoding="utf-8")
    cl_path.write_text(cover_letter_md or "", encoding="utf-8")
    meta = {
        **meta,
        "company": company,
        "position": position,
        "folder": str(d),
        "updated_at": utcnow(),
        "formats": {"resume": "md", "cover_letter": "md"},
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "folder": str(d),
        "resume_md_path": str(resume_path),
        "cover_letter_md_path": str(cl_path),
        "meta_path": str(meta_path),
        "meta": meta,
    }


def write_pdfs(
    *,
    cart_id: str,
    company: str,
    position: str,
    resume_pdf: bytes,
    cover_letter_pdf: bytes,
    meta: dict[str, Any],
) -> dict[str, Any]:
    d = item_dir(cart_id, company, position)
    d.mkdir(parents=True, exist_ok=True)
    resume_path = d / "resume.pdf"
    cl_path = d / "cover_letter.pdf"
    resume_path.write_bytes(resume_pdf)
    cl_path.write_bytes(cover_letter_pdf)
    meta = {
        **meta,
        "confirmed_at": utcnow(),
        "status": "confirmed",
        "formats": {"resume": "pdf", "cover_letter": "pdf"},
        "resume_pdf_path": str(resume_path),
        "cover_letter_pdf_path": str(cl_path),
    }
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "resume_pdf_path": str(resume_path),
        "cover_letter_pdf_path": str(cl_path),
        "meta": meta,
    }


def read_item(cart_id: str, item_id: str) -> dict[str, Any] | None:
    meta = load_cart_meta(cart_id)
    if not meta:
        return None
    for item in meta.get("items") or []:
        if item.get("item_id") == item_id:
            company = item.get("company") or "Unknown"
            position = item.get("position") or "Unknown"
            d = item_dir(cart_id, company, position)
            resume_md = (
                (d / "resume.md").read_text(encoding="utf-8") if (d / "resume.md").exists() else ""
            )
            cl_md = (
                (d / "cover_letter.md").read_text(encoding="utf-8")
                if (d / "cover_letter.md").exists()
                else ""
            )
            item_meta = {}
            if (d / "meta.json").exists():
                item_meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            return {
                **item,
                "resume_md": resume_md,
                "cover_letter_md": cl_md,
                "item_meta": item_meta,
                "has_resume_pdf": (d / "resume.pdf").exists(),
                "has_cover_letter_pdf": (d / "cover_letter.pdf").exists(),
            }
    return None


def resolve_intern_job(intern_job_id: str) -> dict[str, Any]:
    """Map Jobright/intern-list job id → JD text + company/title."""
    from app import db
    from app.modules.job_discovery.quality import jd_plaintext

    intern_job_id = str(intern_job_id or "").strip()
    if not intern_job_id:
        raise ValueError("intern_job_id required")

    listing = db.get_job_listing_by_fingerprint(f"jobright:{intern_job_id}")
    intern = _intern_detail_jd(intern_job_id)

    if listing:
        jd_text = jd_plaintext((listing.get("raw_text") or "").strip())
        meta = listing.get("metadata") if isinstance(listing.get("metadata"), dict) else {}
        title = listing.get("title") or (intern or {}).get("title") or intern_job_id
        company = listing.get("company") or (intern or {}).get("company") or "Unknown"
        location = listing.get("location") or (intern or {}).get("location") or ""
        source_url = (
            listing.get("source_url")
            or meta.get("apply_url")
            or (intern or {}).get("apply_url")
            or (intern or {}).get("detail_url")
        )
        if not jd_text and intern:
            jd_text = intern["jd_text"]
        if not jd_text:
            jd_text = f"{title} at {company}"
        return {
            "intern_job_id": intern_job_id,
            "listing_id": listing["id"],
            "title": title,
            "company": company,
            "location": location,
            "source_url": source_url,
            "jd_text": jd_text,
            "has_detail": bool(intern and intern.get("has_detail")),
        }

    if not intern:
        raise ValueError(f"job not found: {intern_job_id}")

    return {
        "intern_job_id": intern_job_id,
        "listing_id": None,
        "title": intern.get("title") or intern_job_id,
        "company": intern.get("company") or "Unknown",
        "location": intern.get("location") or "",
        "source_url": intern.get("apply_url") or intern.get("detail_url"),
        "jd_text": intern["jd_text"],
        "has_detail": bool(intern.get("has_detail")),
    }


def _intern_detail_jd(intern_job_id: str) -> dict[str, Any] | None:
    if not _DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "intern_list_jobs" not in tables:
            return None
        detail = None
        if "intern_list_job_details" in tables:
            detail = conn.execute(
                "SELECT * FROM intern_list_job_details WHERE job_id = ?",
                (intern_job_id,),
            ).fetchone()
        list_row = conn.execute(
            "SELECT * FROM intern_list_jobs WHERE job_id = ? ORDER BY updated_at DESC LIMIT 1",
            (intern_job_id,),
        ).fetchone()
        if not detail and not list_row:
            return None
        sections: dict[str, Any] = {}
        if detail:
            try:
                sections = json.loads(detail["sections_json"] or "{}")
            except json.JSONDecodeError:
                sections = {}
        title = (
            (sections.get("title") if sections else None)
            or (detail["title"] if detail else None)
            or (list_row["title"] if list_row else None)
            or intern_job_id
        )
        company = (
            (sections.get("company") if sections else None)
            or (detail["company"] if detail else None)
            or (list_row["company"] if list_row else None)
        )
        location = (
            (sections.get("location") if sections else None)
            or (detail["location"] if detail else None)
            or (list_row["location"] if list_row else None)
        )
        apply_url = (detail["apply_url"] if detail else None) or None
        detail_url = (
            detail["detail_url"] if detail else None
        ) or f"https://jobright.ai/jobs/info/{intern_job_id}"
        if detail and (detail["job_summary"] or sections):
            parts = [
                f"{title} at {company}" if company else str(title),
                f"Location: {location}" if location else "",
                f"URL: {apply_url or detail_url}",
                "",
                str(sections.get("summary") or detail["job_summary"] or ""),
                "",
                "Responsibilities:",
                *[f"- {x}" for x in (sections.get("responsibilities") or [])],
                "Qualification:",
                *[f"- {x}" for x in (sections.get("qualification") or [])],
                "Required:",
                *[f"- {x}" for x in (sections.get("required") or [])],
                "Preferred:",
                *[f"- {x}" for x in (sections.get("preferred") or [])],
            ]
            jd_text = "\n".join(p for p in parts if p is not None).strip()
        else:
            from app.modules.job_discovery.quality import jd_plaintext

            raw = (list_row["list_json"] if list_row else "") or ""
            jd_text = jd_plaintext(raw) or f"{title} at {company or 'Unknown'}"
        return {
            "intern_job_id": intern_job_id,
            "title": title,
            "company": company,
            "location": location,
            "apply_url": apply_url,
            "detail_url": detail_url,
            "jd_text": jd_text,
            "has_detail": bool(detail),
        }
    finally:
        conn.close()


def new_cart_id() -> str:
    return str(uuid4())
