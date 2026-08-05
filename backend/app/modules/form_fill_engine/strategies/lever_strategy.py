"""Lever-oriented fill strategy."""

from __future__ import annotations

from typing import Any

from app.modules.form_fill_engine.schemas import ActionInstruction, DOMSnapshot
from app.modules.form_fill_engine.strategies._common import build_fill_then_advance_or_pause


def run_lever_strategy(
    snapshot: DOMSnapshot,
    profile: dict[str, Any],
    job_info: dict[str, Any] | None = None,
) -> list[ActionInstruction]:
    _ = job_info
    return build_fill_then_advance_or_pause(snapshot, profile, ats_label="Lever")
