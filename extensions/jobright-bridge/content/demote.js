/**
 * Soft-demote Jobright list cards after user opens Tailor/Apply from this page.
 * Marks the current detail URL in session so list rows can grey out.
 */
(function () {
  const KEY = "ra_processed_job_urls";

  function load() {
    try {
      return JSON.parse(sessionStorage.getItem(KEY) || "[]");
    } catch (_) {
      return [];
    }
  }

  function save(list) {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(list.slice(-80)));
    } catch (_) {
      /* ignore */
    }
  }

  function markCurrent() {
    const url = location.href.split("#")[0];
    if (!/jobright\.ai|jobright-mock/i.test(url)) return;
    const list = load();
    if (!list.includes(url)) {
      list.push(url);
      save(list);
    }
  }

  function dimProcessed() {
    const list = new Set(load());
    if (!list.size) return;
    const anchors = document.querySelectorAll("a[href]");
    anchors.forEach((a) => {
      try {
        const href = a.href.split("#")[0];
        if (!list.has(href)) return;
        const card = a.closest("article, [class*='card'], [class*='Card'], li, tr") || a;
        card.style.opacity = "0.45";
        card.setAttribute("data-ra-processed", "1");
      } catch (_) {
        /* ignore */
      }
    });
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.type === "ra_mark_processed") {
      markCurrent();
      dimProcessed();
    }
  });

  // After Tailor/Apply/Outreach open, background may not message — mark on FAB use via storage poll
  markCurrent();
  dimProcessed();
  setInterval(dimProcessed, 4000);
})();
