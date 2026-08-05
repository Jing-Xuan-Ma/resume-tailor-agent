"""Workday-oriented fill strategy (profile mapping + pause gate)."""

from __future__ import annotations

from typing import Any

from app.modules.form_fill_engine.schemas import ActionInstruction, DOMSnapshot
from app.modules.form_fill_engine.strategies._common import (
    map_profile_instructions,
    pause_before_submit_instruction,
)


def run_workday_strategy(
    snapshot: DOMSnapshot,
    profile: dict[str, Any],
    job_info: dict[str, Any] | None = None,
) -> list[ActionInstruction]:
    _ = job_info
    instructions, _ = map_profile_instructions(snapshot, profile)
    # Workday multi-step: do not auto-advance past review; always pause for human.
    instructions.append(
        pause_before_submit_instruction(
            "Workday：基本字段已映射。请人工确认后继续；禁止自动 Submit。"
        )
    )
    return instructions
