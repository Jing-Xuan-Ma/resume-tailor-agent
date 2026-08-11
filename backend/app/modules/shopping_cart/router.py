"""HTTP API for shopping-cart batch tailor + apply queue (Phase 1–5)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.modules.shopping_cart import service, store
from app.modules.shopping_cart.apply_pipeline import enrich_cart_for_response

router = APIRouter()


class BatchGenerateRequest(BaseModel):
    user_id: str
    intern_job_ids: list[str] = Field(default_factory=list)
    concurrency: int | None = None
    # wait=true blocks until all items finish (scripts/tests). Default progressive.
    wait: bool = False


class PreviewRequest(BaseModel):
    intern_job_ids: list[str] = Field(default_factory=list)


class ConfirmItemRequest(BaseModel):
    user_id: str


class StartApplyRequest(BaseModel):
    user_id: str
    item_ids: list[str] = Field(default_factory=list)
    process_now: bool = True


class ProcessApplyRequest(BaseModel):
    user_id: str
    limit: int = 20


class OpenFilledFormRequest(BaseModel):
    user_id: str
    # How long to keep the headed browser open for review (ms). Default 30 min.
    keep_open_ms: int = 1_800_000


class OpenRegisterRequest(BaseModel):
    user_id: str
    keep_open_ms: int = 1_800_000


class ConfirmRegisteredRequest(BaseModel):
    user_id: str
    continue_apply: bool = True


@router.post("/preview")
async def preview_jobs(request: PreviewRequest):
    """List selected jobs for the cart UI before batch refine."""
    if not request.intern_job_ids:
        raise HTTPException(status_code=400, detail="intern_job_ids required")
    try:
        return service.preview_jobs(intern_job_ids=request.intern_job_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/batch-generate")
async def batch_generate(request: BatchGenerateRequest, background_tasks: BackgroundTasks):
    if not request.intern_job_ids:
        raise HTTPException(status_code=400, detail="intern_job_ids required")
    try:
        if request.wait:
            return await service.batch_generate_and_wait(
                user_id=request.user_id,
                intern_job_ids=request.intern_job_ids,
                concurrency=request.concurrency,
            )
        cart = await service.batch_generate(
            user_id=request.user_id,
            intern_job_ids=request.intern_job_ids,
            concurrency=request.concurrency,
        )
        cart_id = str(cart.get("cart_id") or "")
        background_tasks.add_task(
            service.run_batch_generate_jobs,
            cart_id=cart_id,
            user_id=request.user_id,
        )
        return cart
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/latest")
async def latest_cart(
    user_id: str = Query(...),
    intern_job_ids: str = Query(..., description="Comma-separated intern job ids"),
):
    """Restore the best existing cart for this selection (prefers finished drafts)."""
    ids = [s.strip() for s in (intern_job_ids or "").split(",") if s.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="intern_job_ids required")
    cart = service.find_latest_cart_for_jobs(user_id=user_id, intern_job_ids=ids)
    if not cart:
        raise HTTPException(status_code=404, detail="No matching cart")
    return cart


@router.get("/{cart_id}")
async def get_cart(cart_id: str, user_id: str = Query(...)):
    cart = service.get_cart(cart_id, user_id=user_id)
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")
    return cart


@router.get("/{cart_id}/items/{item_id}")
async def get_item(cart_id: str, item_id: str, user_id: str = Query(...)):
    cart = service.get_cart(cart_id, user_id=user_id)
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")
    for item in cart.get("items") or []:
        if item.get("item_id") == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")


@router.get("/{cart_id}/items/{item_id}/preview.pdf")
async def preview_item_pdf(
    cart_id: str,
    item_id: str,
    user_id: str = Query(...),
    kind: str = Query("resume", description="resume | cover"),
):
    """On-screen PDF preview. Does not persist files; confirm endpoint writes to folder."""
    try:
        data = service.preview_item_pdf(
            cart_id=cart_id,
            item_id=item_id,
            user_id=user_id,
            kind=kind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="{kind}-preview.pdf"',
        },
    )


@router.post("/{cart_id}/items/{item_id}/confirm")
async def confirm_item(cart_id: str, item_id: str, request: ConfirmItemRequest):
    try:
        return service.confirm_item(cart_id=cart_id, item_id=item_id, user_id=request.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{cart_id}/apply/start")
async def start_apply(cart_id: str, request: StartApplyRequest):
    """Queue apply tasks, then run Phase 2–5 (through form fill / ready_to_submit) by default.

    Playwright uses the sync API — must run off the asyncio event loop (to_thread).
    """
    try:
        return await asyncio.to_thread(
            service.start_apply,
            cart_id=cart_id,
            user_id=request.user_id,
            item_ids=request.item_ids or None,
            process_now=bool(request.process_now),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{cart_id}/apply/process")
async def process_apply(cart_id: str, request: ProcessApplyRequest):
    """Phase 2–5: ATS nav → Autofill → account → form fill (pause before Submit)."""
    try:
        return await asyncio.to_thread(
            service.process_apply_queue,
            cart_id=cart_id,
            user_id=request.user_id,
            limit=request.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{cart_id}/items/{item_id}/fill-review")
async def fill_review(cart_id: str, item_id: str, user_id: str = Query(...)):
    """Flip-through payload: profile checklist, filled fields, screenshot meta."""
    try:
        return service.get_fill_review(cart_id=cart_id, item_id=item_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{cart_id}/items/{item_id}/fill-screenshot")
async def fill_screenshot(cart_id: str, item_id: str, user_id: str = Query(...)):
    try:
        data, media = service.get_fill_screenshot_bytes(
            cart_id=cart_id, item_id=item_id, user_id=user_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type=media,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/{cart_id}/items/{item_id}/open-form")
async def open_filled_form(cart_id: str, item_id: str, request: OpenFilledFormRequest):
    """Open the company ATS page where the form was filled (pause before Submit).

    Restores Playwright storage_state when available so the user lands on the
    filled submit page — does not click Submit.
    """
    try:
        return await asyncio.to_thread(
            service.open_item_filled_form,
            cart_id=cart_id,
            item_id=item_id,
            user_id=request.user_id,
            keep_open_ms=int(request.keep_open_ms or 1_800_000),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{cart_id}/items/{item_id}/open-register")
async def open_register(cart_id: str, item_id: str, request: OpenRegisterRequest):
    """Open/focus headed ATS Create Account page when CAPTCHA blocked auto-register."""
    try:
        return await asyncio.to_thread(
            service.open_item_register_page,
            cart_id=cart_id,
            item_id=item_id,
            user_id=request.user_id,
            keep_open_ms=int(request.keep_open_ms or 1_800_000),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{cart_id}/items/{item_id}/confirm-registered")
async def confirm_registered(cart_id: str, item_id: str, request: ConfirmRegisteredRequest):
    """User finished manual ATS registration → continue Phase 5 form fill."""
    try:
        return await asyncio.to_thread(
            service.confirm_item_manual_register,
            cart_id=cart_id,
            item_id=item_id,
            user_id=request.user_id,
            continue_apply=bool(request.continue_apply),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{cart_id}/apply/status")
async def apply_status(cart_id: str, user_id: str = Query(...)):
    meta = store.load_cart_meta(cart_id)
    if not meta or str(meta.get("user_id") or "") != str(user_id):
        raise HTTPException(status_code=404, detail="Cart not found")
    enriched = enrich_cart_for_response(meta)
    return {
        "cart_id": cart_id,
        "apply_summary": enriched.get("apply_summary"),
        "items": [
            {
                "item_id": i.get("item_id"),
                "intern_job_id": i.get("intern_job_id"),
                "company": i.get("company"),
                "position": i.get("position"),
                "status": i.get("status"),
                "apply": i.get("apply"),
            }
            for i in (enriched.get("items") or [])
        ],
    }
