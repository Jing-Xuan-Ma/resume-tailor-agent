/**
 * Extract job fields from a Jobright-like detail page.
 * Selectors are centralized; update here when Jobright DOM changes.
 * Also supports data-ra-* attributes on the local mock fixture.
 *
 * Critical: Jobright's Apply button already points at the company ATS
 * (Greenhouse / Lever / Workday / …, often with utm_source=jobright).
 * We must capture THAT href and store it as apply_url — do not invent Indeed links.
 */
(function () {
  function textOf(el) {
    return (el && (el.innerText || el.textContent) || "").replace(/\s+/g, " ").trim();
  }

  function first(selectors) {
    for (const sel of selectors) {
      try {
        const el = document.querySelector(sel);
        if (el) return el;
      } catch (_) {
        /* ignore bad selector */
      }
    }
    return null;
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

  /** Company ATS / career apply — same destination Jobright Apply opens. */
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
      u.includes("smartrecruiters.com") ||
      u.includes("jobvite.com") ||
      u.includes("bamboohr.com") ||
      u.includes("applytojob.com") ||
      u.includes("boards.") ||
      /\/jobs?\//i.test(u)
    );
  }

  /**
   * Prefer the exact company Apply link Jobright surfaces.
   * Order: data-ra / greenhouse… / utm_source=jobright / labeled Apply leaving jobright.
   */
  function findExternalApply() {
    const selectors = [
      "a[data-ra-apply]",
      "a[data-testid='apply-link']",
      "a[href*='utm_source=jobright']",
      "a[href*='greenhouse.io']",
      "a[href*='lever.co']",
      "a[href*='ashbyhq.com']",
      "a[href*='myworkdayjobs.com']",
      "a[href*='boards.']",
      "a[href*='jobs.']",
    ];
    for (const sel of selectors) {
      const el = first([sel]);
      const href = absHref(el);
      if (isCompanyApplyHref(href)) return href;
    }

    const anchors = Array.from(document.querySelectorAll("a[href]"));
    // 1) Explicit Apply label → company ATS
    for (const a of anchors) {
      const label = textOf(a).toLowerCase();
      if (!(label.includes("apply") || label === "easy apply")) continue;
      const href = absHref(a);
      if (isCompanyApplyHref(href)) return href;
    }
    // 2) Any utm_source=jobright (Jobright stamped company link)
    for (const a of anchors) {
      const href = absHref(a);
      if (isHttp(href) && /utm_source=jobright/i.test(href) && !isJobrightHost(href)) {
        return href;
      }
    }
    // 3) Apply label that leaves Jobright (even if host is unfamiliar)
    for (const a of anchors) {
      const label = textOf(a).toLowerCase();
      if (!(label.includes("apply") || label === "easy apply")) continue;
      const href = absHref(a);
      if (isHttp(href) && !isJobrightHost(href)) return href;
    }
    // 4) Jobright-hosted Apply redirect — browser follows to company ATS
    for (const a of anchors) {
      const label = textOf(a).toLowerCase();
      if (!(label.includes("apply") || label === "easy apply")) continue;
      const href = absHref(a);
      if (isHttp(href) && isJobrightHost(href)) return href;
    }
    return "";
  }

  function extractJob() {
    const pageUrl = String(location.href || "").trim();
    const titleEl = first([
      "[data-ra-title]",
      "h1[data-testid='job-title']",
      "[class*='JobDetail'] h1",
      "main h1",
      "h1",
    ]);
    const companyEl = first([
      "[data-ra-company]",
      "[data-testid='job-company']",
      "[class*='company']",
      "main h1 + *",
    ]);
    const locationEl = first([
      "[data-ra-location]",
      "[data-testid='job-location']",
      "[class*='location']",
    ]);
    const jdEl = first([
      "[data-ra-jd]",
      "[data-testid='job-description']",
      "[class*='JobDescription']",
      "article",
      "main",
    ]);

    const title = textOf(titleEl) || document.title || "Untitled";
    let company = textOf(companyEl);
    if (companyEl && companyEl.getAttribute && companyEl.getAttribute("data-ra-company")) {
      company = companyEl.getAttribute("data-ra-company") || company;
    }
    const location = textOf(locationEl);
    const raw_text = textOf(jdEl);
    const applyHref = findExternalApply();
    // source_url for apply = Jobright's company Apply link whenever present
    const source_url = applyHref || pageUrl;
    const jobright_url = pageUrl;

    return {
      title,
      company: company || "Unknown Company",
      location: location || null,
      raw_text,
      source_url,
      jobright_url,
      apply_url: applyHref || null,
      page_url: pageUrl,
      has_external_apply: !!applyHref && !isJobrightHost(applyHref),
      extracted_at: new Date().toISOString(),
      body_len: (raw_text || "").length,
    };
  }

  function publish() {
    const job = extractJob();
    window.__RA_JOBRIGHT_EXTRACT__ = job;
    try {
      chrome.runtime.sendMessage({ type: "ra_job_extracted", job });
    } catch (_) {
      /* extension context may be missing on plain file open */
    }
    return job;
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg && msg.type === "ra_extract_now") {
      sendResponse({ ok: true, job: publish() });
      return true;
    }
    return false;
  });

  publish();
  const mo = new MutationObserver(() => {
    clearTimeout(window.__RA_EXTRACT_TIMER__);
    window.__RA_EXTRACT_TIMER__ = setTimeout(publish, 400);
  });
  mo.observe(document.documentElement, { childList: true, subtree: true });
})();
