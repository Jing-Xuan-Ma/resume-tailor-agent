/**
 * Driver B content script — DOMSnapshot capture + ActionInstruction execution.
 * Decision logic lives on the Engine HTTP service only.
 */

const ENGINE_URL_DEFAULT = "http://127.0.0.1:8000/engine/step";

function getAccessibleLabel(el) {
  const id = el.getAttribute("id");
  if (id) {
    try {
      const lab = document.querySelector(`label[for="${CSS.escape(id)}"]`);
      if (lab) return (lab.innerText || lab.textContent || "").trim().slice(0, 240);
    } catch (_) {
      /* ignore */
    }
  }
  const wrap = el.closest("label");
  if (wrap) return (wrap.innerText || wrap.textContent || "").trim().slice(0, 240);
  return (
    el.getAttribute("aria-label") ||
    el.getAttribute("placeholder") ||
    el.getAttribute("name") ||
    (el.innerText || "").trim() ||
    ""
  ).slice(0, 240);
}

function captureDOMSnapshot() {
  const interactiveSelectors = 'input, select, textarea, button, [role="button"]';
  const els = Array.from(document.querySelectorAll(interactiveSelectors)).filter((el) => {
    if (el.disabled) return false;
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (["hidden", "image", "reset"].includes(type)) return false;
    const rect = el.getBoundingClientRect();
    if (type === "file") return true;
    return rect.width > 0 && rect.height > 0;
  });

  window.__engineElementRefs = els;

  return {
    url: window.location.href,
    page_title: document.title,
    elements: els.map((el, i) => ({
      index: i,
      tag: el.tagName.toLowerCase(),
      element_type: el.type || null,
      label: getAccessibleLabel(el),
      current_value: el.value != null ? String(el.value) : null,
      options:
        el.tagName === "SELECT"
          ? Array.from(el.options).map((o) => (o.textContent || "").trim())
          : null,
      required: !!el.required,
      visible: true,
    })),
  };
}

function executeInstruction(instr) {
  if (instr.action === "wait") return;
  if (instr.action === "pause_for_human" || instr.action === "submit") return;
  if (instr.requires_confirmation) return;

  const el = window.__engineElementRefs?.[instr.element_index];
  if (!el) return;

  switch (instr.action) {
    case "fill": {
      el.focus();
      el.value = instr.value || "";
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      break;
    }
    case "click":
      el.click();
      break;
    case "select": {
      const opt = Array.from(el.options || []).find((o) => o.text === instr.value);
      if (opt) el.value = opt.value;
      el.dispatchEvent(new Event("change", { bubbles: true }));
      break;
    }
    case "upload_file":
      // Browser security: cannot set file input value from JS.
      el.click();
      chrome.runtime.sendMessage({
        type: "UPLOAD_MANUAL_FALLBACK",
        reason: instr.reason || "Please choose the resume file manually",
      });
      break;
    default:
      break;
  }
}

async function callEngine(snapshot, jobInfo, profile) {
  const { engineUrl } = await chrome.storage.local.get({ engineUrl: ENGINE_URL_DEFAULT });
  const resp = await fetch(engineUrl || ENGINE_URL_DEFAULT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dom_snapshot: snapshot,
      job_info: jobInfo || {},
      profile: profile || {},
      resume_facts: profile || {},
      allow_submit: false,
    }),
  });
  if (!resp.ok) throw new Error(`Engine HTTP ${resp.status}`);
  return resp.json();
}

async function runApplyFlow(jobInfo, profile) {
  const maxLoops = 5;
  for (let i = 0; i < maxLoops; i++) {
    const snapshot = captureDOMSnapshot();
    const engineResponse = await callEngine(snapshot, jobInfo, profile);

    for (const instr of engineResponse.instructions || []) {
      if (instr.action === "pause_for_human") {
        chrome.runtime.sendMessage({
          type: "SHOW_REVIEW_PANEL",
          summary: engineResponse.summary_for_human,
          stage: engineResponse.stage,
        });
        return engineResponse;
      }
      if (instr.action === "submit") {
        // Data-safety: never auto-submit
        chrome.runtime.sendMessage({
          type: "SHOW_REVIEW_PANEL",
          summary: "paused_before_submit — submit blocked",
          stage: "awaiting_human_review",
        });
        return engineResponse;
      }
      executeInstruction(instr);
      await new Promise((r) => setTimeout(r, 300));
    }
    if (engineResponse.stage === "ready_to_submit" || engineResponse.stage === "awaiting_human_review") {
      chrome.runtime.sendMessage({
        type: "SHOW_REVIEW_PANEL",
        summary: engineResponse.summary_for_human,
        stage: engineResponse.stage,
      });
      break;
    }
  }
}

function initApplyFlow(jobData) {
  const jobInfo = { id: jobData.jobId, resolved_url: location.href };
  const profile = jobData.profile || {};
  runApplyFlow(jobInfo, profile).catch((err) => {
    chrome.runtime.sendMessage({ type: "ENGINE_ERROR", error: String(err) });
  });
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "START_FILL") {
    initApplyFlow(msg.jobData || {});
    sendResponse({ ok: true });
  }
  if (msg?.type === "CAPTURE_ONLY") {
    sendResponse({ snapshot: captureDOMSnapshot() });
  }
  return true;
});

window.__formFillInitApplyFlow = initApplyFlow;
