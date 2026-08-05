"""Tool-calling agent loop for Tailor workspace chat.

Uses LangChain bind_tools when the provider supports it; falls back to a JSON
tool protocol so Zhipu / OpenAI-compat providers still work.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings
from app.core.llm_client import get_chat_openai
from app.modules.resume_workspace.agent_tools import (
    AgentToolContext,
    build_langchain_tools,
    dispatch_tool,
)
from app.modules.resume_workspace.constitution import (
    MASTER_TEMPLATE_LABEL,
    constitution_system_block,
)

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6


def _system_prompt() -> str:
    return (
        constitution_system_block()
        + "\nYou are Resume Agent for the Tailor workspace.\n"
        "You have tools. Use them instead of guessing Profile contents.\n"
        "Goals:\n"
        "1) Save any personal facts the user states into Profile "
        "(phone, email, location/住址/address, visa, custom_fields, new experience rows).\n"
        "2) Match Profile evidence to the current JD via match_profile_to_jd.\n"
        "3) When the user wants the resume changed, call project_resume "
        f"(locked master template {MASTER_TEMPLATE_LABEL}; content-only; one page).\n"
        "Rules: never fabricate employers/metrics/skills; map 住址/地址/address → apply.location; "
        "use custom_fields for extra keys; do not claim a rewrite unless project_resume succeeded.\n"
        "Be concise. After tools finish, reply to the user in plain language."
    )


def _parse_json_tool_payload(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    # fenced json
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()
    if not raw.startswith("{"):
        # try first brace object
        m2 = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m2:
            return None
        raw = m2.group(0)
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _tool_calls_from_json(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize several JSON shapes into [{name, args, id}]."""
    out: list[dict[str, Any]] = []
    if data.get("action") == "final":
        return []
    if data.get("action") == "tool" and data.get("name"):
        out.append(
            {
                "name": str(data["name"]),
                "args": data.get("args") or data.get("arguments") or {},
                "id": "json_0",
            }
        )
        return out
    if data.get("tool") and isinstance(data.get("tool"), str):
        out.append(
            {
                "name": str(data["tool"]),
                "args": data.get("args") or {},
                "id": "json_0",
            }
        )
        return out
    calls = data.get("tool_calls")
    if isinstance(calls, list):
        for i, c in enumerate(calls):
            if not isinstance(c, dict):
                continue
            name = c.get("name") or c.get("tool")
            if not name:
                continue
            args = c.get("args") or c.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            out.append({"name": str(name), "args": args if isinstance(args, dict) else {}, "id": f"json_{i}"})
    return out


async def _run_one_tool(ctx: AgentToolContext, name: str, args: dict[str, Any]) -> str:
    result = dispatch_tool(ctx, name, args)
    if hasattr(result, "__await__"):
        result = await result  # type: ignore[misc]
    return str(result)


async def run_tool_agent(
    *,
    ctx: AgentToolContext,
    message: str,
    chat_history: list[dict] | None = None,
) -> tuple[str, AgentToolContext]:
    """Run up to MAX_TOOL_ROUNDS of tool calling; return final assistant text."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    tools = build_langchain_tools(ctx)
    tool_by_name = {t.name: t for t in tools}

    llm = get_chat_openai(
        model=settings.DEFAULT_PARSER_MODEL or settings.DEFAULT_TAILOR_MODEL,
        temperature=0.2,
        max_tokens=1200,
    )

    history_msgs: list[Any] = []
    for item in (chat_history or [])[-8]:
        role = str(item.get("role") or "")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            history_msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            history_msgs.append(AIMessage(content=content))

    messages: list[Any] = [
        SystemMessage(content=_system_prompt()),
        *history_msgs,
        HumanMessage(content=message),
    ]

    # Prefer native tool calling
    use_native = True
    try:
        bound = llm.bind_tools(tools)
    except Exception as exc:
        log.warning("bind_tools unavailable (%s); using JSON tool protocol", exc)
        use_native = False
        bound = llm
        messages[0] = SystemMessage(
            content=_system_prompt()
            + "\nWhen you need a tool, reply ONLY with JSON: "
            '{"tool_calls":[{"name":"get_profile","args":{}}]} '
            "or multiple tools in tool_calls. When finished, reply with plain text only "
            '(or {"action":"final","message":"..."}).'
        )

    final_text = ""
    for _round in range(MAX_TOOL_ROUNDS):
        try:
            response = await bound.ainvoke(messages)
        except Exception as exc:
            log.warning("agent LLM round failed: %s", exc)
            if not final_text:
                raise
            break

        messages.append(response)
        native_calls = list(getattr(response, "tool_calls", None) or [])
        content = str(getattr(response, "content", "") or "").strip()

        calls: list[dict[str, Any]] = []
        if native_calls:
            for i, tc in enumerate(native_calls):
                if isinstance(tc, dict):
                    calls.append(
                        {
                            "name": tc.get("name"),
                            "args": tc.get("args") or {},
                            "id": tc.get("id") or f"call_{i}",
                        }
                    )
                else:
                    calls.append(
                        {
                            "name": getattr(tc, "name", None),
                            "args": getattr(tc, "args", {}) or {},
                            "id": getattr(tc, "id", None) or f"call_{i}",
                        }
                    )
        elif not use_native or (content.startswith("{") and "tool" in content.lower()):
            data = _parse_json_tool_payload(content)
            if data:
                if data.get("action") == "final" and data.get("message"):
                    final_text = str(data["message"]).strip()
                    break
                calls = _tool_calls_from_json(data)

        if not calls:
            final_text = content
            # If model returned empty content but somehow succeeded
            if not final_text and ctx.state.profile_updated:
                final_text = (
                    "Saved to Profile: "
                    + ", ".join(ctx.state.changed_apply + ctx.state.changed_inventory)[:120]
                    + ". Open the Profile tab to review."
                )
            elif not final_text and ctx.state.did_rewrite:
                final_text = (
                    f"Updated to v{ctx.state.version_index}. Check the PDF preview on the right."
                )
            break

        for call in calls:
            name = str(call.get("name") or "")
            args = call.get("args") if isinstance(call.get("args"), dict) else {}
            call_id = str(call.get("id") or name)
            try:
                if name in tool_by_name and hasattr(tool_by_name[name], "ainvoke"):
                    # StructuredTool.ainvoke accepts dict input
                    try:
                        tool_result = await tool_by_name[name].ainvoke(args or {})
                    except Exception:
                        tool_result = await _run_one_tool(ctx, name, args or {})
                else:
                    tool_result = await _run_one_tool(ctx, name, args or {})
            except Exception as exc:
                tool_result = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

            messages.append(
                ToolMessage(content=str(tool_result), tool_call_id=call_id, name=name)
            )

    if not final_text:
        if ctx.state.profile_updated:
            labels = ctx.state.changed_apply + ctx.state.changed_inventory
            final_text = (
                "Saved to Profile: " + ", ".join(labels[:8]) + ". Open Profile to review."
            )
        elif ctx.state.did_rewrite:
            final_text = (
                f"Updated to v{ctx.state.version_index} on your locked master template. "
                "Check the PDF preview on the right."
            )
        else:
            final_text = (
                "I can save Profile facts, match your inventory to this JD, "
                "or project a one-page resume — tell me what you want."
            )

    return final_text, ctx
