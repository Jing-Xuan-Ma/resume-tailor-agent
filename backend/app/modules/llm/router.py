"""LLM provider status + runtime preference (UI model picker)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.llm_client import describe_llm_status, set_runtime_preference

router = APIRouter()


class LlmPreferenceRequest(BaseModel):
    provider: str | None = Field(
        default=None,
        description="Provider id (zhipu, xiaomi, google, …). Use 'auto' to clear override.",
    )
    failover: bool | None = Field(
        default=None,
        description="When true, try next configured provider on 503/429/timeout.",
    )


@router.get("/status")
async def llm_status():
    """Configured providers, preferred + Auto failover, last successful usage."""
    return describe_llm_status()


@router.put("/preference")
async def llm_preference(body: LlmPreferenceRequest):
    try:
        prefs = set_runtime_preference(provider=body.provider, failover=body.failover)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return describe_llm_status() | {"ok": True, **prefs}
