const DEFAULTS = {
  apiBase: "http://127.0.0.1:8000",
  frontendBase: "http://127.0.0.1:3000",
  extensionToken: "dev-extension-token",
};

function isJobrightUrl(url) {
  const u = String(url || "");
  return /jobright\.ai/i.test(u) || /jobright-mock\.html/i.test(u);
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.type) return false;

  if (msg.type === "ra_job_extracted") {
    chrome.storage.session.set({ lastJob: msg.job || null });
    chrome.runtime.sendMessage({ type: "ra_job_updated", job: msg.job }).catch(() => {});
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === "ra_upsert_lead") {
    upsertLead(msg.job || {}, msg.force === true)
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true;
  }

  if (msg.type === "ra_get_settings") {
    chrome.storage.sync.get(DEFAULTS, (cfg) => sendResponse({ ok: true, cfg: { ...DEFAULTS, ...cfg } }));
    return true;
  }

  if (msg.type === "ra_extract_from_jobright") {
    extractFromJobrightTab()
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true;
  }

  // Open Resume Agent in a dedicated full window (no side panel).
  if (msg.type === "ra_open_workspace") {
    const url = String(msg.url || "").trim();
    if (!url) {
      sendResponse({ ok: false, error: "missing_url" });
      return false;
    }
    openWorkspaceWindow(url, {
      returnTabId: msg.returnTabId,
      returnWindowId: msg.returnWindowId,
      returnUrl: msg.returnUrl,
    })
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true;
  }

  if (msg.type === "ra_open_tailor") {
    openStepFromJobright("tailor", msg.force === true)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true;
  }

  if (msg.type === "ra_open_apply") {
    openStepFromJobright("apply", msg.force === true)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true;
  }

  if (msg.type === "ra_open_outreach") {
    openStepFromJobright("outreach", msg.force === true)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true;
  }

  if (msg.type === "ra_focus_jobright") {
    focusJobright(msg.returnUrl)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true;
  }

  return false;
});

/** Toolbar icon → one-click Tailor (no Side Panel). */
chrome.action.onClicked.addListener(() => {
  void openTailorFromJobright(false);
});

async function findJobrightTab() {
  const all = await chrome.tabs.query({});
  const jrTabs = (all || []).filter((t) => isJobrightUrl(t.url));
  const focused = jrTabs.find((t) => t.active);
  if (focused) return focused;
  if (jrTabs.length) return jrTabs[0];
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (active && isJobrightUrl(active.url)) return active;
  return null;
}

async function injectExtractors(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["content/extract.js", "content/fab.js", "content/demote.js"],
  });
}

async function extractFromJobrightTab() {
  const tab = await findJobrightTab();
  if (!tab || tab.id == null) {
    return {
      ok: false,
      error: "No Jobright tab found. Keep a job detail open, then try again.",
    };
  }

  try {
    const res = await chrome.tabs.sendMessage(tab.id, { type: "ra_extract_now" });
    if (res && res.job && (res.job.raw_text || "").trim()) {
      await chrome.storage.session.set({ lastJob: res.job });
      return { ok: true, job: res.job, tabId: tab.id, mode: "message" };
    }
  } catch (_) {
    /* not injected yet — reinject below */
  }

  try {
    await injectExtractors(tab.id);
    await new Promise((r) => setTimeout(r, 200));
    const res2 = await chrome.tabs.sendMessage(tab.id, { type: "ra_extract_now" });
    if (res2 && res2.job && (res2.job.raw_text || "").trim()) {
      await chrome.storage.session.set({ lastJob: res2.job });
      return { ok: true, job: res2.job, tabId: tab.id, mode: "reinjected" };
    }
  } catch (err) {
    return {
      ok: false,
      error:
        "Could not read this Jobright page. Refresh the Jobright tab (F5) once after reloading the extension.",
      detail: String(err && err.message ? err.message : err),
      tabUrl: tab.url || "",
    };
  }

  const stored = await chrome.storage.session.get("lastJob");
  if (stored.lastJob && (stored.lastJob.raw_text || "").trim()) {
    return { ok: true, job: stored.lastJob, tabId: tab.id, mode: "cached" };
  }

  return {
    ok: false,
    error: "Job page opened but JD text was empty. Scroll the description into view, then retry.",
    tabUrl: tab.url || "",
  };
}

async function openTailorFromJobright(force) {
  return openStepFromJobright("tailor", force);
}

/** @param {"tailor"|"apply"|"outreach"} step */
async function openStepFromJobright(step, force) {
  const extracted = await extractFromJobrightTab();
  if (!extracted.ok || !extracted.job || !(extracted.job.raw_text || "").trim()) {
    return { ok: false, error: (extracted && extracted.error) || "No JD detected" };
  }
  const job = { ...extracted.job };
  const tabUrl =
    job.page_url || job.jobright_url || (extracted.tabUrl || "") || "";
  if ((!job.page_url || !job.jobright_url || !job.source_url) && /^https?:\/\//i.test(tabUrl)) {
    job.page_url = job.page_url || tabUrl;
    job.jobright_url = job.jobright_url || tabUrl;
    job.source_url = job.source_url || job.apply_url || tabUrl;
  }

  const data = await upsertLead(job, force);
  let url = data.workspace_url;
  if (step === "apply") url = data.apply_step_url || url;
  if (step === "outreach") url = data.outreach_step_url || url;

  let returnWindowId = null;
  if (extracted.tabId != null) {
    try {
      const t = await chrome.tabs.get(extracted.tabId);
      returnWindowId = t.windowId;
    } catch (_) {
      /* ignore */
    }
  }
  return openWorkspaceWindow(url, {
    returnTabId: extracted.tabId,
    returnWindowId,
    returnUrl: job.jobright_url || job.page_url || null,
  }).then(async (opened) => {
    if (extracted.tabId != null) {
      try {
        await chrome.tabs.sendMessage(extracted.tabId, { type: "ra_mark_processed" });
      } catch (_) {
        /* ignore */
      }
    }
    return opened;
  });
}

