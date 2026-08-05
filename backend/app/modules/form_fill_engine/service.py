"""Decision Engine orchestration — pure logic, no browser I/O."""

from __future__ import annotations

import logging
from typing import Any

from app.modules.form_fill_engine.ats_detector import detect_ats
from app.modules.form_fill_engine.field_mapper import map_all_fields
from app.modules.form_fill_engine.human_review import build_summary
from app.modules.form_fill_engine.schemas import (
    ActionInstruction,
    ATSType,
    DOMSnapshot,
    EngineResponse,
    EngineStepRequest,
)
from app.modules.form_fill_engine.screener_answerer import (
    answer_screener_question,
    is_likely_screener,
)
from app.modules.form_fill_engine.strategies.generic_dom_agent import run_generic_dom_agent_strategy
from app.modules.form_fill_engine.strategies.greenhouse_strategy import run_greenhouse_strategy
from app.modules.form_fill_engine.strategies.lever_strategy import run_lever_strategy
from app.modules.form_fill_engine.strategies.workday_strategy import run_workday_strategy

log = logging.getLogger(__name__)

_STRATEGY = {
    ATSType.WORKDAY: run_workday_strategy,
    ATSType.GREENHOUSE: run_greenhouse_strategy,
    ATSType.LEVER: run_lever_strategy,
}


def _mock_response(request: EngineStepRequest) -> EngineResponse:
    snap = request.dom_snapshot
    instructions: list[ActionInstruction] = []
    for el in snap.elements[:5]:
        if el.tag == "button":
            continue
        if el.label and "email" in el.label.lower():
            instructions.append(
                ActionInstruction(
                    action="fill",
                    element_index=el.index,
                    value=str(request.profile.get("email") or "mock@example.com"),
                    reason="mock: email field",
                )
            )
    instructions.append(
        ActionInstruction(
            action="pause_for_human",
            reason="mock engine — awaiting human review",
            requires_confirmation=True,
        )
    )
    return EngineResponse(
        instructions=instructions,
        stage="awaiting_human_review",
        summary_for_human=build_summary(instructions),
        ats=detect_ats(snap.url, snap),
        meta={"mock": True},
    )


def run_known_ats_strategy(
    ats_type: ATSType,
    snapshot: DOMSnapshot,
    profile: dict[str, Any],
    job_info: dict[str, Any] | None = None,
) -> list[ActionInstruction]:
    fn = _STRATEGY.get(ats_type)
    if fn is None:
        return run_generic_dom_agent_strategy(snapshot, profile, job_info)
    return fn(snapshot, profile, job_info)


async def plan_step(request: EngineStepRequest) -> EngineResponse:
    if request.mock:
        return _mock_response(request)

    snapshot = request.dom_snapshot
    ats_result = detect_ats(snapshot.url, snapshot)

    if ats_result.confidence > 0.8 and ats_result.ats_type in _STRATEGY:
        instructions = run_known_ats_strategy(
            ats_result.ats_type, snapshot, request.profile, request.job_info
        )
    else:
        instructions = run_generic_dom_agent_strategy(
            snapshot, request.profile, request.job_info
        )

    # Screener pass: unmatched likely-question fields
    mappings = map_all_fields(snapshot.elements, request.profile)
    mapped_idx = {
        m.element_index: m.matched_profile_key
        for m in mappings
        if m.matched_profile_key and m.value_to_fill
    }
    filled_indices = {
        i.element_index
        for i in instructions
        if i.element_index is not None and i.action in {"fill", "select", "upload_file"}
    }

    for el in snapshot.elements:
        if el.index in filled_indices:
            continue
        if not is_likely_screener(el, mapped_idx.get(el.index)):
            continue
        answer = await answer_screener_question(
            el.label,
            request.resume_facts or request.profile,
            element_index=el.index,
        )
        if not answer.generated_answer:
            instructions.append(
                ActionInstruction(
                    action="pause_for_human",
                    element_index=el.index,
                    reason=f"筛选题无法安全作答，需人工：{el.label[:80]}",
                    requires_confirmation=True,
                )
            )
            continue
        action = "select" if el.tag == "select" or (el.options) else "fill"
        instructions.append(
            ActionInstruction(
                action=action,
                element_index=el.index,
                value=answer.generated_answer,
                reason=(
                    f"AI生成回答，证据校验"
                    f"{'通过' if answer.evidence_check_passed else '未通过，需人工确认'}"
                ),
                requires_confirmation=answer.needs_human_review,
            )
        )

    # Data-safety: never emit auto-submit unless explicitly allowed; even then confirm.
    advancing = any(
        i.action == "click"
        and i.element_index is not None
        and any(
            k in ((snapshot.elements[i.element_index].label if 0 <= i.element_index < len(snapshot.elements) else "") or "").lower()
            for k in ("next", "continue", "review", "下一步", "继续")
        )
        for i in instructions
    )
    if request.allow_submit:
        instructions.append(
            ActionInstruction(
                action="submit",
                reason="allow_submit=true — Driver 仍须人工确认后执行",
                requires_confirmation=True,
            )
        )
    elif not advancing and not any(i.action == "pause_for_human" for i in instructions):
        instructions.append(
            ActionInstruction(
                action="pause_for_human",
                reason="paused_before_submit — 默认禁止真实投递",
                requires_confirmation=True,
            )
        )

    needs_review = any(i.requires_confirmation or i.action == "pause_for_human" for i in instructions)
    if needs_review:
        stage: str = "awaiting_human_review"
    elif advancing:
        stage = "filling"
    elif any(i.action == "submit" for i in instructions):
        stage = "ready_to_submit"
    else:
        stage = "filling"

    # Drop trailing duplicate pauses
    seen_pause = False
    deduped: list[ActionInstruction] = []
    for instr in instructions:
        if instr.action == "pause_for_human":
            if seen_pause:
                continue
            seen_pause = True
        deduped.append(instr)

    return EngineResponse(
        instructions=deduped,
        stage=stage,  # type: ignore[arg-type]
        summary_for_human=build_summary(deduped),
        ats=ats_result,
        meta={
            "element_count": len(snapshot.elements),
            "allow_submit": request.allow_submit,
        },
    )
