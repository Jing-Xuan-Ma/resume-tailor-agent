/**
 * Top-frame FAB. Uses layered extract; if empty, asks background to scrape all frames.
 * Surfaces diagnostics.failure so "Agent 打不开" is actionable.
 */
(function () {
  if (window !== window.top) return;
  if (document.getElementById("ra-jobright-fab")) return;

  const wrap = document.createElement("div");
  wrap.id = "ra-jobright-fab";
  wrap.setAttribute("data-testid", "ra-jobright-fab");
  Object.assign(wrap.style, {
    position: "fixed",
    right: "16px",
    bottom: "20px",
    zIndex: "2147483646",
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    alignItems: "stretch",
  });

  function showError(text) {
    let banner = document.getElementById("ra-jobright-fab-error");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "ra-jobright-fab-error";
      Object.assign(banner.style, {
        position: "fixed",
        right: "16px",
        bottom: "170px",
        zIndex: "2147483647",
        maxWidth: "340px",
        padding: "10px 12px",
        borderRadius: "10px",
        background: "#7f1d1d",
        color: "#fff",
        font: "600 12px/1.35 system-ui,sans-serif",
        boxShadow: "0 8px 24px rgba(15,23,42,0.28)",
        whiteSpace: "pre-wrap",
      });
      document.documentElement.appendChild(banner);
    }
    banner.textContent = text || "Failed";
    clearTimeout(banner.__hideTimer);
    banner.__hideTimer = setTimeout(() => {
      if (banner && banner.parentNode) banner.parentNode.removeChild(banner);
    }, 16000);
  }

  function bodyLen(job) {
    return job && job.raw_text ? String(job.raw_text).trim().length : 0;
  }

  function formatDiag(job) {
    try {
      if (window.__RA_FAB_DIAG__ && typeof window.__RA_FAB_DIAG__.formatFromJob === "function") {
        return window.__RA_FAB_DIAG__.formatFromJob(job);
      }
      if (typeof window.__RA_FORMAT_EXTRACT_DIAG__ === "function") {
        return window.__RA_FORMAT_EXTRACT_DIAG__(job);
      }
    } catch (_) {
      /* ignore */
    }
    return "仍读不到 JD（body_len=" + bodyLen(job) + "）。扩展 Reload ≥0.2.4 后 F5。";
  }

  async function readJobLocal() {
    try {
      if (typeof window.__RA_EXTRACT_READY__ === "function") {
        return await window.__RA_EXTRACT_READY__();
      }
      if (typeof window.__RA_EXTRACT_NOW__ === "function") {
        return window.__RA_EXTRACT_NOW__();
      }
    } catch (_) {
      /* ignore */
    }
    return window.__RA_JOBRIGHT_EXTRACT__ || null;
  }

  function scrapeFallbackViaBackground() {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "ra_scrape_active_tab", force: true }, (res) => {
          if (chrome.runtime.lastError) {
            resolve({ ok: false, error: chrome.runtime.lastError.message });
            return;
          }
          resolve(res || { ok: false, error: "no_response" });
        });
      } catch (e) {
        resolve({ ok: false, error: String(e && e.message ? e.message : e) });
      }
    });
  }

  function openWithJob(messageType, job, btn, prev) {
    chrome.runtime.sendMessage(
      {
        type: messageType,
        force: true,
        job,
        pageUrl: location.href,
      },
      (res) => {
        const err = chrome.runtime.lastError;
        btn.disabled = false;
        btn.textContent = prev;
        if (err) {
          showError("扩展需重新加载（版本 ≥0.2.4）并 F5。\n" + err.message);
          return;
        }
        if (!res || !res.ok) {
          showError((res && res.error) || "打开失败：后端 :8000 是否在跑？");
        }
      }
    );
  }

  function makeBtn(label, testId, bg, messageType) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    btn.setAttribute("data-testid", testId);
    Object.assign(btn.style, {
      border: "none",
      borderRadius: "999px",
      padding: "11px 14px",
      background: bg,
      color: "#fff",
      font: "600 12px/1.2 system-ui,sans-serif",
      boxShadow: "0 8px 24px rgba(15,23,42,0.22)",
      cursor: "pointer",
      whiteSpace: "nowrap",
    });
    btn.addEventListener("click", async () => {
      const prev = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Opening…";

      let job = await readJobLocal();
      if (bodyLen(job) < 80) {
        const scraped = await scrapeFallbackViaBackground();
        if (scraped && scraped.ok && scraped.job && bodyLen(scraped.job) >= 40) {
          job = scraped.job;
        } else if (scraped && scraped.ok && scraped.opened) {
          btn.disabled = false;
          btn.textContent = prev;
          return;
        }
      }

      if (bodyLen(job) < 40) {
        btn.disabled = false;
        btn.textContent = prev;
        showError(formatDiag(job));
        return;
      }

      try {
        openWithJob(messageType, job, btn, prev);
      } catch (e) {
        btn.disabled = false;
        btn.textContent = prev;
        showError(String(e && e.message ? e.message : e));
      }
    });
    return btn;
  }

  wrap.appendChild(makeBtn("Open Tailor", "ra-fab-tailor", "#047857", "ra_open_tailor"));
  wrap.appendChild(makeBtn("Open Apply", "ra-fab-apply", "#0f172a", "ra_open_apply"));
  wrap.appendChild(makeBtn("Open Outreach", "ra-fab-outreach", "#1d4ed8", "ra_open_outreach"));
  document.documentElement.appendChild(wrap);
})();
