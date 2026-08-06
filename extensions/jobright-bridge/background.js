const DEFAULTS = {
  apiBase: "http://127.0.0.1:8000",
  frontendBase: "http://127.0.0.1:3000",
  extensionToken: "dev-extension-token",
};

function isJobrightUrl(url) {
  const u = String(url || "");
  return /jobright\.ai/i.test(u) || /jobright-mock\.html/i.test(u);
}

/** Pending ATS tabs waiting for form-fill inject after load. */
const pendingJobs = {}; // { tabId: { jobId, resumePath, profile } }

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg) return false;

  // Form-fill co-pilot (merged from entrypoints/jobright_extension)
  if (msg.action === "openAndFill") {
    chrome.tabs.create({ url: msg.url }, (newTab) => {
      if (!newTab?.id) {
        sendResponse({ ok: false, error: "tab_create_failed" });
        return;
      }
      pendingJobs[newTab.id] = {
        jobId: msg.jobId,
        resumePath: msg.tailoredResumePath,
        profile: msg.profile || {},
      };
      sendResponse({ ok: true, tabId: newTab.id });
    });
    return true;
  }

  if (msg.type === "SHOW_REVIEW_PANEL") {
    chrome.storage.local.set({
      lastReview: {
        summary: msg.summary,
        stage: msg.stage,
        at: Date.now(),
        tabId: sender.tab?.id,
      },
    });
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === "UPLOAD_MANUAL_FALLBACK") {
    chrome.storage.local.set({
      lastUploadHint: {
        reason: msg.reason,
        file_path_hint: msg.file_path_hint,
        at: Date.now(),
      },
    });
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === "SUBMISSION_LOGGED") {
    console.info("submission signal (not auto-confirmed)", msg.jobId);
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === "ENGINE_ERROR") {
    chrome.storage.local.set({
      lastReview: {
        summary: String(msg.error || "engine_error"),
        stage: "error",
        at: Date.now(),
        tabId: sender.tab?.id,
      },
    });
    sendResponse({ ok: true });
    return false;
  }

  if (!msg.type) return false;

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
    openStepFromJobright("tailor", msg.force !== false, sender.tab, msg.job, msg.pageUrl)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true;
  }

  if (msg.type === "ra_open_apply") {
    openStepFromJobright("apply", msg.force !== false, sender.tab, msg.job, msg.pageUrl)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true;
  }

  if (msg.type === "ra_open_outreach") {
    openStepFromJobright("outreach", msg.force !== false, sender.tab, msg.job, msg.pageUrl)
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

  if (msg.type === "ra_scrape_active_tab") {
    const tab = sender.tab;
    scrapeTabDeep(tab && tab.id)
      .then((job) => {
        if (job && (job.raw_text || "").trim().length >= 40) {
          sendResponse({ ok: true, job });
        } else {
          sendResponse({
            ok: false,
            error: "deep_scrape_empty",
            job: job || null,
          });
        }
      })
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true;
  }

  return false;
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status !== "complete" || !pendingJobs[tabId]) return;
  const jobData = pendingJobs[tabId];
  delete pendingJobs[tabId];

  chrome.scripting
    .executeScript({
      target: { tabId },
      files: ["content/form_fill.js"],
    })
    .then(() =>
      chrome.tabs.sendMessage(tabId, {
        type: "START_FILL",
        jobData,
      })
    )
    .catch((err) => console.warn("form_fill inject failed", err));
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
    files: ["content/extract.js", "content/fab-diagnostics.js", "content/fab.js", "content/demote.js"],
  });
}

async function scrapeTabDeep(tabId) {
  if (tabId == null) {
    const tab = await findJobrightTab();
    tabId = tab && tab.id;
  }
  if (tabId == null) return null;

  // Inline deep scrape in every frame — does not depend on content-script globals.
  const results = await chrome.scripting.executeScript({
    target: { tabId, allFrames: true },
    func: () => {
      function deepText(root, limit) {
        let out = "";
        const max = limit || 40000;
        function walk(node) {
          if (!node || out.length >= max) return;
          if (node.nodeType === Node.TEXT_NODE) {
            const t = node.textContent || "";
            if (t.trim()) out += t + " ";
            return;
          }
          if (node.nodeType !== 1 && node.nodeType !== 11) return;
          const tag = (node.tagName || "").toUpperCase();
          if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT" || tag === "SVG") return;
          try {
            if (node.shadowRoot) walk(node.shadowRoot);
          } catch (_) {}
          const kids = node.childNodes || [];
          for (let i = 0; i < kids.length; i++) walk(kids[i]);
        }
        walk(root);
        return out.replace(/\s+/g, " ").trim().slice(0, max);
      }
      let raw = "";
      try {
        raw = deepText(document.documentElement);
      } catch (_) {}
      let title = document.title || "Untitled";
      try {
        const h1 = document.querySelector("h1");
        if (h1 && (h1.innerText || h1.textContent)) {
          title = (h1.innerText || h1.textContent).trim();
        }
      } catch (_) {}
      let apply = null;
      try {
        const anchors = Array.from(document.querySelectorAll("a[href]"));
        for (const a of anchors) {
          const href = a.href || "";
          const label = ((a.innerText || a.textContent || "") + "").toLowerCase();
          if (/utm_source=jobright|greenhouse|lever\.co|myworkdayjobs|ashbyhq/i.test(href)) {
            apply = href;
            break;
          }
          if (label.includes("apply") && /^https?:/i.test(href) && !/jobright\.ai/i.test(href)) {
            apply = href;
            break;
          }
        }
      } catch (_) {}
      return {
        title,
        company: "Unknown Company",
        raw_text: raw,
        page_url: location.href,
        jobright_url: location.href,
        source_url: apply || location.href,
        apply_url: apply,
        body_len: (raw || "").length,
        frame_href: location.href,
      };
    },
  });

  let best = null;
  for (const row of results || []) {
    const job = row && row.result;
    if (!job) continue;
    if (!best || (job.raw_text || "").length > (best.raw_text || "").length) {
      best = job;
    }
  }
  if (best) {
    best.extracted_at = new Date().toISOString();
    best.has_external_apply = !!(best.apply_url && !/jobright\.ai/i.test(best.apply_url));
  }
  return best;
}

