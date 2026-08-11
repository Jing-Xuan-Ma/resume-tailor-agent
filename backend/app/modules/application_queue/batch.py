"""Batch intern-list → tailor → enqueue → optional parallel fill / confirm-all."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import Any

from app import db
from app.config import settings
from app.modules.application_queue import store
from app.modules.job_discovery.quality import jd_plaintext
from app.modules.resume_workspace.service import workspace_service
from app.modules.safety.audit_log import audit


def _intern_detail_jd(intern_job_id: str) -> dict[str, Any] | None:
    """Build JD payload from intern_list_* tables in the shared SQLite DB."""
    path = getattr(settings, "SQLITE_PATH", None)
    db_path = path or (settings.__dict__.get("sqlite_path"))
    # Prefer the same SQLite file the app already uses.
    from app.db import DB_PATH

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
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
            (detail["detail_url"] if detail else None)
            or f"https://jobright.ai/jobs/info/{intern_job_id}"
        )
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


def resolve_intern_job(intern_job_id: str) -> dict[str, Any]:
    """Map Jobright/intern-list job id → listing + JD text for handoff."""
    intern_job_id = str(intern_job_id or "").strip()
    if not intern_job_id:
        raise ValueError("intern_job_id required")

    listing = db.get_job_listing_by_fingerprint(f"jobright:{intern_job_id}")
    intern = _intern_detail_jd(intern_job_id)

    if listing:
        jd_text = jd_plaintext((listing.get("raw_text") or "").strip())
        meta = listing.get("metadata") if isinstance(listing.get("metadata"), dict) else {}
        title = listing.get("title") or (intern or {}).get("title")
        company = listing.get("company") or (intern or {}).get("company")
        source_url = (
            listing.get("source_url")
            or meta.get("apply_url")
            or (intern or {}).get("apply_url")
            or (intern or {}).get("detail_url")
        )
        if not jd_text and intern:
            jd_text = intern["jd_text"]
        if not jd_text:
            jd_text = f"{title} at {company or 'Unknown'}"
        return {
            "intern_job_id": intern_job_id,
            "listing_id": listing["id"],
            "title": title,
            "company": company,
            "source_url": source_url,
            "jd_text": jd_text,
            "has_detail": bool(intern and intern.get("has_detail")),
        }

    if not intern:
        raise ValueError(f"job not found in intern_list or job_listings: {intern_job_id}")

    return {
        "intern_job_id": intern_job_id,
        "listing_id": None,
        "title": intern.get("title"),
        "company": intern.get("company"),
        "source_url": intern.get("apply_url") or intern.get("detail_url"),
        "jd_text": intern["jd_text"],
        "has_detail": bool(intern.get("has_detail")),
    }


async def _tailor_one(*, user_id: str, resolved: dict[str, Any]) -> dict[str, Any]:
    """Create session → rewrite → confirm → enqueue. Returns queue item or error."""
    job_key = resolved.get("listing_id") or resolved["intern_job_id"]
    out: dict[str, Any] = {
        "intern_job_id": resolved["intern_job_id"],
        "listing_id": resolved.get("listing_id"),
        "company": resolved.get("company"),
        "position": resolved.get("title"),
        "ok": False,
    }
    try:
        session = workspace_service.create_session(
            user_id=user_id,
            jd_text=resolved["jd_text"],
            job_id=str(job_key),
        )
        session_id = session["id"]
        out["session_id"] = session_id
        result = await workspace_service.rewrite(
            user_id=user_id,
            session_id=session_id,
            instruction="Tailor resume for this role from the job description.",
        )
        version_id = result["new_version_id"]
        out["version_id"] = version_id
        confirmed = workspace_service.confirm_version(version_id, user_id)
        if not confirmed or confirmed.get("blocked"):
            out["error"] = (
                (confirmed or {}).get("reason")
                or "confirm blocked by evidence guard — open refine resume for this job"
            )
            out["blocked"] = True
            out["refine_url"] = (
                f"{settings.FRONTEND_BASE_URL}/?view=resume&sessionId={session_id}"
                f"&jobId={job_key}"
            )
            return out

        created = store.enqueue(
            user_id=user_id,
            items=[
                {
                    "job_id": str(job_key),
                    "version_id": version_id,
                    "source_url": resolved.get("source_url"),
                    "company": resolved.get("company"),
                    "position": resolved.get("title"),
                }
            ],
        )
        item = created[0]
        out["ok"] = True
        out["queue_item_id"] = item["id"]
        out["fill_status"] = item["fill_status"]
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return out


async def batch_start(
    *,
    user_id: str,
    intern_job_ids: list[str],
    concurrency: int = 3,
) -> dict[str, Any]:
    ids = [str(x).strip() for x in intern_job_ids if str(x).strip()]
    if not ids:
        raise ValueError("intern_job_ids required")
    concurrency = max(1, min(int(concurrency or 3), 8))

    resolved_list: list[dict[str, Any]] = []
    resolve_errors: list[dict[str, Any]] = []
    for jid in ids:
        try:
            resolved_list.append(resolve_intern_job(jid))
        except Exception as exc:  # noqa: BLE001
            resolve_errors.append({"intern_job_id": jid, "ok": False, "error": str(exc)})

    sem = asyncio.Semaphore(concurrency)

    async def run_one(resolved: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            return await _tailor_one(user_id=user_id, resolved=resolved)

    results = list(await asyncio.gather(*(run_one(r) for r in resolved_list)))
    results.extend(resolve_errors)

    try:
        audit(
            user_id,
            "queue_batch_start",
            {
                "requested": len(ids),
                "ok": sum(1 for r in results if r.get("ok")),
                "failed": sum(1 for r in results if not r.get("ok")),
            },
        )
    except Exception:
        pass

    return {
        "requested": len(ids),
        "concurrency": concurrency,
        "results": results,
        "queue_item_ids": [r["queue_item_id"] for r in results if r.get("queue_item_id")],
        "queue_url": f"{settings.FRONTEND_BASE_URL}/queue",
    }


async def process_many(
    *,
    user_id: str,
    item_ids: list[str] | None = None,
    concurrency: int = 3,
) -> list[dict[str, Any]]:
    """Fill & pause for queued items (all queued for user, or explicit ids)."""
    if item_ids:
        targets = [i for i in (store.get_item(x) for x in item_ids) if i]
    else:
        targets = [
            i
            for i in store.list_items(user_id)
            if i.get("fill_status") in {"queued", "failed"}
        ]
    concurrency = max(1, min(int(concurrency or 3), 5))
    sem = asyncio.Semaphore(concurrency)

    async def one(item: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            return await asyncio.to_thread(
                store.process_item, item_id=item["id"], user_id=user_id
            )

    return list(await asyncio.gather(*(one(i) for i in targets)))


def confirm_many(
    *,
    user_id: str,
    item_ids: list[str] | None = None,
    acknowledge: bool = False,
) -> list[dict[str, Any]]:
    """One-click confirm for all (or selected) items awaiting submit."""
    if not acknowledge:
        raise ValueError("acknowledge=true is required for confirm-all")
    if item_ids:
        targets = [i for i in (store.get_item(x) for x in item_ids) if i]
    else:
        targets = [
            i
            for i in store.list_items(user_id)
            if i.get("awaiting_confirm") or i.get("fill_status") == "awaiting_confirm"
        ]
    out: list[dict[str, Any]] = []
    for item in targets:
        out.append(
            store.confirm_item(item_id=item["id"], user_id=user_id, acknowledge=True)
        )
    try:
        audit(user_id, "queue_confirm_all", {"count": len(out), "ids": [o["id"] for o in out]})
    except Exception:
        pass
    return out