async function focusJobright(fallbackUrl) {
  const stored = await chrome.storage.session.get("jobrightReturn");
  const info = stored.jobrightReturn || {};
  const returnUrl = String(fallbackUrl || info.returnUrl || "").trim();

  if (info.returnTabId != null) {
    try {
      await chrome.tabs.update(info.returnTabId, { active: true });
      if (info.returnWindowId != null) {
        await chrome.windows.update(info.returnWindowId, { focused: true });
      }
      return { ok: true, mode: "focus_tab" };
    } catch (_) {
      /* tab closed — fall through */
    }
  }

  if (returnUrl && /^https?:\/\//i.test(returnUrl)) {
    const tabs = await chrome.tabs.query({ url: ["*://jobright.ai/*", "*://*.jobright.ai/*"] });
    if (tabs && tabs[0] && tabs[0].id != null) {
      await chrome.tabs.update(tabs[0].id, { active: true, url: returnUrl });
      if (tabs[0].windowId != null) {
        await chrome.windows.update(tabs[0].windowId, { focused: true });
      }
      return { ok: true, mode: "reuse_jobright_tab" };
    }
    const win = await chrome.windows.create({
      url: returnUrl,
      focused: true,
      type: "normal",
      width: 1280,
      height: 900,
    });
    return { ok: true, mode: "open_jobright", windowId: win && win.id };
  }

  return { ok: false, error: "no_jobright_return_target" };
}

async function openWorkspaceWindow(url, returnInfo) {
  const info = {
    returnTabId: returnInfo && returnInfo.returnTabId,
    returnWindowId: returnInfo && returnInfo.returnWindowId,
    returnUrl: returnInfo && returnInfo.returnUrl,
  };
  await chrome.storage.session.set({ jobrightReturn: info });

  let finalUrl = url;
  if (info.returnUrl && !/[?&]returnTo=/.test(url)) {
    const join = url.includes("?") ? "&" : "?";
    finalUrl = `${url}${join}returnTo=${encodeURIComponent(info.returnUrl)}`;
  }

  const win = await chrome.windows.create({
    url: finalUrl,
    focused: true,
    type: "normal",
    width: 1440,
    height: 900,
  });
  const tabId = win && win.tabs && win.tabs[0] && win.tabs[0].id;
  return { ok: true, windowId: win && win.id, tabId };
}

async function loadCfg() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(DEFAULTS, (cfg) => resolve({ ...DEFAULTS, ...cfg }));
  });
}

async function upsertLead(job, force) {
  const cfg = await loadCfg();
  let applyUrl = String(job.apply_url || "").trim();
  // Keep Jobright-stamped company ATS links; only drop pure jobright.ai page URLs
  // that are not an Apply redirect (we still allow jobright apply redirects).
  const pageUrl = String(job.page_url || job.jobright_url || "").trim();
  if (applyUrl && /jobright\.ai/i.test(applyUrl) && !/apply/i.test(applyUrl)) {
    applyUrl = "";
  }
  // Manual Apply must open the SAME company link Jobright Apply uses.
  const sourceUrl = applyUrl || pageUrl || String(job.source_url || "").trim();
  if (!sourceUrl) {
    throw new Error("No page URL found — keep the Jobright tab focused and retry.");
  }
  const body = {
    title: job.title || "Untitled",
    company: job.company || "Unknown Company",
    location: job.location || null,
    raw_text: job.raw_text || "",
    source_url: sourceUrl,
    jobright_url: pageUrl || null,
    source_platform: "jobright_extension",
    force: !!force,
    metadata: {
      apply_url: applyUrl || null,
      extracted_at: job.extracted_at || null,
      page_url: pageUrl || null,
      has_external_apply: !!(applyUrl && !/jobright\.ai/i.test(applyUrl)),
    },
  };
  const res = await fetch(`${cfg.apiBase.replace(/\/$/, "")}/api/v1/jobs/index/leads`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Extension-Token": cfg.extensionToken || "",
    },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch (_) {
    data = { detail: text };
  }
  if (!res.ok) {
    const detail = data.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : detail && detail.message
          ? `${detail.message} (${detail.reason || ""})`
          : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  const fe = cfg.frontendBase.replace(/\/$/, "");
  const id = data.id;
  const root = `${fe}/?view=resume&jobId=${encodeURIComponent(id)}`;
  // Jobright already shows JD — open Tailor (agent + PDF) directly.
  data.workspace_url = `${root}&step=tailor`;
  data.apply_step_url = `${root}&step=apply`;
  // Dedicated outreach tab — not squeezed beside PDF.
  data.outreach_step_url = `${fe}/outreach?jobId=${encodeURIComponent(id)}`;
  return data;
}
