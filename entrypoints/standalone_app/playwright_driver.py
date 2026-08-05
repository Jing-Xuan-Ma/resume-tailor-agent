"""Playwright Driver A — capture DOMSnapshot + execute ActionInstructions.

Does not contain decision logic; always calls the Engine HTTP API (or in-process).
"""

from __future__ import annotations

import base64
import logging
import sys
from pathlib import Path
from typing import Any

import httpx

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if _BACKEND.is_dir() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.modules.form_fill_engine.schemas import (
    ActionInstruction,
    DOMSnapshot,
    EngineResponse,
    EngineStepRequest,
    InteractiveElement,
)

log = logging.getLogger(__name__)

# Injected into page.evaluate — keep self-contained JS.
_CAPTURE_JS = r"""
() => {
  function getAccessibleLabel(el) {
    const id = el.getAttribute('id');
    if (id) {
      const lab = document.querySelector('label[for="' + CSS.escape(id) + '"]');
      if (lab) return (lab.innerText || lab.textContent || '').trim().slice(0, 240);
    }
    const wrap = el.closest('label');
    if (wrap) return (wrap.innerText || wrap.textContent || '').trim().slice(0, 240);
    return (
      el.getAttribute('aria-label') ||
      el.getAttribute('placeholder') ||
      el.getAttribute('name') ||
      (el.innerText || '').trim() ||
      ''
    ).slice(0, 240);
  }
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return '';
    if (el.id) return '#' + CSS.escape(el.id);
    const tag = el.tagName.toLowerCase();
    const name = el.getAttribute('name');
    if (name) return tag + '[name=' + JSON.stringify(name) + ']';
    const parent = el.parentElement;
    if (!parent) return tag;
    const siblings = Array.from(parent.children).filter((c) => c.tagName === el.tagName);
    const idx = siblings.indexOf(el) + 1;
    return cssPath(parent) + ' > ' + tag + ':nth-of-type(' + idx + ')';
  }
  const interactiveSelectors = 'input, select, textarea, button, [role="button"]';
  const els = Array.from(document.querySelectorAll(interactiveSelectors)).filter((el) => {
    if (el.disabled) return false;
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (['hidden', 'image', 'reset'].includes(type)) return false;
    const rect = el.getBoundingClientRect();
    if (type === 'file') return true;
    return rect.width > 0 && rect.height > 0;
  });
  return els.map((el, i) => {
    const tag = el.tagName.toLowerCase();
    let options = null;
    if (tag === 'select') {
      options = Array.from(el.options).map((o) => (o.textContent || '').trim());
    }
    return {
      index: i,
      tag: tag === 'a' ? 'button' : tag,
      element_type: el.type || null,
      label: getAccessibleLabel(el),
      current_value: el.value != null ? String(el.value) : null,
      options,
      required: !!el.required,
      visible: true,
      selector: cssPath(el),
    };
  });
}
"""


async def capture_dom_snapshot(page, *, include_screenshot: bool = False) -> DOMSnapshot:
    """Convert current Playwright page into Engine-standard DOMSnapshot."""
    raw = await page.evaluate(_CAPTURE_JS)
    elements = [InteractiveElement(**e) for e in (raw or [])]
    screenshot_b64 = None
    if include_screenshot:
        shot = await page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(shot).decode("ascii")
    return DOMSnapshot(
        url=page.url,
        page_title=await page.title(),
        elements=elements,
        screenshot_base64=screenshot_b64,
    )


def build_selector_for(target: InteractiveElement) -> str:
    if target.selector:
        return target.selector
    # Fallback: nth interactive match — fragile; prefer selector from capture
    return f"xpath=(//input|//select|//textarea|//button)[{target.index + 1}]"


async def execute_instruction(
    page,
    instr: ActionInstruction,
    elements: list[InteractiveElement],
) -> None:
    """Translate one Engine instruction into Playwright I/O."""
    if instr.action in {"pause_for_human", "submit"}:
        # Orchestrator handles gates; never auto-submit here.
        return
    if instr.action == "wait":
        await page.wait_for_timeout(1000)
        return
    if instr.element_index is None:
        return
    if instr.element_index < 0 or instr.element_index >= len(elements):
        log.warning("element_index out of range: %s", instr.element_index)
        return
    target = elements[instr.element_index]
    selector = build_selector_for(target)

    if instr.requires_confirmation:
        log.info("skipping requires_confirmation instr: %s", instr.reason)
        return

    if instr.action == "fill":
        await page.fill(selector, instr.value or "")
    elif instr.action == "click":
        await page.click(selector)
    elif instr.action == "select":
        await page.select_option(selector, label=instr.value)
    elif instr.action == "upload_file":
        if instr.file_path:
            await page.set_input_files(selector, instr.file_path)
        else:
            log.warning("upload_file missing file_path — manual fallback")
    else:
        log.warning("unknown action: %s", instr.action)


async def call_engine_api(
    snapshot: DOMSnapshot,
    job_info: dict[str, Any],
    profile: dict[str, Any],
    *,
    engine_url: str = "http://127.0.0.1:8000/engine/step",
    resume_facts: dict[str, Any] | None = None,
    in_process: bool = False,
) -> EngineResponse:
    req = EngineStepRequest(
        dom_snapshot=snapshot,
        job_info=job_info,
        profile=profile,
        resume_facts=resume_facts or {},
        allow_submit=False,
    )
    if in_process:
        from app.modules.form_fill_engine.service import plan_step

        return await plan_step(req)
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(engine_url, json=req.model_dump())
        resp.raise_for_status()
        return EngineResponse.model_validate(resp.json())


async def run_apply_flow(
    page,
    job_info: dict[str, Any],
    profile: dict[str, Any],
    *,
    engine_url: str = "http://127.0.0.1:8000/engine/step",
    resume_facts: dict[str, Any] | None = None,
    in_process: bool = True,
    max_loops: int = 5,
) -> EngineResponse:
    """Scenario ① main loop — stops at pause_for_human / ready_to_submit.

    Never clicks real Submit (data-safety: paused_before_submit).
    """
    url = job_info.get("resolved_url") or job_info.get("url")
    if url:
        await page.goto(url, wait_until="domcontentloaded")

    last: EngineResponse | None = None
    for _ in range(max_loops):
        snapshot = await capture_dom_snapshot(page)
        last = await call_engine_api(
            snapshot,
            job_info,
            profile,
            engine_url=engine_url,
            resume_facts=resume_facts,
            in_process=in_process,
        )
        for instr in last.instructions:
            if instr.action == "pause_for_human":
                log.info("pause_for_human: %s", last.summary_for_human)
                return last
            if instr.action == "submit":
                # Hard stop — do not submit
                log.warning("submit instruction ignored (paused_before_submit)")
                return last
            await execute_instruction(page, instr, snapshot.elements)
        if last.stage in {"ready_to_submit", "awaiting_human_review", "error"}:
            break
    return last or EngineResponse(stage="error", summary_for_human="empty loop")
