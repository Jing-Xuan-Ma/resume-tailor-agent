/**
 * Write-intent tracking — infer "this next action publishes something".
 *
 * The MCP surface is coordinates-only by design, so `physical_click(x, y)`
 * carries no clue whether it lands on a bookmark icon or a Publish button.
 * Asking the agent to self-declare would make the gate advisory, and an
 * agent mid-task routes around advisory gates.
 *
 * So we infer from the input side instead: publishing is always preceded by
 * composing. Typing a meaningful amount of text arms the page; the next
 * click or Enter on that page is then treated as the submit and routed
 * through the gate. An agent cannot avoid arming it, because it cannot
 * publish without typing first.
 *
 * Deliberate limits:
 *   - Short typing (below writeIntentMinChars) does not arm. Search boxes
 *     would otherwise consume the write quota, and a search is not a post.
 *   - Intent expires. Typing a query, reading for ten minutes, then clicking
 *     a link is not a submit.
 */

import type { Page } from 'playwright-core';

import { logger } from '../util/logger.js';
import { writeIntentMinChars } from './budget.js';

/** How long an armed intent stays armed. */
const INTENT_TTL_MS = 5 * 60_000;

export interface WriteIntent {
  armedAt: number;
  chars: number;
  url: string;
}

// Keyed by Page so intents die with their tab; no manual cleanup needed.
const pending = new WeakMap<Page, WriteIntent>();

/**
 * Record that text was typed. Arms the submit gate when the volume suggests
 * composition rather than a query. Returns true when armed.
 */
export function noteTyping(page: Page, chars: number, url: string): boolean {
  const threshold = writeIntentMinChars();
  if (chars < threshold) return false;
  pending.set(page, { armedAt: Date.now(), chars, url });
  logger.info('write intent armed', { chars, threshold, url });
  return true;
}

function fresh(page: Page): WriteIntent | null {
  const intent = pending.get(page);
  if (!intent) return null;
  if (Date.now() - intent.armedAt > INTENT_TTL_MS) {
    pending.delete(page);
    logger.info('write intent expired', { armedAt: intent.armedAt, url: intent.url });
    return null;
  }
  return intent;
}

/** Is a submit pending on this page? Does not consume. */
export function peekWriteIntent(page: Page): WriteIntent | null {
  return fresh(page);
}

/** Take the pending intent, clearing it. Null when nothing is armed. */
export function consumeWriteIntent(page: Page): WriteIntent | null {
  const intent = fresh(page);
  if (intent) pending.delete(page);
  return intent;
}

/**
 * Put a consumed intent back, preserving its original arming time.
 *
 * Used when a submit was refused by a later gate: the action never happened,
 * so the composed text is still sitting in the field and the next attempt is
 * still a submit. The original `armedAt` is kept so a rejection loop cannot
 * extend the TTL indefinitely.
 */
export function restoreWriteIntent(page: Page, intent: WriteIntent): void {
  pending.set(page, intent);
}

/** Drop any pending intent, e.g. after navigating away. */
export function clearWriteIntent(page: Page): void {
  pending.delete(page);
}
