/**
 * Format extract diagnostics for FAB error banners.
 * Depends on extract.js (window.__RA_FORMAT_EXTRACT_DIAG__ or job.diagnostics).
 */
(function () {
  function formatFromJob(job) {
    if (typeof window.__RA_FORMAT_EXTRACT_DIAG__ === "function") {
      return window.__RA_FORMAT_EXTRACT_DIAG__(job);
    }
    const d = job && job.diagnostics;
    if (!d) {
      const len = job && job.raw_text ? String(job.raw_text).trim().length : 0;
      return "仍读不到 JD（body_len=" + len + "）。扩展请 Reload ≥0.2.4 后 F5。";
    }
    return [
      "读不到可用 JD",
      "failure=" + d.failure,
      "layer=" + d.layer + " body_len=" + d.body_len,
      d.hint || "",
      "请点 Overview；扩展 Reload 后 F5。",
    ]
      .filter(Boolean)
      .join("\n");
  }

  window.__RA_FAB_DIAG__ = { formatFromJob };
})();
