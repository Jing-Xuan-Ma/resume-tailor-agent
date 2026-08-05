"""Generic DOM-agent fallback for unknown ATS platforms."""

from __future__ import annotations

from typing import Any

from app.modules.form_fill_engine.schemas import ActionInstruction, DOMSnapshot
from app.modules.form_fill_engine.strategies._common import build_fill_then_advance_or_pause


def run_generic_dom_agent_strategy(
    snapshot: DOMSnapshot,
    profile: dict[str, Any],
    job_info: dict[str, Any] | None = None,
) -> list[ActionInstruction]:
    """Rule-first fill + multi-step advance; higher failure rate OK for long-tail ATS."""
    _ = job_info
    return build_fill_then_advance_or_pause(snapshot, profile, ats_label="通用DOM-Agent")
