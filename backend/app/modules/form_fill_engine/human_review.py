"""Build human-readable review summaries for Apply / Co-pilot UI."""

from __future__ import annotations

from app.modules.form_fill_engine.schemas import ActionInstruction


def build_summary(instructions: list[ActionInstruction]) -> str:
    if not instructions:
        return "No form actions planned."

    lines: list[str] = ["即将执行的表单操作："]
    fills = [i for i in instructions if i.action in {"fill", "select", "upload_file"}]
    pauses = [i for i in instructions if i.action == "pause_for_human" or i.requires_confirmation]
    submits = [i for i in instructions if i.action == "submit"]

    for i, instr in enumerate(fills, 1):
        flag = " ⚠需确认" if instr.requires_confirmation else ""
        val = instr.value or instr.file_path or ""
        preview = (val[:80] + "…") if len(val) > 80 else val
        lines.append(f"{i}. [{instr.action}] #{instr.element_index}: {preview}{flag}")
        if instr.reason:
            lines.append(f"   — {instr.reason}")

    if pauses:
        lines.append("")
        lines.append(f"需人工确认：{len(pauses)} 项（证据不足或敏感字段）。")
    if submits:
        lines.append("")
        lines.append("⚠️ 含 submit 指令 — 默认仍应 paused_before_submit，勿自动确认投递。")
    elif any(i.action == "pause_for_human" for i in instructions):
        lines.append("")
        lines.append("已停在人工复核闸门（paused_before_submit）。")

    return "\n".join(lines)
