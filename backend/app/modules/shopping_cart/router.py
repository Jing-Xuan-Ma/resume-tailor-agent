"""HTTP API for shopping-cart batch tailor + PDF confirm. Browser apply is Agent/MCP."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.modules.shopping_cart import service

router = APIRouter()

_APPLY_MOVED = (
    "Browser apply moved to Agent chat. Confirm the PDF here, then use "
    ".agents/skills/jobright-apply with ghost-driver-mcp. Never auto-click Submit."
)


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
    raise HTTPException(status_code=410, detail=_APPLY_MOVED)


@router.post("/{cart_id}/apply/process")
async def process_apply(cart_id: str, request: ProcessApplyRequest):
    raise HTTPException(status_code=410, detail=_APPLY_MOVED)


@router.get("/{cart_id}/items/{item_id}/fill-review")
async def fill_review(cart_id: str, item_id: str, user_id: str = Query(...)):
    raise HTTPException(status_code=410, detail=_APPLY_MOVED)


@router.get("/{cart_id}/items/{item_id}/fill-screenshot")
async def fill_screenshot(cart_id: str, item_id: str, user_id: str = Query(...)):
    raise HTTPException(status_code=410, detail=_APPLY_MOVED)


@router.post("/{cart_id}/items/{item_id}/open-form")
async def open_filled_form(cart_id: str, item_id: str, request: OpenFilledFormRequest):
    raise HTTPException(status_code=410, detail=_APPLY_MOVED)


@router.post("/{cart_id}/items/{item_id}/open-register")
async def open_register(cart_id: str, item_id: str, request: OpenRegisterRequest):
    raise HTTPException(status_code=410, detail=_APPLY_MOVED)


@router.post("/{cart_id}/items/{item_id}/confirm-registered")
async def confirm_registered(cart_id: str, item_id: str, request: ConfirmRegisteredRequest):
    raise HTTPException(status_code=410, detail=_APPLY_MOVED)


@router.get("/{cart_id}/apply/status")
async def apply_status(cart_id: str, user_id: str = Query(...)):
    raise HTTPException(status_code=410, detail=_APPLY_MOVED)
