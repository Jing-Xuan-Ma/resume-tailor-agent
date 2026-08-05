async function refreshReview() {
  const { lastReview } = await chrome.storage.local.get("lastReview");
  const el = document.getElementById("review");
  if (!lastReview) {
    el.textContent = "尚无复核摘要";
    return;
  }
  el.textContent = `[${lastReview.stage || ""}]\n${lastReview.summary || ""}`;
}

function setStatus(text) {
  document.getElementById("review").textContent = text;
}

document.getElementById("refresh").addEventListener("click", refreshReview);

document.getElementById("openTailor").addEventListener("click", () => {
  setStatus("Opening Tailor…");
  chrome.runtime.sendMessage({ type: "ra_open_tailor" }, (resp) => {
    setStatus(resp?.ok ? "Tailor window opened." : resp?.error || "Open Tailor failed");
  });
});

document.getElementById("openApply").addEventListener("click", () => {
  setStatus("Opening Apply workspace…");
  chrome.runtime.sendMessage({ type: "ra_open_apply" }, (resp) => {
    setStatus(resp?.ok ? "Apply workspace opened." : resp?.error || "Open Apply failed");
  });
});

document.getElementById("openFill").addEventListener("click", async () => {
  const url = document.getElementById("url").value.trim();
  if (!url) {
    setStatus("请填写 Apply URL");
    return;
  }
  const { applyProfile } = await chrome.storage.local.get({ applyProfile: {} });
  chrome.runtime.sendMessage(
    {
      action: "openAndFill",
      url,
      jobId: `ext-${Date.now()}`,
      profile: applyProfile,
    },
    (resp) => {
      setStatus(resp?.ok ? `已打开 tab ${resp.tabId}，等待 Engine…` : "打开失败");
    }
  );
});

refreshReview();