async function extractOnce(tabId) {
  // Prefer layered extractReady (MutationObserver + L1/L2/L3) over raw deep scrape.
  try {
    const res = await chrome.tabs.sendMessage(tabId, { type: "ra_extract_now" });
    if (res && res.job && (res.job.raw_text || "").trim().length >= 40) {
      return res.job;
    }
  } catch (_) {
    /* fall through */
  }

  try {
    const injected = await chrome.scripting.executeScript({
      target: { tabId, allFrames: false },
      func: async () => {
        try {
          if (typeof window.__RA_EXTRACT_READY__ === "function") {
            const job = await window.__RA_EXTRACT_READY__();
            return { ok: true, job };
          }
          if (typeof window.__RA_EXTRACT_NOW__ === "function") {
            return { ok: true, job: window.__RA_EXTRACT_NOW__() };
          }
        } catch (e) {
          return { ok: false, error: String(e && e.message ? e.message : e) };
        }
        return { ok: false, error: "extract_not_ready" };
      },
    });
    const payload = injected && injected[0] && injected[0].result;
    if (payload && payload.ok && payload.job && (payload.job.raw_text || "").trim().length >= 40) {
      return payload.job;
    }
  } catch (_) {
    /* fall through */
  }

  try {
    const deep = await scrapeTabDeep(tabId);
    if (deep && (deep.raw_text || "").trim().length >= 40) {
      deep.extract_layer = deep.extract_layer || "background_deep";
      return deep;
    }
  } catch (_) {
    /* ignore */
  }
  return null;
}

async function extractFromJobrightTab(preferredTab) {
  let tab = null;
  // Prefer the tab that sent the click, even when Chrome omits tab.url.
  if (preferredTab && preferredTab.id != null) {
    tab = preferredTab;
  } else {
    tab = await findJobrightTab();
  }
  if (!tab || tab.id == null) {
    return {
      ok: false,
      error: "No Jobright tab found. Keep a job detail open, then try again.",
    };
  }

  let lastDetail = "";
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const job = await extractOnce(tab.id);
      if (job) {
        await chrome.storage.session.set({ lastJob: job });
        return { ok: true, job, tabId: tab.id, mode: attempt ? `retry_${attempt}` : "message" };
      }
    } catch (err) {
      lastDetail = String(err && err.message ? err.message : err);
    }
    try {
      await injectExtractors(tab.id);
      await new Promise((r) => setTimeout(r, 250 + attempt * 200));
      const job2 = await extractOnce(tab.id);
      if (job2) {
        await chrome.storage.session.set({ lastJob: job2 });
        return { ok: true, job: job2, tabId: tab.id, mode: "reinjected" };
      }
    } catch (err) {
      lastDetail = String(err && err.message ? err.message : err);
    }
    await new Promise((r) => setTimeout(r, 400));
  }

  const stored = await chrome.storage.session.get("lastJob");
  if (stored.lastJob && (stored.lastJob.raw_text || "").trim()) {
    return { ok: true, job: stored.lastJob, tabId: tab.id, mode: "cached" };
  }

  return {
    ok: false,
    error:
      "读不到职位描述。请确认已打开左侧职位详情正文，然后 F5 刷新后再试。" +
      (lastDetail ? `\n(${lastDetail})` : ""),
    tabUrl: tab.url || "",
  };
}

async function openTailorFromJobright(force) {
  return openStepFromJobright("tailor", force);
}

/** @param {"tailor"|"apply"|"outreach"} step */
async function openStepFromJobright(step, force, preferredTab, jobFromPage, pageUrlHint) {
  let extracted;
  const incoming = jobFromPage && typeof jobFromPage === "object" ? jobFromPage : null;
  const incomingText = incoming && String(incoming.raw_text || "").trim();
  if (incoming && incomingText.length >= 40) {
    const tabId = preferredTab && preferredTab.id != null ? preferredTab.id : null;
    const pageUrl =
      String(pageUrlHint || incoming.page_url || incoming.jobright_url || (preferredTab && preferredTab.url) || "").trim();
    const job = {
      ...incoming,
      page_url: incoming.page_url || pageUrl || null,
      jobright_url: incoming.jobright_url || pageUrl || null,
      source_url: incoming.source_url || incoming.apply_url || pageUrl || null,
    };
    await chrome.storage.session.set({ lastJob: job });
    extracted = { ok: true, job, tabId, mode: "fab_payload" };
  } else {
    extracted = await extractFromJobrightTab(preferredTab);
  }

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

  try {
    const win = await chrome.windows.create({
      url: finalUrl,
      focused: true,
      type: "normal",
      width: 1440,
      height: 900,
    });
    const tabId = win && win.tabs && win.tabs[0] && win.tabs[0].id;
    return { ok: true, windowId: win && win.id, tabId, mode: "window" };
  } catch (err) {
    // Fallback when window create is blocked — still open Agent in a tab.
    const tab = await chrome.tabs.create({ url: finalUrl, active: true });
    return {
      ok: true,
      tabId: tab && tab.id,
      mode: "tab_fallback",
      detail: String(err && err.message ? err.message : err),
    };
  }
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
