/**
 * Layered JD extraction for Jobright (shadow roots + same-origin iframes).
 * Layer 1: content scoring (Readability-lite)
 * Layer 2: known container selectors
 * Layer 3: deepText whole-page fallback
 * Loaded in all frames; FAB only mounts in top frame.
 */
(function () {
  const MIN_JD_LEN = 40;
  const GOOD_JD_LEN = 120;
  const STABLE_QUIET_MS = 400;
  const STABLE_TIMEOUT_MS = 6000;

  const NOISE_RE =
    /nav|menu|sidebar|aside|footer|header|share|social|advert|cookie|banner|toolbar|breadcrumb|recommend|related|popup|modal|toast/i;

  const LAYER2_SELECTORS = [
    "[data-ra-jd]",
    "article",
    "main",
    "[role='main']",
    ".posting-description",
    ".content-wrapper",
    ".job-description",
    "[class*='JobDescription']",
    "[class*='job-description']",
    "[class*='JobDetail']",
    "[class*='job-detail']",
    "[class*='Description']",
    ".description",
    ".post",
    ".article-body",
    ".content",
  ];

  function textOf(el, visibleOnly) {
    if (!el) return "";
    const raw = visibleOnly
      ? el.innerText || el.textContent || ""
      : el.textContent || el.innerText || "";
    return String(raw).replace(/\s+/g, " ").trim();
  }

  function isNoiseEl(el) {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return false;
    const tag = (el.tagName || "").toUpperCase();
    if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT" || tag === "SVG" || tag === "NAV") {
      return true;
    }
    if (tag === "ASIDE" || tag === "FOOTER" || tag === "HEADER") return true;
    const id = el.id || "";
    const cls = typeof el.className === "string" ? el.className : "";
    const role = el.getAttribute && (el.getAttribute("role") || "");
    if (NOISE_RE.test(id) || NOISE_RE.test(cls) || NOISE_RE.test(role)) return true;
    if (role === "navigation" || role === "banner" || role === "complementary") return true;
    return false;
  }

  /** Walk light DOM + open shadow roots (skips obvious chrome). */
  function deepText(root, budget) {
    let out = "";
    const limit = budget || 40000;
    function walk(node) {
      if (!node || out.length >= limit) return;
      if (node.nodeType === Node.TEXT_NODE) {
        const t = node.textContent || "";
        if (t.trim()) out += t + " ";
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE && node.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) {
        return;
      }
      const el = node;
      if (el.nodeType === Node.ELEMENT_NODE && isNoiseEl(el)) return;
      if (el.shadowRoot) walk(el.shadowRoot);
      const children = el.childNodes || [];
      for (let i = 0; i < children.length; i++) walk(children[i]);
    }
    try {
      walk(root);
    } catch (_) {
      /* ignore */
    }
    return out.replace(/\s+/g, " ").trim().slice(0, limit);
  }

  function collectSameOriginFrameText() {
    let merged = "";
    try {
      const frames = document.querySelectorAll("iframe");
      for (const frame of frames) {
        try {
          const doc = frame.contentDocument;
          if (!doc) continue;
          const t = deepText(doc.documentElement || doc.body);
          if (t.length > merged.length) merged = t;
        } catch (_) {
          /* cross-origin */
        }
      }
    } catch (_) {
      /* ignore */
    }
    return merged;
  }

  function absHref(a) {
    if (!a) return "";
    try {
      return new URL(a.getAttribute("href") || "", location.href).href;
    } catch (_) {
      return a.href || "";
    }
  }

  function isHttp(url) {
    return typeof url === "string" && /^https?:\/\//i.test(url);
  }

  function isJobrightHost(url) {
    return /jobright\.ai/i.test(url || "");
  }

  function isCompanyApplyHref(href) {
    if (!isHttp(href) || isJobrightHost(href)) return false;
    const u = href.toLowerCase();
    return (
      u.includes("utm_source=jobright") ||
      u.includes("greenhouse.io") ||
      u.includes("lever.co") ||
      u.includes("ashbyhq.com") ||
      u.includes("myworkdayjobs.com") ||
      u.includes("workday.com") ||
      u.includes("icims.com") ||
      u.includes("boards.") ||
      /\/jobs?\//i.test(u)
    );
  }

  function findExternalApply(root) {
    const scope = root || document;
    let anchors = [];
    try {
      anchors = Array.from(scope.querySelectorAll("a[href]"));
    } catch (_) {
      return "";
    }
    try {
      scope.querySelectorAll("*").forEach((el) => {
        if (el.shadowRoot) {
          anchors = anchors.concat(Array.from(el.shadowRoot.querySelectorAll("a[href]")));
        }
      });
    } catch (_) {
      /* ignore */
    }
    for (const a of anchors) {
      const label = textOf(a, true).toLowerCase();
      const href = absHref(a);
      if ((label.includes("apply") || label.includes("autofill")) && isCompanyApplyHref(href)) {
        return href;
      }
    }
    for (const a of anchors) {
      const href = absHref(a);
      if (isHttp(href) && /utm_source=jobright/i.test(href) && !isJobrightHost(href)) return href;
    }
    for (const a of anchors) {
      const label = textOf(a, true).toLowerCase();
      const href = absHref(a);
      if ((label.includes("apply") || label === "easy apply") && isHttp(href) && !isJobrightHost(href)) {
        return href;
      }
    }
    return "";
  }

  function firstHeading() {
    const sels = ["h1", "[data-ra-title]", "[class*='JobTitle']", "[class*='job-title']"];
    for (const sel of sels) {
      try {
        const el = document.querySelector(sel);
        if (el) {
          const t = textOf(el, true);
          if (t) return t;
        }
      } catch (_) {
        /* ignore */
      }
    }
    try {
      const all = document.querySelectorAll("*");
      for (const el of all) {
        if (!el.shadowRoot) continue;
        const h = el.shadowRoot.querySelector("h1");
        if (h) {
          const t = textOf(h, true);
          if (t) return t;
        }
      }
    } catch (_) {
      /* ignore */
    }
    return (document.title || "Untitled").split("|")[0].trim() || "Untitled";
  }

  function clickOverviewTab() {
    const wanted = ["overview", "job description", "description", "职位描述", "详情"];
    const nodes = [];
    function collect(root) {
      if (!root) return;
      try {
        root.querySelectorAll("button, a, [role='tab'], span, div").forEach((el) => nodes.push(el));
        root.querySelectorAll("*").forEach((el) => {
          if (el.shadowRoot) collect(el.shadowRoot);
        });
      } catch (_) {
        /* ignore */
      }
    }
    collect(document);
    for (const el of nodes) {
      const label = textOf(el, true).toLowerCase();
      if (!label || label.length > 48) continue;
      if (label === "overview" || label === "job description" || label === "职位描述") {
        try {
          el.click();
          return true;
        } catch (_) {
          /* ignore */
        }
      }
    }
    for (const el of nodes) {
      const label = textOf(el, true).toLowerCase();
      if (wanted.some((w) => label === w)) {
        try {
          el.click();
          return true;
        } catch (_) {
          /* ignore */
        }
      }
    }
    return false;
  }

  /**
   * Wait until DOM stops mutating (quietMs) or timeoutMs elapses.
   * Replaces "click then immediately read" for SPA rendering.
   */
  function waitForStableContent(opts) {
    const quietMs = (opts && opts.quietMs) || STABLE_QUIET_MS;
    const timeoutMs = (opts && opts.timeoutMs) || STABLE_TIMEOUT_MS;
    const root = (opts && opts.root) || document.documentElement || document.body;

    return new Promise((resolve) => {
      let settled = false;
      let quietTimer = null;
      const started = Date.now();

      function finish(reason) {
        if (settled) return;
        settled = true;
        try {
          observer.disconnect();
        } catch (_) {
          /* ignore */
        }
        if (quietTimer) clearTimeout(quietTimer);
        resolve({
          ok: reason === "quiet",
          reason,
          waited_ms: Date.now() - started,
        });
      }

      function bump() {
        if (settled) return;
        if (quietTimer) clearTimeout(quietTimer);
        quietTimer = setTimeout(() => finish("quiet"), quietMs);
      }

      let observer;
      try {
        observer = new MutationObserver(() => bump());
        observer.observe(root, {
          childList: true,
          subtree: true,
          characterData: true,
        });
      } catch (_) {
        finish("observe_failed");
        return;
      }

      bump();
      setTimeout(() => finish("timeout"), timeoutMs);
    });
  }

  function linkDensity(el) {
    const full = textOf(el, true);
    if (!full) return 1;
    let linkText = 0;
    try {
      el.querySelectorAll("a").forEach((a) => {
        linkText += textOf(a, true).length;
      });
    } catch (_) {
      /* ignore */
    }
    return linkText / Math.max(full.length, 1);
  }

  function sentenceBonus(text) {
    const parts = text.split(/[.!?。！？]/).filter((s) => s.trim().length > 20);
    return Math.min(parts.length, 12) * 15;
  }

  function jdKeywordBonus(text) {
    let score = 0;
    const lower = text.toLowerCase();
    const keys = [
      "responsibilities",
      "requirements",
      "qualifications",
      "about the role",
      "job description",
      "what you",
      "you will",
      "experience",
      "职位",
      "职责",
      "要求",
    ];
    for (const k of keys) {
      if (lower.includes(k)) score += 25;
    }
    return score;
  }

  function scoreBlock(el) {
    if (!el || isNoiseEl(el)) return -Infinity;
    const text = textOf(el, true);
    if (text.length < MIN_JD_LEN) return -Infinity;
    const density = linkDensity(el);
    let score = text.length * 0.35;
    score += sentenceBonus(text);
    score += jdKeywordBonus(text);
    score -= density * 800;
    if (density > 0.45) score -= 400;
    const tag = (el.tagName || "").toUpperCase();
    if (tag === "ARTICLE" || tag === "MAIN" || tag === "SECTION") score += 80;
    return score;
  }

  /** Collect candidate elements from light DOM + open shadows. */
  function collectCandidates(root, out) {
    if (!root) return;
    const tags = "p, div, section, article, main, li, span";
    try {
      root.querySelectorAll(tags).forEach((el) => {
        if (isNoiseEl(el)) return;
        const t = textOf(el, true);
        if (t.length >= MIN_JD_LEN && t.length <= 25000) out.push(el);
      });
      root.querySelectorAll("*").forEach((el) => {
        if (el.shadowRoot) collectCandidates(el.shadowRoot, out);
      });
    } catch (_) {
      /* ignore */
    }
  }

  function layer1Scored() {
    const candidates = [];
    collectCandidates(document, candidates);
    let best = null;
    let bestScore = -Infinity;
    for (const el of candidates) {
      const s = scoreBlock(el);
      if (s > bestScore) {
        bestScore = s;
        best = el;
      }
    }
    if (!best || bestScore < 0) {
      return { ok: false, text: "", score: bestScore, reason: "no_scored_block" };
    }
    const text = textOf(best, true);
    return {
      ok: text.length >= MIN_JD_LEN,
      text,
      score: bestScore,
      reason: text.length >= GOOD_JD_LEN ? "scored_good" : "scored_short",
      tag: (best.tagName || "").toLowerCase(),
    };
  }

  function queryAllDeep(selector) {
    const found = [];
    function walk(root) {
      if (!root) return;
      try {
        root.querySelectorAll(selector).forEach((el) => found.push(el));
        root.querySelectorAll("*").forEach((el) => {
          if (el.shadowRoot) walk(el.shadowRoot);
        });
      } catch (_) {
        /* ignore */
      }
    }
    walk(document);
    return found;
  }

  function layer2Containers() {
    let best = "";
    let hit = null;
    for (const sel of LAYER2_SELECTORS) {
      const els = queryAllDeep(sel);
      for (const el of els) {
        if (isNoiseEl(el)) continue;
        const t = textOf(el, true);
        if (t.length > best.length) {
          best = t;
          hit = sel;
        }
      }
      if (best.length >= GOOD_JD_LEN) break;
    }
    return {
      ok: best.length >= MIN_JD_LEN,
      text: best,
      selector: hit,
      reason: best.length >= GOOD_JD_LEN ? "container_good" : best ? "container_short" : "no_container",
    };
  }

  function layer3Deep() {
    const pageText = deepText(document.documentElement);
    const frameText = collectSameOriginFrameText();
    const raw = frameText.length > pageText.length ? frameText : pageText;
    return {
      ok: raw.length >= MIN_JD_LEN,
      text: raw,
      reason: raw.length >= GOOD_JD_LEN ? "deep_good" : raw ? "deep_short" : "deep_empty",
      from_frame: frameText.length > pageText.length,
    };
  }

  function runLayers() {
    const layers = {};
    const l1 = layer1Scored();
    layers.layer1_score = {
      ok: l1.ok,
      len: (l1.text || "").length,
      score: l1.score,
      reason: l1.reason,
      tag: l1.tag || null,
    };
    if (l1.ok && (l1.text || "").length >= GOOD_JD_LEN) {
      return { raw: l1.text, layer: "layer1_score", layers };
    }

    const l2 = layer2Containers();
    layers.layer2_containers = {
      ok: l2.ok,
      len: (l2.text || "").length,
      selector: l2.selector,
      reason: l2.reason,
    };
    if (l2.ok && (l2.text || "").length >= GOOD_JD_LEN) {
      return { raw: l2.text, layer: "layer2_containers", layers };
    }

    // Prefer longest among short-but-ok layer1/2 before deep paste
    let shortBest = "";
    let shortLayer = null;
    if (l1.ok && (l1.text || "").length > shortBest.length) {
      shortBest = l1.text;
      shortLayer = "layer1_score";
    }
    if (l2.ok && (l2.text || "").length > shortBest.length) {
      shortBest = l2.text;
      shortLayer = "layer2_containers";
    }

    const l3 = layer3Deep();
    layers.layer3_deep = {
      ok: l3.ok,
      len: (l3.text || "").length,
      reason: l3.reason,
    };

    if (shortBest.length >= MIN_JD_LEN && shortBest.length >= (l3.text || "").length * 0.55) {
      // Prefer cleaner short block over noisier deep dump when comparable
      if (shortBest.length >= GOOD_JD_LEN || shortBest.length > (l3.text || "").length * 0.35) {
        return { raw: shortBest, layer: shortLayer, layers };
      }
    }

    if (l3.ok) {
      return { raw: l3.text, layer: "layer3_deep", layers };
    }
    if (shortBest.length >= MIN_JD_LEN) {
      return { raw: shortBest, layer: shortLayer, layers };
    }
    return { raw: l3.text || shortBest || "", layer: "none", layers };
  }

  function classifyFailure(diag) {
    if (!diag) return "unknown";
    if (diag.wait && diag.wait.reason === "timeout" && (diag.body_len || 0) < MIN_JD_LEN) {
      return "page_not_rendered";
    }
    if ((diag.body_len || 0) > 0 && (diag.body_len || 0) < MIN_JD_LEN) {
      return "too_short_likely_sidebar";
    }
    if (diag.layer === "none" || (diag.body_len || 0) < MIN_JD_LEN) {
      return "shadow_or_cross_origin";
    }
    return "ok";
  }

  function buildDiagnostics(extra) {
    const wait = (extra && extra.wait) || null;
    const layered = (extra && extra.layered) || { raw: "", layer: "none", layers: {} };
    const bodyLen = (layered.raw || "").length;
    const diag = {
      layer: layered.layer,
      layers: layered.layers || {},
      wait: wait,
      body_len: bodyLen,
      overview_clicked: !!(extra && extra.overviewClicked),
      frame: window === window.top ? "top" : "iframe",
      href: String(location.href || "").slice(0, 240),
    };
    diag.failure = classifyFailure(diag);
    diag.hint =
      diag.failure === "page_not_rendered"
        ? "等待 DOM 稳定超时，内容可能未渲染（登录墙/新布局）"
        : diag.failure === "too_short_likely_sidebar"
          ? "抓到的文本过短，可能命中侧栏而非 JD 正文"
          : diag.failure === "shadow_or_cross_origin"
            ? "三层策略都未找到足够正文（可能在 Shadow DOM / 跨域 iframe）"
            : "ok";
    return diag;
  }

  function extractJob(options) {
    const pageUrl = String(location.href || "").trim();
    const layered = runLayers();
    let raw = layered.raw || "";

    const title = firstHeading();
    let company = "";
    try {
      const c = document.querySelector("[data-ra-company], [data-testid='job-company']");
      if (c) company = c.getAttribute("data-ra-company") || textOf(c, true);
    } catch (_) {
      /* ignore */
    }

    // Heuristic company from title line patterns in scored text
    if (!company && raw) {
      const m = raw.match(/\bat\s+([A-Z][\w&.,' -]{1,60})/);
      if (m) company = m[1].trim();
    }

    const applyHref = findExternalApply(document);
    if ((raw || "").length < MIN_JD_LEN && title) {
      raw = `${title}\n${company}\n${raw || ""}`.trim();
    }

    const diagnostics = buildDiagnostics({
      wait: options && options.wait,
      layered: { ...layered, raw },
      overviewClicked: options && options.overviewClicked,
    });

    return {
      title: title || "Untitled",
      company: company || "Unknown Company",
      location: null,
      raw_text: raw || "",
      source_url: applyHref || pageUrl,
      jobright_url: pageUrl,
      apply_url: applyHref || null,
      page_url: pageUrl,
      has_external_apply: !!applyHref && !isJobrightHost(applyHref),
      extracted_at: new Date().toISOString(),
      body_len: (raw || "").length,
      frame: window === window.top ? "top" : "iframe",
      extract_layer: layered.layer,
      diagnostics,
    };
  }

  async function extractReady() {
    const overviewClicked = clickOverviewTab();
    const wait1 = await waitForStableContent({ quietMs: STABLE_QUIET_MS, timeoutMs: STABLE_TIMEOUT_MS });
    // Second pass: some JR layouts need another Overview nudge after first paint
    const overviewClicked2 = clickOverviewTab();
    const wait2 = await waitForStableContent({
      quietMs: STABLE_QUIET_MS,
      timeoutMs: Math.min(3000, STABLE_TIMEOUT_MS),
    });
    return extractJob({
      overviewClicked: overviewClicked || overviewClicked2,
      wait: {
        pass1: wait1,
        pass2: wait2,
        reason: wait2.reason === "quiet" || wait1.reason === "quiet" ? "quiet" : wait2.reason || wait1.reason,
        waited_ms: (wait1.waited_ms || 0) + (wait2.waited_ms || 0),
      },
    });
  }

  function formatDiagnosticsMessage(job) {
    const d = job && job.diagnostics;
    if (!d) {
      return "仍读不到 JD（无 diagnostics）。请 Reload 扩展到最新版后 F5。";
    }
    const lines = [
      "读不到可用 JD",
      "failure=" + d.failure,
      "layer=" + d.layer + " body_len=" + d.body_len,
      d.hint || "",
    ];
    if (d.wait) {
      lines.push("wait=" + d.wait.reason + " (" + d.wait.waited_ms + "ms)");
    }
    const L = d.layers || {};
    if (L.layer1_score) {
      lines.push(
        "L1 score: ok=" +
          L.layer1_score.ok +
          " len=" +
          L.layer1_score.len +
          " (" +
          L.layer1_score.reason +
          ")"
      );
    }
    if (L.layer2_containers) {
      lines.push(
        "L2 container: ok=" +
          L.layer2_containers.ok +
          " len=" +
          L.layer2_containers.len +
          (L.layer2_containers.selector ? " sel=" + L.layer2_containers.selector : "")
      );
    }
    if (L.layer3_deep) {
      lines.push("L3 deep: ok=" + L.layer3_deep.ok + " len=" + L.layer3_deep.len);
    }
    lines.push("请确认已打开职位详情 Overview；扩展 Reload 后 F5。");
    return lines.filter(Boolean).join("\n");
  }

  function publish() {
    const job = extractJob({ wait: null, overviewClicked: false });
    window.__RA_JOBRIGHT_EXTRACT__ = job;
    try {
      if (window === window.top && typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage({ type: "ra_job_extracted", job });
      }
    } catch (_) {
      /* ignore */
    }
    return job;
  }

  try {
    if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
      chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
        if (!msg || !msg.type) return false;
        if (msg.type === "ra_extract_now") {
          extractReady()
            .then((job) => sendResponse({ ok: true, job }))
            .catch((e) => sendResponse({ ok: false, error: String(e) }));
          return true;
        }
        if (msg.type === "ra_extract_sync") {
          sendResponse({ ok: true, job: extractJob() });
          return false;
        }
        return false;
      });
    }
  } catch (_) {
    /* non-extension context */
  }

  window.__RA_EXTRACT_NOW__ = extractJob;
  window.__RA_EXTRACT_READY__ = extractReady;
  window.__RA_FORMAT_EXTRACT_DIAG__ = formatDiagnosticsMessage;
  publish();
})();
