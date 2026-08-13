/**
 * Phase 3 — Physical keyboard.
 *
 * Like the cursor, this never accepts a selector. The AI agent decides
 * WHICH field has focus (via the A11y tree + physical_click to focus),
 * then calls physical_type with raw text. We type character-by-character
 * with Gaussian-random inter-key delay so timing signatures look human.
 *
 * Why not `page.keyboard.type(text, {delay})`? That function's `delay`
 * is constant — every character waits the same N ms. Real humans do not.
 * We use an AR(1) Gaussian process that produces correlated delays:
 * short delays cluster into "burst" sequences, with occasional longer
 * "thinking pauses" — matching real keystroke autocorrelation.
 */

import type { Page } from 'playwright-core';

import { logger } from '../util/logger.js';
import { gaussianInt, createArJitter } from './rand.js';

export const TYPE_DELAY_MIN_MS = 50;
export const TYPE_DELAY_MAX_MS = 200;
/** Cap for short fields (title/summary/tag search). Long body → write_clipboard + paste. */
export const MAX_TYPE_CHARS = 8000;

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/** Platform-appropriate modifier for "select all" in focused inputs. */
function selectAllModifier(): 'Meta' | 'Control' {
  return process.platform === 'darwin' ? 'Meta' : 'Control';
}

/**
 * Select all text in the currently-focused input/textarea via
 * Meta+A (macOS) or Control+A (Windows/Linux).
 */
export async function selectAllInFocusedField(page: Page): Promise<void> {
  const mod = selectAllModifier();
  await page.keyboard.press(`${mod}+a`);
}

/**
 * Type text into the page's currently-focused element, one character at
 * a time, with a Gaussian-random delay between each.
 *
 * Delays are autocorrelated (AR-1, ρ=0.3) so consecutive key timings form
 * natural bursts — a statistical pattern that distinguishes human typing
 * from independent per-key random draws.
 *
 * Newlines are routed through `keyboard.press('Enter')` because
 * Playwright's `type()` splits on '\n' and types a literal newline
 * event which some inputs handle differently than Enter.
 *
 * The function is silent about focus: the caller is responsible for
 * having clicked into a focusable element first (e.g. via physical_click
 * on the field's centre from the A11y tree).
 */
export interface TypeTextOptions {
  minDelayMs?: number;
  maxDelayMs?: number;
  /** Select all in the focused field before typing (replaces existing text). */
  replace?: boolean;
}

/**
 * Press a key chord via Playwright keyboard (e.g. "Meta+c", "Control+a").
 * Used for copy/paste shortcuts after focusing the target element.
 */
export async function pressKeys(page: Page, keys: string): Promise<void> {
  if (typeof keys !== 'string' || !keys.trim()) {
    throw new Error('pressKeys: keys must be a non-empty string');
  }
  await page.keyboard.press(keys.trim());
  logger.info('physical_keypress complete', { keys: keys.trim() });
}

export async function typeText(
  page: Page,
  text: string,
  opts: TypeTextOptions = {},
): Promise<number> {
  if (typeof text !== 'string') {
    throw new Error(`typeText: text must be a string, got ${typeof text}`);
  }
  if (text.length > MAX_TYPE_CHARS) {
    throw new Error(
      `typeText: text length ${text.length} exceeds cap of ${MAX_TYPE_CHARS}`,
    );
  }

  const minDelay = opts.minDelayMs ?? TYPE_DELAY_MIN_MS;
  const maxDelay = opts.maxDelayMs ?? TYPE_DELAY_MAX_MS;

  if (opts.replace) {
    await selectAllInFocusedField(page);
    await sleep(gaussianInt(50, 150));
  }

  const jitter = createArJitter(minDelay, maxDelay);

  let typed = 0;
  for (const ch of text) {
    if (ch === '\n') {
      await page.keyboard.press('Enter');
    } else {
      await page.keyboard.type(ch);
    }
    typed += 1;
    // No delay after the last character.
    if (typed < text.length) {
      await sleep(jitter.next());
    }
  }

  if (typed > 0) {
    logger.info('physical_type complete', { chars: typed });
  }
  return typed;
}
