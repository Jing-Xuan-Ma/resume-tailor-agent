"""HTTP API for per-job application queue (Phase 4)."""

from fastapi import APIRouter, HTTPException, Query

from app.modules.application_queue import store
from app.modules.application_queue.schemas import (
    QueueAckRequest,
    QueueEnqueueRequest,
    QueueItemResponse,
    QueueListResponse,
)

router = APIRouter()


def _to_resp(row: dict) -> QueueItemResponse:
    return QueueItemResponse(
        id=row["id"],
        user_id=row["user_id"],
        job_id=row.get("job_id"),
        version_id=row.get("version_id"),
        source_url=row.get("source_url"),
        company=row.get("company"),
        position=row.get("position"),
        fill_status=str(row.get("fill_status") or "queued"),
        awaiting_confirm=bool(row.get("awaiting_confirm")),
        apply_id=row.get("apply_id"),
        submitted_at=row.get("submitted_at"),
        skipped_at=row.get("skipped_at"),
        error=row.get("error"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


@router.post("/enqueue", response_model=QueueListResponse)
async def enqueue(request: QueueEnqueueRequest):
    if not request.items:
        raise HTTPException(status_code=400, detail="items required")
    created = store.enqueue(
        user_id=request.user_id,
        items=[i.model_dump() for i in request.items],
    )
    return QueueListResponse(items=[_to_resp(c) for c in created])


@router.get("", response_model=QueueListResponse)
async def list_queue(user_id: str = Query(...)):
    items = store.list_items(user_id)
    return QueueListResponse(items=[_to_resp(i) for i in items])


@router.post("/{item_id}/process", response_model=QueueItemResponse)
async def process_queue_item(item_id: str, request: QueueAckRequest):
    """Fill ATS form and pause before Submit for this queue row only."""
    try:
        item = store.process_item(item_id=item_id, user_id=request.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_resp(item)


@router.post("/{item_id}/confirm-submit", response_model=QueueItemResponse)
async def confirm_queue_item(item_id: str, request: QueueAckRequest):
    """User confirms Submit for this job only (audit; no live click)."""
    try:
        item = store.confirm_item(
            item_id=item_id,
            user_id=request.user_id,
            acknowledge=bool(request.acknowledge),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_resp(item)


@router.post("/{item_id}/skip", response_model=QueueItemResponse)
async def skip_queue_item(item_id: str, request: QueueAckRequest):
    try:
        item = store.skip_item(item_id=item_id, user_id=request.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_resp(item)
