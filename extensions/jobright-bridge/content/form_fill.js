/**
 * Driver B — multi-frame capture (same-origin iframe merge) + ActionInstruction exec.
 * Cross-origin iframes: each frame runs its own content script (all_frames: true).
 */

const ENGINE_URL_DEFAULT = "http://127.0.0.1:8000/engine/step";

function getAccessibleLabel(el) {
  const id = el.getAttribute("id");
  if (id) {
    try {
      const lab = document.querySelector(`label[for="${CSS.escape(id)}"]`);
      if (lab) return (lab.innerText || lab.textContent || "").trim().slice(0, 240);
    } catch (_) {}
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

function collectLocalElements() {
  const interactiveSelectors = 'input, select, textarea, button, [role="button"]';
  return Array.from(document.querySelectorAll(interactiveSelectors)).filter((el) => {
    if (el.disabled) return false;
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (["hidden", "image", "reset"].includes(type)) return false;
    const rect = el.getBoundingClientRect();
    if (type === "file") return true;
    return rect.width > 0 && rect.height > 0;
  });
}

function serializeEls(els, frameIndex, frameUrl) {
  return els.map((el, i) => ({
    index: i, // remapped by merger
    tag: el.tagName.toLowerCase(),
    element_type: el.type || null,
    label: getAccessibleLabel(el),
    current_value:
      el.type === "file"
        ? el.files && el.files.length
          ? el.files[0].name
          : ""
        : el.value != null
          ? String(el.value)
          : null,
    options:
      el.tagName === "SELECT"
        ? Array.from(el.options).map((o) => (o.textContent || "").trim())
        : null,
    required: !!el.required,
    visible: true,
    frame_index: frameIndex,
    frame_url: frameUrl,
    in_iframe: frameIndex > 0,
  }));
}

/** Same-origin: walk iframes and keep live element refs for execute. */
function captureDOMSnapshotMerged() {
  const refs = [];
  const elements = [];
  let frameIndex = 0;

  function walk(doc, win, fi, frameUrl) {
    const els = Array.from(
      doc.querySelectorAll('input, select, textarea, button, [role="button"]')
    ).filter((el) => {
      if (el.disabled) return false;
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (["hidden", "image", "reset"].includes(type)) return false;
      const rect = el.getBoundingClientRect();
      if (type === "file") return true;
      return rect.width > 0 && rect.height > 0;
    });
    for (const el of els) {
      const ser = serializeEls([el], fi, frameUrl)[0];
      ser.index = elements.length;
      elements.push(ser);
      refs.push(el);
    }
    const iframes = doc.querySelectorAll("iframe");
    iframes.forEach((iframe) => {
      try {
        const childDoc = iframe.contentDocument;
        const childWin = iframe.contentWindow;
        if (!childDoc || !childWin) return;
        frameIndex += 1;
        walk(childDoc, childWin, frameIndex, childWin.location.href);
      } catch (_) {
        // cross-origin — child content script handles itself
      }
    });
  }

  // Only top frame merges; child frames respond to CAPTURE_FRAME messages.
  if (window === window.top) {
    walk(document, window, 0, location.href);
    window.__engineElementRefs = refs;
    return {
      url: location.href,
      page_title: document.title,
      elements,
      frame_count: frameIndex + 1,
      form_stage: null,
    };
  }

  // Nested frame standalone capture
  const local = collectLocalElements();
  window.__engineElementRefs = local;
  return {
    url: location.href,
    page_title: document.title,
    elements: serializeEls(local, 0, location.href).map((e, i) => ({ ...e, index: i })),
    frame_count: 1,
  };
}

function executeInstruction(instr) {
  if (instr.action === "wait") return;
  if (instr.action === "pause_for_human" || instr.action === "submit") return;

  const el = window.__engineElementRefs?.[instr.element_index];
  if (!el) return;

  if (instr.requires_confirmation && instr.action !== "upload_file") return;

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
      // Cannot set file path from content script — open native picker.
      el.click();
      chrome.runtime.sendMessage({
        type: "UPLOAD_MANUAL_FALLBACK",
        reason: instr.reason || "请手动选择简历文件",
        file_path_hint: instr.file_path || "",
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
  if (window !== window.top) return; // only top orchestrates
  const maxLoops = 8;
  for (let i = 0; i < maxLoops; i++) {
    const snapshot = captureDOMSnapshotMerged();
    const engineResponse = await callEngine(snapshot, jobInfo, profile);
    let advanced = false;

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
        chrome.runtime.sendMessage({
          type: "SHOW_REVIEW_PANEL",
          summary: "paused_before_submit — submit blocked",
          stage: "awaiting_human_review",
        });
        return engineResponse;
      }
      if (instr.action === "wait") {
        await new Promise((r) => setTimeout(r, Number(instr.value) || 1000));
        continue;
      }
      executeInstruction(instr);
      if (instr.action === "click") advanced = true;
      await new Promise((r) => setTimeout(r, 300));
    }

    if (engineResponse.stage === "awaiting_human_review") {
      chrome.runtime.sendMessage({
        type: "SHOW_REVIEW_PANEL",
        summary: engineResponse.summary_for_human,
        stage: engineResponse.stage,
      });
      return engineResponse;
    }
    if (advanced || engineResponse.stage === "filling") {
      await new Promise((r) => setTimeout(r, 800));
      continue;
    }
    break;
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
  if (msg?.type === "START_FILL" && window === window.top) {
    initApplyFlow(msg.jobData || {});
    sendResponse({ ok: true });
  }
  if (msg?.type === "CAPTURE_ONLY") {
    sendResponse({ snapshot: captureDOMSnapshotMerged() });
  }
  return true;
});

window.__formFillInitApplyFlow = initApplyFlow;
