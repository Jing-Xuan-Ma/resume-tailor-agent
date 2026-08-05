/**
 * On Resume Agent pages: wire "← Jobright" to focus the original Jobright tab.
 */
(function () {
  function markFocused() {
    document.documentElement.dataset.raJobrightFocused = "1";
  }

  function requestFocus(returnTo) {
    try {
      chrome.runtime.sendMessage(
        { type: "ra_focus_jobright", returnUrl: returnTo || null },
        (res) => {
          if (res && res.ok) markFocused();
        }
      );
    } catch (_) {
      /* extension missing */
    }
  }

  window.addEventListener("ra-focus-jobright", (ev) => {
    const detail = (ev && ev.detail) || {};
    requestFocus(detail.returnTo);
  });

  // Also expose a small floating control if header is not ready yet.
  function ensureFab() {
    const params = new URLSearchParams(location.search);
    const returnTo = params.get("returnTo");
    const isResume = params.get("view") === "resume" || params.has("jobId");
    if (!isResume) return;
    // Prefer the in-app header button when present.
    if (document.querySelector("[data-testid=back-to-jobright]")) {
      const existing = document.getElementById("ra-back-jobright-fab");
      if (existing) existing.remove();
      return;
    }
    if (document.getElementById("ra-back-jobright-fab")) return;

    const btn = document.createElement("button");
    btn.id = "ra-back-jobright-fab";
    btn.type = "button";
    btn.textContent = "← Jobright";
    btn.setAttribute("data-testid", "ra-back-jobright-fab");
    Object.assign(btn.style, {
      position: "fixed",
      left: "16px",
      bottom: "20px",
      zIndex: "2147483646",
      border: "1px solid #a7f3d0",
      borderRadius: "999px",
      padding: "10px 14px",
      background: "#ecfdf5",
      color: "#065f46",
      font: "600 12px/1.2 system-ui,sans-serif",
      boxShadow: "0 6px 18px rgba(6,95,70,0.18)",
      cursor: "pointer",
    });
    btn.addEventListener("click", () => {
      requestFocus(returnTo);
      window.setTimeout(() => {
        if (!document.documentElement.dataset.raJobrightFocused && returnTo) {
          location.href = returnTo;
        }
      }, 400);
    });
    document.documentElement.appendChild(btn);
  }

  ensureFab();
  setInterval(ensureFab, 2000);
})();
