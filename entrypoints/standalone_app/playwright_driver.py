"""Playwright Driver A — multi-frame capture, dynamic settle, file upload.

Decision logic stays in the Engine; this module only translates JSON ↔ browser I/O.
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

# Per-frame capture — keep self-contained (no external refs).
_CAPTURE_JS = r"""
() => {
  function getAccessibleLabel(el) {
    const id = el.getAttribute('id');
    if (id) {
      try {
        const lab = document.querySelector('label[for="' + CSS.escape(id) + '"]');
        if (lab) return (lab.innerText || lab.textContent || '').trim().slice(0, 240);
      } catch (e) {}
    }
    const wrap = el.closest('label');
    if (wrap) return (wrap.innerText || wrap.textContent || '').trim().slice(0, 240);
    const labelled = el.getAttribute('aria-labelledby');
    if (labelled) {
      const node = document.getElementById(labelled);
      if (node) return (node.innerText || '').trim().slice(0, 240);
    }
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
    if (el.id) {
      try { return '#' + CSS.escape(el.id); } catch (e) { return '#' + el.id; }
    }
    const tag = el.tagName.toLowerCase();
    const name = el.getAttribute('name');
    if (name) return tag + '[name=' + JSON.stringify(name) + ']';
    const da = el.getAttribute('data-automation-id');
    if (da) return tag + '[data-automation-id=' + JSON.stringify(da) + ']';
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
    const style = window.getComputedStyle(el);
    if (style && (style.visibility === 'hidden' || style.display === 'none')) return false;
    return rect.width > 0 && rect.height > 0;
  });
  return els.map((el, i) => {
    const tag = el.tagName.toLowerCase();
    let options = null;
    if (tag === 'select') {
      options = Array.from(el.options).map((o) => (o.textContent || '').trim());
    }
    let current = null;
    if (tag === 'input' && (el.type || '').toLowerCase() === 'file') {
      current = (el.files && el.files.length) ? el.files[0].name : '';
    } else if (el.value != null) {
      current = String(el.value);
    }
    return {
      index: i,
      tag: tag === 'a' ? 'button' : tag,
      element_type: el.type || null,
      label: getAccessibleLabel(el),
      current_value: current,
      options,
      required: !!el.required,
      visible: true,
      selector: cssPath(el),
    };
  });
}
"""


def _frame_for_index(page, frame_index: int):
    frames = list(page.frames)
    if 0 <= int(frame_index) < len(frames):
        return frames[int(frame_index)]
    return page.main_frame


async def capture_dom_snapshot(page, *, include_screenshot: bool = False) -> DOMSnapshot:
    """Scan main frame + all child frames (same-origin accessible via Playwright)."""
    elements: list[InteractiveElement] = []
    frames = list(page.frames)
    global_index = 0
    for fi, frame in enumerate(frames):
        try:
            raw = await frame.evaluate(_CAPTURE_JS)
        except Exception as exc:
            # Cross-origin iframe: Playwright cannot evaluate — skip with log
            log.debug("frame %s capture skipped: %s", fi, exc)
            continue
        if not isinstance(raw, list):
            continue
        frame_url = ""
        try:
            frame_url = frame.url or ""
        except Exception:
            frame_url = ""
        in_iframe = fi != 0
        for item in raw:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["index"] = global_index
            global_index += 1
            row["frame_index"] = fi
            row["frame_url"] = frame_url
            row["in_iframe"] = in_iframe
            # Prefix label hint for Engine summaries when inside iframe
            if in_iframe and row.get("label"):
                row["label"] = str(row["label"])
            try:
                elements.append(InteractiveElement(**row))
            except Exception as exc:
                log.debug("skip element: %s", exc)

    # Infer form stage from visible button labels
    form_stage = None
    labels = " ".join((e.label or "").lower() for e in elements)
    if "submit" in labels and "next" not in labels:
        form_stage = "review_or_final"
    elif "next" in labels or "continue" in labels:
        form_stage = "multi_step"

    screenshot_b64 = None
    if include_screenshot:
        shot = await page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(shot).decode("ascii")

    title = ""
    try:
        title = await page.title()
    except Exception:
        title = ""

    return DOMSnapshot(
        url=page.url,
        page_title=title,
        elements=elements,
        screenshot_base64=screenshot_b64,
        form_stage=form_stage,
        frame_count=len(frames),
    )


def build_selector_for(target: InteractiveElement) -> str:
    if target.selector:
        return target.selector
    return f"xpath=(//input|//select|//textarea|//button)[{max(1, target.index + 1)}]"


async def settle_after_action(page, *, ms: int = 800) -> None:
    """Wait for dynamic ATS UIs (SPA / iframe / network)."""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=ms)
    except Exception:
        pass
    try:
        await page.wait_for_timeout(min(ms, 3000))
    except Exception:
        pass


async def _upload_on_frame(frame, target: InteractiveElement, file_path: str) -> bool:
    path = Path(file_path)
    if not path.is_file():
        log.warning("upload_file path missing: %s", file_path)
        return False

    selectors: list[str] = []
    if target.selector:
        selectors.append(target.selector)
    selectors.extend(
        [
            "input[type='file']",
            "input[type='file'][name*='resume' i]",
            "input[type='file'][id*='resume' i]",
            "input[data-automation-id*='resume' i]",
            "input[data-testid*='resume' i]",
        ]
    )
    for sel in selectors:
        try:
            loc = frame.locator(sel).first
            if await loc.count() == 0:
                continue
            await loc.set_input_files(str(path.resolve()), timeout=4000)
            return True
        except Exception as exc:
            log.debug("upload selector %s failed: %s", sel, exc)
            continue
    # Label fallback
    label = (target.label or "").strip()
    if label:
        try:
            await frame.get_by_label(label, exact=False).set_input_files(
                str(path.resolve()), timeout=4000
            )
            return True
        except Exception:
            pass
    return False


async def execute_instruction(
    page,
    instr: ActionInstruction,
    elements: list[InteractiveElement],
) -> bool:
    """Translate one Engine instruction into Playwright I/O. Returns success."""
    if instr.action in {"pause_for_human", "submit"}:
        return True
    if instr.action == "wait":
        ms = 1000
        if instr.value and str(instr.value).isdigit():
            ms = int(instr.value)
        await settle_after_action(page, ms=ms)
        return True

    if instr.element_index is None:
        return False
    if instr.element_index < 0 or instr.element_index >= len(elements):
        log.warning("element_index out of range: %s", instr.element_index)
        return False

    target = elements[instr.element_index]
    frame = _frame_for_index(page, target.frame_index)
    selector = build_selector_for(target)

    # Confirmation gate: still execute uploads/fills when we have concrete values
    # (Engine sets requires_confirmation for missing files / low confidence).
    if instr.requires_confirmation and instr.action != "upload_file":
        log.info("skipping requires_confirmation instr: %s", instr.reason)
        return False
    if instr.requires_confirmation and instr.action == "upload_file" and not instr.file_path:
        log.info("upload needs manual picker: %s", instr.reason)
        try:
            await frame.locator(selector).first.click(timeout=2000)
        except Exception:
            pass
        return False

    try:
        if instr.action == "fill":
            loc = frame.locator(selector).first
            await loc.fill(instr.value or "", timeout=3000)
            # Trigger framework listeners (React/Vue)
            try:
                await loc.dispatch_event("input")
                await loc.dispatch_event("change")
            except Exception:
                pass
            return True
        if instr.action == "click":
            await frame.locator(selector).first.click(timeout=3000)
            await settle_after_action(page, ms=1200)
            return True
        if instr.action == "select":
            loc = frame.locator(selector).first
            try:
                await loc.select_option(label=instr.value, timeout=3000)
            except Exception:
                await loc.select_option(value=instr.value, timeout=3000)
            return True
        if instr.action == "upload_file":
            ok = await _upload_on_frame(frame, target, instr.file_path or "")
            if not ok:
                log.warning("upload_file failed for index=%s path=%s", instr.element_index, instr.file_path)
            await settle_after_action(page, ms=800)
            return ok
        log.warning("unknown action: %s", instr.action)
        return False
    except Exception as exc:
        log.warning("execute %s failed: %s", instr.action, exc)
        return False


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
    max_loops: int = 8,
) -> EngineResponse:
    """Main loop with re-snapshot after dynamic Next / iframe loads.

    Never clicks real Submit (data-safety: paused_before_submit).
    """
    url = job_info.get("resolved_url") or job_info.get("url")
    if url:
        await page.goto(url, wait_until="domcontentloaded")
        await settle_after_action(page, ms=1000)

    last: EngineResponse | None = None
    prev_signature: str | None = None
    stagnant = 0

    for loop_i in range(max_loops):
        snapshot = await capture_dom_snapshot(page)
        signature = "|".join(
            f"{e.frame_index}:{e.tag}:{e.label}:{e.current_value}" for e in snapshot.elements
        )
        if signature == prev_signature:
            stagnant += 1
        else:
            stagnant = 0
        prev_signature = signature

        last = await call_engine_api(
            snapshot,
            job_info,
            profile,
            engine_url=engine_url,
            resume_facts=resume_facts,
            in_process=in_process,
        )

        advanced = False
        for instr in last.instructions:
            if instr.action == "pause_for_human":
                log.info("pause_for_human @loop=%s: %s", loop_i, last.summary_for_human)
                return last
            if instr.action == "submit":
                log.warning("submit instruction ignored (paused_before_submit)")
                return last
            ok = await execute_instruction(page, instr, snapshot.elements)
            if instr.action == "click" and ok:
                advanced = True

        if last.stage == "awaiting_human_review" and any(
            i.action == "pause_for_human" for i in last.instructions
        ):
            return last

        if advanced or last.stage == "filling":
            await settle_after_action(page, ms=1000)
            # Continue loop to re-snapshot dynamic / next-step form
            if stagnant >= 2 and not advanced:
                # DOM unchanged twice without advance → force pause
                return EngineResponse(
                    instructions=[
                        ActionInstruction(
                            action="pause_for_human",
                            reason="动态表单无变化，交还人工",
                            requires_confirmation=True,
                        )
                    ],
                    stage="awaiting_human_review",
                    summary_for_human="表单 DOM 停滞，请人工继续。",
                    ats=last.ats,
                    meta={"stagnant": True, "loop": loop_i},
                )
            continue

        if last.stage in {"ready_to_submit", "error"}:
            break

    return last or EngineResponse(stage="error", summary_for_human="empty loop")
