"""Generic DOM-agent fallback for unknown ATS platforms."""

from __future__ import annotations

from typing import Any

from app.modules.form_fill_engine.schemas import ActionInstruction, DOMSnapshot
from app.modules.form_fill_engine.strategies._common import (
    map_profile_instructions,
    pause_before_submit_instruction,
)


def run_generic_dom_agent_strategy(
    snapshot: DOMSnapshot,
    profile: dict[str, Any],
    job_info: dict[str, Any] | None = None,
) -> list[ActionInstruction]:
    """Rule-first fill; optional LLM planning can be layered later.

    Accepts higher failure rate / slower speed for long-tail ATS.
    """
    _ = job_info
    instructions, mappings = map_profile_instructions(snapshot, profile)
    unmatched = sum(1 for m in mappings if m.match_method == "unmatched")
    instructions.append(
        ActionInstruction(
            action="wait",
            reason=f"通用 DOM-Agent：已映射 {len(instructions)} 项，未匹配 {unmatched} 项",
        )
    )
    instructions.append(
        pause_before_submit_instruction(
            "未知 ATS：仅完成高置信度字段填充，其余交还人工（generic_dom_agent）。"
        )
    )
    return instructions
