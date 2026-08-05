/** Resolve logged-in user id from localStorage auth blob. */
export const FALLBACK_USER_ID = "00000000-0000-0000-0000-0000000000a1";

export function getAuthUserId(): string {
  if (typeof window === "undefined") return FALLBACK_USER_ID;
  try {
    const raw = localStorage.getItem("resume-agent-auth");
    if (!raw) return FALLBACK_USER_ID;
    const parsed = JSON.parse(raw) as { user?: { id?: string } };
    return String(parsed?.user?.id || FALLBACK_USER_ID);
  } catch {
    return FALLBACK_USER_ID;
  }
}
