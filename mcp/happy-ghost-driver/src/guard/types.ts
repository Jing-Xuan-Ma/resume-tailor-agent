/**
 * Shared vocabulary for the account-safety guards.
 *
 * The guards answer one question: "does this action keep the session inside
 * the envelope a real person would produce?" That needs two axes — what the
 * action mechanically is (ActionType) and how much account risk it carries
 * (WriteClass) — because a scroll and a comment submit are both "a click or
 * two" mechanically but worlds apart in consequence.
 */

/** The mechanical action performed. Mirrors the physical_* tool surface. */
export type ActionType = 'click' | 'type' | 'keypress' | 'scroll' | 'navigate' | 'submit';

/**
 * Risk tier, which is what quotas are actually keyed on.
 *
 *   read  — pure consumption: scrolling, navigating, reading.
 *   light — interaction that touches the page but produces no content:
 *           clicks, focusing a field, typing into it, copy shortcuts.
 *   write — content leaves your account and becomes visible to others:
 *           posting, commenting, DMing. Irreversible, and the tier a
 *           platform's risk model weighs most heavily.
 */
export type WriteClass = 'read' | 'light' | 'write';

export const WRITE_CLASSES: readonly WriteClass[] = ['read', 'light', 'write'];

/** One recorded action in the ledger. */
export interface LedgerEntry {
  ts: number;
  domain: string;
  actionType: ActionType;
  writeClass: WriteClass;
  url: string;
  /** Short, non-sensitive note (e.g. "chars=42"). Never the typed content. */
  detail: string | null;
}

export interface LedgerCountQuery {
  domain?: string;
  writeClass?: WriteClass;
  sinceTs: number;
}

/** Why an action was refused. Surfaced to the agent as a structured error. */
export interface GuardRejection {
  error: 'budget_exceeded' | 'not_foreground' | 'night_guard';
  /** Human-readable explanation, written for the operator, not the model. */
  message: string;
  /** Machine-usable context so an agent can decide to back off vs retry. */
  detail?: Record<string, unknown>;
}

/**
 * Extract a registrable-ish domain for quota grouping: "www.xiaohongshu.com"
 * and "creator.xiaohongshu.com" must share one budget, because they share
 * one account.
 *
 * This is deliberately not a public-suffix-list implementation. It collapses
 * to the last two labels, which is correct for the .com/.cn/.io hosts we
 * target and degrades to "the whole host" for anything unusual — a grouping
 * error here can only ever make quotas stricter, never looser, for the
 * multi-part TLDs (e.g. com.cn) where it over-collapses.
 */
export function domainOf(url: string): string {
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (!host) return 'unknown';
    const labels = host.split('.').filter((l) => l.length > 0);
    if (labels.length <= 2) return host;
    return labels.slice(-2).join('.');
  } catch {
    return 'unknown';
  }
}
