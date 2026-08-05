"""Greenhouse-oriented fill strategy."""

from __future__ import annotations

from typing import Any

from app.modules.form_fill_engine.schemas import ActionInstruction, DOMSnapshot
from app.modules.form_fill_engine.strategies._common import (
    map_profile_instructions,
    pause_before_submit_instruction,
)


def run_greenhouse_strategy(
    snapshot: DOMSnapshot,
    profile: dict[str, Any],
    job_info: dict[str, Any] | None = None,
) -> list[ActionInstruction]:
    _ = job_info
    instructions, _ = map_profile_instructions(snapshot, profile)
    for instr in instructions:
        if instr.action == "upload_file":
            instr.requires_confirmation = True
            instr.reason = (instr.reason or "") + " | Greenhouse 简历上传建议人工确认路径"
    instructions.append(
        pause_before_submit_instruction(
            "Greenhouse：字段已映射。文件上传若失败请手动选择；停在 paused_before_submit。"
        )
    )
    return instructions
