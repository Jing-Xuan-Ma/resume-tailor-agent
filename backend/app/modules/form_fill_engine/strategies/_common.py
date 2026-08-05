"""Shared helpers for ATS fill strategies."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.modules.form_fill_engine.field_mapper import map_all_fields
from app.modules.form_fill_engine.schemas import (
    ActionInstruction,
    DOMSnapshot,
    FieldMappingResult,
    InteractiveElement,
)

_SUBMIT_LABELS = (
    "submit application",
    "submit",
    "apply now",
    "send application",
    "确认投递",
    "提交申请",
)

_NEXT_LABELS = (
    "next",
    "continue",
    "save and continue",
    "review",
    "保存并继续",
    "下一步",
    "继续",
)


def mapping_to_instruction(
    m: FieldMappingResult,
    element: InteractiveElement | None = None,
) -> ActionInstruction | None:
    if not m.value_to_fill:
        return None
    etype = (element.element_type if element else "") or ""
    tag = (element.tag if element else "") or ""
    key = m.matched_profile_key or ""

    # Skip if already filled with same value (dynamic re-snapshot loops)
    if element and element.current_value and str(element.current_value).strip() == str(m.value_to_fill).strip():
        if etype != "file":
            return None

    if key in {"resume_path", "cover_letter_path"} or etype == "file":
        path = m.value_to_fill
        exists = bool(path) and Path(path).is_file()
        return ActionInstruction(
            action="upload_file",
            element_index=m.element_index,
            file_path=path,
            reason=(
                f"匹配到 {key}（{m.match_method}，置信度 {m.confidence:.0%}）"
                + ("" if exists else " — 文件不存在，Driver 将降级为手动选择")
            ),
            # Auto-upload when file exists; extension still may degrade to picker
            requires_confirmation=not exists,
        )
    if tag == "select" or etype in {"select", "radio"}:
        return ActionInstruction(
            action="select",
            element_index=m.element_index,
            value=m.value_to_fill,
            reason=f"匹配到 {key}（{m.match_method}，置信度 {m.confidence:.0%}）",
            requires_confirmation=m.confidence < 0.85,
        )
    return ActionInstruction(
        action="fill",
        element_index=m.element_index,
        value=m.value_to_fill,
        reason=f"匹配到 {key}（{m.match_method}，置信度 {m.confidence:.0%}）",
        requires_confirmation=m.confidence < 0.85,
    )


def map_profile_instructions(
    snapshot: DOMSnapshot,
    profile: dict[str, Any],
) -> tuple[list[ActionInstruction], list[FieldMappingResult]]:
    mappings = map_all_fields(snapshot.elements, profile)
    by_idx = {e.index: e for e in snapshot.elements}
    instructions: list[ActionInstruction] = []
    for m in mappings:
        instr = mapping_to_instruction(m, by_idx.get(m.element_index))
        if instr:
            instructions.append(instr)
    return instructions, mappings


def _label_of(el: InteractiveElement) -> str:
    return (el.label or "").strip().lower()


def _is_buttonish(el: InteractiveElement) -> bool:
    tag = (el.tag or "").lower()
    etype = (el.element_type or "").lower()
    return tag in {"button", "a"} or etype in {"button", "submit"}


def find_submit_button(snapshot: DOMSnapshot) -> InteractiveElement | None:
    for el in snapshot.elements:
        if not _is_buttonish(el):
            continue
        low = _label_of(el)
        if any(k == low or k in low for k in _SUBMIT_LABELS):
            # Prefer explicit submit application over bare "submit" on Next-like flows
            return el
    return None


def find_next_or_review_button(snapshot: DOMSnapshot) -> InteractiveElement | None:
    for el in snapshot.elements:
        if not _is_buttonish(el):
            continue
        low = _label_of(el)
        if any(x in low for x in _SUBMIT_LABELS) and "next" not in low:
            continue
        if any(k in low for k in _NEXT_LABELS):
            return el
    return None


def pause_before_submit_instruction(
    reason: str = "表单已填好基本字段，停在人工确认（paused_before_submit）",
) -> ActionInstruction:
    return ActionInstruction(
        action="pause_for_human",
        element_index=None,
        reason=reason,
        requires_confirmation=True,
    )


def build_fill_then_advance_or_pause(
    snapshot: DOMSnapshot,
    profile: dict[str, Any],
    *,
    ats_label: str = "ATS",
) -> list[ActionInstruction]:
    """Fill visible mapped fields; click Next for multi-step; else pause.

    Dynamic forms: Driver re-snapshots after Next+wait and calls Engine again.
    Never auto-clicks final Submit.
    """
    instructions, _ = map_profile_instructions(snapshot, profile)
    next_btn = find_next_or_review_button(snapshot)
    submit_btn = find_submit_button(snapshot)

    fill_actions = [i for i in instructions if i.action in {"fill", "select", "upload_file"}]
    # Advance when there is a Next/Continue and we still have a multi-step path
    # (Next present; prefer advancing before pause so iframe step-2 can appear).
    can_advance = next_btn is not None and (
        submit_btn is None
        or next_btn.index != submit_btn.index
    )
    # If label is Review, still advance into review page then pause on next loop
    if can_advance and fill_actions:
        instructions.append(
            ActionInstruction(
                action="click",
                element_index=next_btn.index,
                reason=f"{ats_label}：当前步已填，点击「{next_btn.label}」进入下一步（动态表单）",
            )
        )
        instructions.append(
            ActionInstruction(
                action="wait",
                value="1500",
                reason="等待动态表单/iframe 内容刷新",
            )
        )
        # Do not pause yet — driver loop continues
        return instructions

    if can_advance and not fill_actions:
        # Nothing to fill on this step — try advancing once, then pause next round
        instructions.append(
            ActionInstruction(
                action="click",
                element_index=next_btn.index,
                reason=f"{ats_label}：本步无可填字段，尝试进入下一步",
            )
        )
        instructions.append(ActionInstruction(action="wait", value="1500", reason="等待下一步渲染"))
        return instructions

    instructions.append(
        pause_before_submit_instruction(
            f"{ats_label}：可见字段已处理。停在人工确认闸门（paused_before_submit）。"
            + (f" iframe帧数={snapshot.frame_count}" if snapshot.frame_count > 1 else "")
        )
    )
    return instructions
