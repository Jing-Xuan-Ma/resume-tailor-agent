"""Lever-oriented fill strategy."""

from __future__ import annotations

from typing import Any

from app.modules.form_fill_engine.schemas import ActionInstruction, DOMSnapshot
from app.modules.form_fill_engine.strategies._common import (
    map_profile_instructions,
    pause_before_submit_instruction,
)


def run_lever_strategy(
    snapshot: DOMSnapshot,
    profile: dict[str, Any],
    job_info: dict[str, Any] | None = None,
) -> list[ActionInstruction]:
    _ = job_info
    instructions, _ = map_profile_instructions(snapshot, profile)
    for instr in instructions:
        if instr.action == "upload_file":
            instr.requires_confirmation = True
            instr.reason = (instr.reason or "") + " | Lever 文件上传默认手动兜底"
    instructions.append(
        pause_before_submit_instruction(
            "Lever：字段已映射。停在人工确认闸门（paused_before_submit）。"
        )
    )
    return instructions
