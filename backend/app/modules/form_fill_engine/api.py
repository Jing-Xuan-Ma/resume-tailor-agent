"""FastAPI routes for the shared Form-Fill Decision Engine."""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.form_fill_engine.schemas import EngineResponse, EngineStepRequest
from app.modules.form_fill_engine.service import plan_step

router = APIRouter()


@router.post("/step", response_model=EngineResponse)
async def engine_step(request: EngineStepRequest) -> EngineResponse:
    """Drivers POST DOMSnapshot + profile; receive ActionInstruction batch."""
    return await plan_step(request)


@router.get("/health")
async def engine_health() -> dict:
    return {"status": "ok", "service": "form_fill_engine"}
