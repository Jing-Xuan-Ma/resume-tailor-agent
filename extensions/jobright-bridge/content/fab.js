/**
 * Floating workbench on Jobright: Tailor / Apply / Outreach (primary entry).
 */
(function () {
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
    btn.addEventListener("click", () => {
      const prev = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Opening…";
      try {
        chrome.runtime.sendMessage({ type: messageType }, (res) => {
          btn.disabled = false;
          btn.textContent = prev;
          if (!res || !res.ok) {
            btn.title = (res && res.error) || "Failed";
          }
        });
      } catch (_) {
        btn.disabled = false;
        btn.textContent = prev;
      }
    });
    return btn;
  }

  wrap.appendChild(makeBtn("Open Tailor", "ra-fab-tailor", "#047857", "ra_open_tailor"));
  wrap.appendChild(makeBtn("Open Apply", "ra-fab-apply", "#0f172a", "ra_open_apply"));
  wrap.appendChild(makeBtn("Open Outreach", "ra-fab-outreach", "#1d4ed8", "ra_open_outreach"));
  document.documentElement.appendChild(wrap);
})();
