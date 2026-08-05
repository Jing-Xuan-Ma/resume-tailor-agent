/** True for real http(s) posting URLs. Mocks use empty originalUrl. */
export function isLivePostingUrl(url?: string | null) {
  const raw = (url || "").trim();
  if (!raw || !/^https?:\/\//i.test(raw)) return false;
  // Indeed/JobSpy markdown escapes break the host (rb.wd5\.myworkday… → connection closed).
  if (raw.includes("\\")) return false;

  let host = "";
  let path = "";
  try {
    const u = new URL(raw);
    host = u.hostname.toLowerCase();
    path = u.pathname || "";
  } catch {
    return false;
  }

  // Explicit demo / placeholder hosts only — do not block real ATS or LinkedIn.
  if (
    host === "example.com" ||
    host.endsWith(".example.com") ||
    host === "localhost" ||
    host === "127.0.0.1"
  ) {
    return false;
  }

  // Thin Workday career roots (e.g. /FRS) often ERR_CONNECTION_CLOSED — not a job page.
  if (host.includes("myworkdayjobs.com") || host.endsWith(".workday.com")) {
    const parts = path.split("/").filter(Boolean);
    const lower = parts.map((p) => p.toLowerCase());
    if (lower.includes("job")) return true;
    if (lower.some((p) => p.startsWith("jr") || p.startsWith("r-"))) return true;
    if (parts.length >= 3) return true;
    return false;
  }

  return true;
}

/** Prefer a URL that will actually load in the browser. */
export function pickOpenablePostingUrl(
  sourceUrl?: string | null,
  boardUrl?: string | null
): string | null {
  if (isLivePostingUrl(sourceUrl)) return String(sourceUrl).trim();
  if (isLivePostingUrl(boardUrl)) return String(boardUrl).trim();
  return null;
}
