/** True for real http(s) posting URLs. Mocks use empty originalUrl. */
export function isLivePostingUrl(url?: string | null) {
  const raw = (url || "").trim();
  if (!raw || !/^https?:\/\//i.test(raw)) return false;

  let host = "";
  try {
    host = new URL(raw).hostname.toLowerCase();
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

  return true;
}
