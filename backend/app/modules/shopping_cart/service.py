"""Concurrent shopping-cart generation: resume + cover letter → MD draft,
PDF preview, confirm → folder.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from app import db
from app.config import settings
from app.modules.resume_core.cover_letter import CoverLetterNode
from app.modules.resume_workspace.service import ResumeWorkspaceService
from app.modules.resume_workspace.template_editor import ResumeTemplateEditor
from app.modules.shopping_cart import store

log = logging.getLogger(__name__)

_cover_letter_node = CoverLetterNode()
_workspace = ResumeWorkspaceService()


def _text_pdf(text: str) -> bytes:
    lines = [ln.rstrip() for ln in (text or "").splitlines()] or [""]
    wrapped = ResumeTemplateEditor._wrap_lines(lines, 92)
    return ResumeTemplateEditor._render_pdf(
        wrapped,
        font_size=10.0,
        leading=13.0,
        top=752,
        page_height=792,
        bottom=36,
    )


def _resume_pdf_bytes(*, user_id: str, full_resume: dict[str, Any]) -> bytes:
    """Render resume PDF from the locked Word master (one-page trim), not Helvetica dump.

    Falling back to plain-text PDF only when master/LibreOffice is unavailable.
    """
    if not isinstance(full_resume, dict) or not full_resume:
        return _text_pdf("")

    try:
        from app.modules.profile.library_service import get_master_inventory
        from app.modules.resume_workspace.master_inject import inject_content
        from app.modules.resume_workspace.master_template import (
            ensure_master_template_bytes,
            ensure_user_has_master_template,
        )
        from app.modules.resume_workspace.one_page_lock import enforce_one_page

        ensure_user_has_master_template(user_id)
        master = ensure_master_template_bytes()
        template = db.get_active_template(user_id) or {}
        if template.get("docx_bytes"):
            master = template["docx_bytes"]
        if not master:
            return ResumeTemplateEditor.generate_pdf_from_resume(full_resume)

        inventory = get_master_inventory(user_id) or {}
        locked = enforce_one_page(
            master_docx=master,
            resume=full_resume,
            master_inventory=inventory,
        )
        if locked.pdf_bytes:
            return locked.pdf_bytes

        docx_bytes = inject_content(master, full_resume, inventory)
        return ResumeTemplateEditor.convert_to_pdf_via_libreoffice(docx_bytes)
    except Exception:
        log.exception("master resume PDF failed; falling back to plain-text PDF")
        return ResumeTemplateEditor.generate_pdf_from_resume(full_resume)


async def _generate_one(
    *,
    user_id: str,
    cart_id: str,
    resolved: dict[str, Any],
    item_id: str | None = None,
) -> dict[str, Any]:
    item_id = item_id or store.new_cart_id()
    company = str(resolved.get("company") or "Unknown")
    position = str(resolved.get("title") or "Unknown")
    t0 = time.perf_counter()
    out: dict[str, Any] = {
        "item_id": item_id,
        "intern_job_id": resolved["intern_job_id"],
        "listing_id": resolved.get("listing_id"),
        "company": company,
        "position": position,
        "location": resolved.get("location") or "",
        "source_url": resolved.get("source_url"),
        "status": "failed",
        "ok": False,
        "elapsed_ms": 0,
    }
    try:
        from app.modules.shopping_cart.fast_path import (
            cover_letter_light,
            cover_letter_template,
            fast_path_enabled,
            rewrite_fast,
        )

        job_key = resolved.get("listing_id") or resolved["intern_job_id"]
        session = _workspace.create_session(
            user_id=user_id,
            jd_text=resolved["jd_text"],
            job_id=str(job_key),
        )
        session_id = session["id"]
        use_fast = fast_path_enabled()
        t_rewrite = time.perf_counter()
        if use_fast:
            result = await rewrite_fast(
                user_id=user_id,
                session_id=session_id,
                instruction="Hybrid tailor from inventory (shopping cart).",
            )
        else:
            result = await _workspace.rewrite(
                user_id=user_id,
                session_id=session_id,
                instruction="Tailor resume for this role from the job description.",
            )
        rewrite_ms = int((time.perf_counter() - t_rewrite) * 1000)
        version_id = result["new_version_id"]
        resume_md = str(result.get("markdown") or "")
        full_resume = result.get("full_resume") or {}

        original = {}
        try:
            from app.modules.profile.library_service import get_master_inventory

            original = get_master_inventory(user_id) or {}
        except Exception:
            original = full_resume

        job_payload = {
            "title": position,
            "company": company,
            "raw_text": resolved["jd_text"],
            "source_url": resolved.get("source_url"),
        }
        t_cover = time.perf_counter()
        if use_fast and bool(getattr(settings, "SHOPPING_CART_COVER_LLM", True)):
            generated = await cover_letter_light(
                job=job_payload,
                tailored_resume=full_resume,
                original_resume=original,
            )
        elif use_fast:
            generated = cover_letter_template(job=job_payload, tailored_resume=full_resume)
        else:
            generated = await _cover_letter_node.run(
                job=job_payload,
                tailored_resume=full_resume,
                original_resume=original,
            )
        cover_ms = int((time.perf_counter() - t_cover) * 1000)
        cover_md = str(generated.get("text") or "")

        files = store.save_item_files(
            cart_id=cart_id,
            company=company,
            position=position,
            resume_md=resume_md,
            cover_letter_md=cover_md,
            meta={
                "item_id": item_id,
                "intern_job_id": resolved["intern_job_id"],
                "listing_id": resolved.get("listing_id"),
                "session_id": session_id,
                "version_id": version_id,
                "status": "ready_md",
                "user_id": user_id,
                "source_url": resolved.get("source_url"),
                "full_resume": full_resume,
                "mode": result.get("mode") or ("fast_path" if use_fast else "full"),
                "timing": {
                    "rewrite_ms": rewrite_ms,
                    "cover_letter_ms": cover_ms,
                    "steps": result.get("timing") or {},
                },
            },
        )
        try:
            db.save_cover_letter(
                user_id=user_id,
                job_id=str(job_key),
                tailored_resume_id=None,
                text=cover_md,
                metadata={
                    "source": "shopping_cart",
                    "cart_id": cart_id,
                    "item_id": item_id,
                    "mode": result.get("mode") or ("fast_path" if use_fast else "full"),
                    "cover_model": generated.get("model"),
                },
            )
        except Exception:
            pass

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        mode = result.get("mode") or ("fast_path" if use_fast else "full")
        log.info(
            "shopping_cart item done mode=%s company=%s position=%s "
            "elapsed_ms=%s rewrite_ms=%s cover_ms=%s",
            mode,
            company,
            position,
            elapsed_ms,
            rewrite_ms,
            cover_ms,
        )
        out.update(
            {
                "ok": True,
                "status": "ready_md",
                "session_id": session_id,
                "version_id": version_id,
                "folder": files["folder"],
                "resume_md": resume_md,
                "cover_letter_md": cover_md,
                "elapsed_ms": elapsed_ms,
                "rewrite_ms": rewrite_ms,
                "cover_letter_ms": cover_ms,
                "mode": mode,
                "step_timing": result.get("timing") or {},
                "cover_source": generated.get("source"),
                "cover_model": generated.get("model"),
            }
        )
        return out
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        out["error"] = str(exc)
        out["status"] = "failed"
        out["elapsed_ms"] = elapsed_ms
        log.warning(
            "shopping_cart item failed company=%s elapsed_ms=%s error=%s",
            company,
            elapsed_ms,
            exc,
        )
        return out


def preview_jobs(*, intern_job_ids: list[str]) -> dict[str, Any]:
    """Resolve selected intern-list jobs for cart display — no tailor yet."""
    ids = [str(x).strip() for x in intern_job_ids if str(x).strip()]
    if not ids:
        raise ValueError("intern_job_ids required")
    items: list[dict[str, Any]] = []
    for jid in ids:
        try:
            r = store.resolve_intern_job(jid)
            items.append(
                {
                    "intern_job_id": r["intern_job_id"],
                    "listing_id": r.get("listing_id"),
                    "company": r.get("company") or "Unknown",
                    "position": r.get("title") or jid,
                    "location": r.get("location") or "",
                    "source_url": r.get("source_url"),
                    "has_detail": bool(r.get("has_detail")),
                    "status": "pending",
                    "ok": True,
                }
            )
        except Exception as exc:  # noqa: BLE001
            items.append(
                {
                    "intern_job_id": jid,
                    "company": "?",
                    "position": jid,
                    "location": "",
                    "status": "unresolved",
                    "ok": False,
                    "error": str(exc),
                }
            )
    return {
        "requested": len(ids),
        "items": items,
        "status": "preview",
    }


_TERMINAL_ITEM_STATUSES = frozenset({"ready_md", "confirmed", "failed"})


def _default_apply_shell(intern_job_id: str) -> dict[str, Any]:
    from app.modules.shopping_cart.apply_pipeline import default_apply_payload

    return default_apply_payload(intern_job_id=intern_job_id)


def _recompute_cart_progress(meta: dict[str, Any]) -> dict[str, Any]:
    items = list(meta.get("items") or [])
    ok_count = sum(1 for i in items if i.get("ok") and i.get("status") in {"ready_md", "confirmed"})
    failed_count = sum(
        1
        for i in items
        if i.get("status") == "failed"
        or (i.get("ok") is False and i.get("status") not in {"generating", "stalled", "pending"})
    )
    generating_count = sum(
        1 for i in items if i.get("status") in {"generating", "stalled", "pending"}
    )
    meta["ok_count"] = ok_count
    meta["failed_count"] = failed_count
    meta["generating_count"] = generating_count
    meta["updated_at"] = store.utcnow()
    if generating_count == 0 and items:
        meta["status"] = "ready"
        per_item = [int(i.get("elapsed_ms") or 0) for i in items if i.get("ok")]
        meta["max_item_ms"] = max(per_item) if per_item else 0
    else:
        meta["status"] = "generating"
    return meta


def _patch_cart_item(cart_id: str, item_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    meta = store.load_cart_meta(cart_id)
    if not meta:
        return None
    items = list(meta.get("items") or [])
    found = False
    for i, item in enumerate(items):
        if str(item.get("item_id")) != str(item_id):
            continue
        items[i] = {**item, **patch}
        found = True
        break
    if not found:
        return None
    meta["items"] = items
    _recompute_cart_progress(meta)
    store.save_cart_meta(cart_id, meta)
    return meta


def _result_to_cart_item(r: dict[str, Any]) -> dict[str, Any]:
    intern_job_id = str(r.get("intern_job_id") or "")
    return {
        "item_id": r.get("item_id"),
        "intern_job_id": intern_job_id,
        "listing_id": r.get("listing_id"),
        "company": r.get("company"),
        "position": r.get("position"),
        "location": r.get("location") or "",
        "source_url": r.get("source_url"),
        "status": r.get("status"),
        "ok": bool(r.get("ok")),
        "error": r.get("error"),
        "session_id": r.get("session_id"),
        "version_id": r.get("version_id"),
        "folder": r.get("folder"),
        "elapsed_ms": r.get("elapsed_ms"),
        "rewrite_ms": r.get("rewrite_ms"),
        "cover_letter_ms": r.get("cover_letter_ms"),
        "step_timing": r.get("step_timing"),
        "cover_model": r.get("cover_model"),
        "cover_source": r.get("cover_source"),
        "apply": r.get("apply") or _default_apply_shell(intern_job_id),
    }


async def batch_generate(
    *,
    user_id: str,
    intern_job_ids: list[str],
    concurrency: int | None = None,
) -> dict[str, Any]:
    """Create cart shell immediately; jobs continue in background via run_batch_generate_jobs.

    Callers (HTTP) should schedule ``run_batch_generate_jobs`` as a BackgroundTask and
    return this payload so the UI can poll and apply ready items before the whole batch finishes.
    """
    ids = [str(x).strip() for x in intern_job_ids if str(x).strip()]
    if not ids:
        raise ValueError("intern_job_ids required")
    default_conc = int(getattr(settings, "SHOPPING_CART_BATCH_CONCURRENCY", 2) or 2)
    concurrency = max(1, min(int(concurrency or default_conc), 8))
    cart_id = store.new_cart_id()

    from app.modules.shopping_cart.apply_pipeline import default_apply_payload

    items: list[dict[str, Any]] = []
    work: list[tuple[str, dict[str, Any]]] = []  # (item_id, resolved)
    for jid in ids:
        item_id = store.new_cart_id()
        try:
            resolved = store.resolve_intern_job(jid)
            items.append(
                {
                    "item_id": item_id,
                    "intern_job_id": resolved["intern_job_id"],
                    "listing_id": resolved.get("listing_id"),
                    "company": resolved.get("company") or "Unknown",
                    "position": resolved.get("title") or jid,
                    "location": resolved.get("location") or "",
                    "source_url": resolved.get("source_url"),
                    "status": "generating",
                    "ok": False,
                    "error": None,
                    "apply": default_apply_payload(intern_job_id=resolved["intern_job_id"]),
                }
            )
            work.append((item_id, resolved))
        except Exception as exc:  # noqa: BLE001
            items.append(
                {
                    "item_id": item_id,
                    "intern_job_id": jid,
                    "company": "?",
                    "position": jid,
                    "location": "",
                    "status": "failed",
                    "ok": False,
                    "error": str(exc),
                    "elapsed_ms": 0,
                    "apply": default_apply_payload(intern_job_id=jid),
                }
            )

    meta = {
        "cart_id": cart_id,
        "user_id": user_id,
        "status": "generating",
        "created_at": store.utcnow(),
        "updated_at": store.utcnow(),
        "concurrency": concurrency,
        "requested": len(ids),
        "ok_count": 0,
        "failed_count": sum(1 for i in items if i.get("status") == "failed"),
        "generating_count": sum(1 for i in items if i.get("status") == "generating"),
        "soft_timeout_s": int(getattr(settings, "SHOPPING_CART_ITEM_SOFT_TIMEOUT_S", 180) or 180),
        "work_queue": [
            {"item_id": item_id, "intern_job_id": resolved["intern_job_id"]}
            for item_id, resolved in work
        ],
        "items": items,
    }
    _recompute_cart_progress(meta)
    store.save_cart_meta(cart_id, meta)

    # Stash resolved JD payloads for the background runner (avoid re-resolve drift).
    stash = {
        item_id: {
            "intern_job_id": resolved["intern_job_id"],
            "listing_id": resolved.get("listing_id"),
            "title": resolved.get("title"),
            "company": resolved.get("company"),
            "location": resolved.get("location"),
            "source_url": resolved.get("source_url"),
            "jd_text": resolved.get("jd_text"),
            "has_detail": resolved.get("has_detail"),
        }
        for item_id, resolved in work
    }
    stash_path = store.cart_dir(cart_id) / "work_stash.json"
    stash_path.write_text(json.dumps(stash, ensure_ascii=False), encoding="utf-8")

    return get_cart(cart_id, user_id=user_id) or {
        "cart_id": cart_id,
        "status": "generating",
        "items": items,
        "requested": len(ids),
        "ok_count": 0,
        "failed_count": meta["failed_count"],
        "concurrency": concurrency,
    }


async def run_batch_generate_jobs(*, cart_id: str, user_id: str) -> None:
    """Background worker: generate each item, patch cart as soon as each finishes."""
    import json as _json

    meta = store.load_cart_meta(cart_id)
    if not meta:
        log.warning("run_batch_generate_jobs: cart missing %s", cart_id)
        return
    if str(meta.get("user_id")) != str(user_id):
        log.warning("run_batch_generate_jobs: user mismatch cart=%s", cart_id)
        return

    concurrency = max(1, min(int(meta.get("concurrency") or 2), 8))
    soft_timeout_s = max(30, int(meta.get("soft_timeout_s") or 180))
    stash_path = store.cart_dir(cart_id) / "work_stash.json"
    if not stash_path.exists():
        log.warning("run_batch_generate_jobs: no stash for %s", cart_id)
        meta["status"] = "ready"
        store.save_cart_meta(cart_id, meta)
        return
    stash: dict[str, Any] = _json.loads(stash_path.read_text(encoding="utf-8"))
    work_ids = [
        str(i.get("item_id"))
        for i in (meta.get("items") or [])
        if i.get("status") == "generating" and str(i.get("item_id") or "") in stash
    ]
    if not work_ids:
        _recompute_cart_progress(meta)
        store.save_cart_meta(cart_id, meta)
        return

    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    batch_t0 = time.perf_counter()

    async def run_one(item_id: str) -> None:
        resolved = stash[item_id]
        async with sem:
            task = asyncio.create_task(
                _generate_one(
                    user_id=user_id,
                    cart_id=cart_id,
                    resolved=resolved,
                    item_id=item_id,
                )
            )

            async def soft_timeout_watch() -> None:
                await asyncio.sleep(soft_timeout_s)
                if task.done():
                    return
                async with lock:
                    _patch_cart_item(
                        cart_id,
                        item_id,
                        {
                            "status": "stalled",
                            "ok": False,
                            "error": (
                                f"Still generating after {soft_timeout_s}s — "
                                "other ready items can be reviewed/applied now"
                            ),
                        },
                    )
                    log.warning(
                        "shopping_cart item soft-timeout cart=%s item=%s company=%s",
                        cart_id,
                        item_id,
                        resolved.get("company"),
                    )

            watchdog = asyncio.create_task(soft_timeout_watch())
            try:
                result = await task
            except Exception as exc:  # noqa: BLE001
                result = {
                    "item_id": item_id,
                    "intern_job_id": resolved.get("intern_job_id"),
                    "company": resolved.get("company"),
                    "position": resolved.get("title"),
                    "location": resolved.get("location") or "",
                    "source_url": resolved.get("source_url"),
                    "ok": False,
                    "status": "failed",
                    "error": str(exc),
                    "elapsed_ms": 0,
                }
            finally:
                watchdog.cancel()
                try:
                    await watchdog
                except asyncio.CancelledError:
                    pass

            async with lock:
                _patch_cart_item(cart_id, item_id, _result_to_cart_item(result))
                log.info(
                    "shopping_cart progressive item cart=%s item=%s ok=%s status=%s elapsed_ms=%s",
                    cart_id,
                    item_id,
                    result.get("ok"),
                    result.get("status"),
                    result.get("elapsed_ms"),
                )

    await asyncio.gather(*(run_one(iid) for iid in work_ids))

    meta = store.load_cart_meta(cart_id) or meta
    meta["elapsed_ms"] = int((time.perf_counter() - batch_t0) * 1000)
    _recompute_cart_progress(meta)
    store.save_cart_meta(cart_id, meta)
    try:
        stash_path.unlink(missing_ok=True)
    except Exception:
        pass
    log.info(
        "shopping_cart batch background done cart_id=%s ok=%s failed=%s wall_ms=%s",
        cart_id,
        meta.get("ok_count"),
        meta.get("failed_count"),
        meta.get("elapsed_ms"),
    )


# Keep sync helper for scripts/tests that want to wait for full completion.
async def batch_generate_and_wait(
    *,
    user_id: str,
    intern_job_ids: list[str],
    concurrency: int | None = None,
) -> dict[str, Any]:
    cart = await batch_generate(
        user_id=user_id,
        intern_job_ids=intern_job_ids,
        concurrency=concurrency,
    )
    cart_id = str(cart.get("cart_id") or "")
    await run_batch_generate_jobs(cart_id=cart_id, user_id=user_id)
    return get_cart(cart_id, user_id=user_id) or cart


async def batch_generate_legacy_wait(
    *,
    user_id: str,
    intern_job_ids: list[str],
    concurrency: int = 4,
) -> dict[str, Any]:
    """Deprecated alias."""
    return await batch_generate_and_wait(
        user_id=user_id,
        intern_job_ids=intern_job_ids,
        concurrency=concurrency,
    )


def get_cart(cart_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    from app.modules.shopping_cart.apply_pipeline import enrich_cart_for_response

    meta = store.load_cart_meta(cart_id)
    if not meta:
        return None
    if user_id and str(meta.get("user_id")) != str(user_id):
        return None
    items = []
    for item in meta.get("items") or []:
        item_id = item.get("item_id")
        if item_id and item.get("ok"):
            full = store.read_item(cart_id, item_id)
            items.append(full or item)
        else:
            items.append(item)
    return enrich_cart_for_response({**meta, "items": items})


def start_apply(
    *,
    cart_id: str,
    user_id: str,
    item_ids: list[str] | None = None,
    process_now: bool = True,
) -> dict[str, Any]:
    from app.modules.shopping_cart.apply_pipeline import start_apply_batch
    from app.modules.shopping_cart.apply_worker import process_cart_queue

    queued = start_apply_batch(cart_id=cart_id, user_id=user_id, item_ids=item_ids)
    if not process_now or not queued.get("queued_count"):
        return {
            **queued,
            "phase": 5,
            "processed_count": 0,
            "message": queued.get("message")
            or "Apply tasks queued. Call apply/process to run Phase 2–5.",
        }

    processed = process_cart_queue(cart_id=cart_id, user_id=user_id)
    return {
        **queued,
        **processed,
        "phase": processed.get("phase") or 5,
        "queued_count": queued.get("queued_count"),
        "apply_summary": processed.get("apply_summary") or queued.get("apply_summary"),
        "message": (
            f"Queued {queued.get('queued_count', 0)}; "
            f"ok {processed.get('ok_count', 0)}, "
            f"failed {processed.get('failed_count', 0)} "
            f"(through Phase {processed.get('phase') or 5}: form fill → ready_to_submit)."
        ),
    }


def process_apply_queue(*, cart_id: str, user_id: str, limit: int = 20) -> dict[str, Any]:
    from app.modules.shopping_cart.apply_worker import process_cart_queue

    return process_cart_queue(cart_id=cart_id, user_id=user_id, limit=limit)


def get_fill_review(*, cart_id: str, item_id: str, user_id: str) -> dict[str, Any]:
    from app.modules.shopping_cart.apply_worker import get_fill_review as _get

    return _get(cart_id=cart_id, item_id=item_id, user_id=user_id)


def open_item_filled_form(
    *, cart_id: str, item_id: str, user_id: str, keep_open_ms: int = 1_800_000
) -> dict[str, Any]:
    from app.modules.shopping_cart.apply_worker import open_item_filled_form as _open

    return _open(cart_id=cart_id, item_id=item_id, user_id=user_id, keep_open_ms=keep_open_ms)


def get_fill_screenshot_bytes(*, cart_id: str, item_id: str, user_id: str) -> tuple[bytes, str]:
    """Return (bytes, media_type) for Phase 5 screenshot under this cart only."""
    review = get_fill_review(cart_id=cart_id, item_id=item_id, user_id=user_id)
    path = (review.get("review") or {}).get("screenshot_path")
    if not path:
        # fall back to apply state
        meta = store.load_cart_meta(cart_id)
        if not meta:
            raise ValueError("Cart not found")
        for item in meta.get("items") or []:
            if item.get("item_id") == item_id:
                apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
                path = apply.get("screenshot_path")
                break
    if not path:
        raise ValueError("Screenshot not found")
    p = Path(path).resolve()
    root = store.cart_dir(cart_id).resolve()
    if root not in p.parents and p != root:
        raise ValueError("Screenshot path outside cart")
    if not p.is_file():
        raise ValueError("Screenshot file missing")
    suffix = p.suffix.lower()
    media = (
        "image/png"
        if suffix == ".png"
        else "image/jpeg"
        if suffix in {".jpg", ".jpeg"}
        else "application/octet-stream"
    )
    return p.read_bytes(), media


def confirm_item(*, cart_id: str, item_id: str, user_id: str) -> dict[str, Any]:
    meta = store.load_cart_meta(cart_id)
    if not meta or str(meta.get("user_id")) != str(user_id):
        raise ValueError("Cart not found")
    full = store.read_item(cart_id, item_id)
    if not full or not full.get("ok"):
        raise ValueError("Cart item not ready")
    item_meta = full.get("item_meta") or {}
    full_resume = item_meta.get("full_resume") or {}
    company = full.get("company") or "Unknown"
    position = full.get("position") or "Unknown"

    resume_pdf = _resume_pdf_bytes(user_id=user_id, full_resume=full_resume)
    cover_pdf = _text_pdf(full.get("cover_letter_md") or "")
    written = store.write_pdfs(
        cart_id=cart_id,
        company=company,
        position=position,
        resume_pdf=resume_pdf,
        cover_letter_pdf=cover_pdf,
        meta=item_meta,
    )

    # Update cart index status
    for item in meta.get("items") or []:
        if item.get("item_id") == item_id:
            item["status"] = "confirmed"
            item["formats"] = {"resume": "pdf", "cover_letter": "pdf"}
            break
    meta["updated_at"] = store.utcnow()
    store.save_cart_meta(cart_id, meta)

    return {
        "cart_id": cart_id,
        "item_id": item_id,
        "status": "confirmed",
        "company": company,
        "position": position,
        "resume_pdf_path": written["resume_pdf_path"],
        "cover_letter_pdf_path": written["cover_letter_pdf_path"],
        "folder": str(store.item_dir(cart_id, company, position)),
    }


def preview_item_pdf(
    *,
    cart_id: str,
    item_id: str,
    user_id: str,
    kind: str = "resume",
) -> bytes:
    """Render PDF for on-screen preview only — does not write confirmed files.

    If the item was already confirmed and the PDF exists on disk, serve that file
    so preview matches what was saved.
    """
    meta = store.load_cart_meta(cart_id)
    if not meta or str(meta.get("user_id")) != str(user_id):
        raise ValueError("Cart not found")
    full = store.read_item(cart_id, item_id)
    if not full or not full.get("ok"):
        raise ValueError("Cart item not ready")

    company = str(full.get("company") or "Unknown")
    position = str(full.get("position") or "Unknown")
    folder = store.item_dir(cart_id, company, position)
    kind_key = (kind or "resume").strip().lower()
    if kind_key in {"cover", "cover_letter", "cl"}:
        disk = folder / "cover_letter.pdf"
        if disk.is_file():
            return disk.read_bytes()
        return _text_pdf(str(full.get("cover_letter_md") or ""))

    disk = folder / "resume.pdf"
    if disk.is_file():
        return disk.read_bytes()
    item_meta = full.get("item_meta") or {}
    full_resume = item_meta.get("full_resume") or {}
    if isinstance(full_resume, dict) and full_resume:
        return _resume_pdf_bytes(user_id=user_id, full_resume=full_resume)
    return _text_pdf(str(full.get("resume_md") or ""))
