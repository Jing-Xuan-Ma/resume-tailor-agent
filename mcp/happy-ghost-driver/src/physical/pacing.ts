/**
 * Session-level pacing — the macro rhythm that cooldown.ts cannot provide.
 *
 * cooldown.ts puts 1-3s around each action, which makes an individual click
 * look human. It does nothing about the shape of an hour: a real person
 * pauses to actually read what they opened, drifts back up a feed they
 * scrolled past, and stops for minutes at a time. Without that, the session
 * reads as "microscopically human, macroscopically a script" — and the
 * macro shape is what a platform's risk model actually sees.
 *
 * All of this is bounded and opt-out (`PACING_ENABLED=0`) because it trades
 * wall-clock time for realism, and only applies when a real page is driving.
 */

import type { Page } from 'playwright-core';

import { logger } from '../util/logger.js';
import { gaussianInt } from './rand.js';
import type { ScrollDirection } from './scroll.js';

const DEFAULT_READING_DWELL_MAX_MS = 12_000;
const READING_DWELL_MIN_MS = 1_200;
/** Skim model: a fixed orientation cost plus time proportional to length. */
const READING_BASE_MS = 800;
const READING_MS_PER_CHAR = 8;

const DEFAULT_REST_EVERY = 40;
const DEFAULT_REST_MIN_MS = 60_000;
const DEFAULT_REST_MAX_MS = 300_000;

const DEFAULT_REVERSE_SCROLL_PROB = 0.15;
/** A drift back up is a glance, not a re-read. */
const REVERSE_SCROLL_MIN_PX = 80;
const REVERSE_SCROLL_MAX_FRACTION = 0.35;

function envInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === '') return fallback;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) return fallback;
  return Math.round(n);
}

function envFloat(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === '') return fallback;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) return fallback;
  return n;
}

export function pacingEnabled(): boolean {
  const raw = process.env.PACING_ENABLED;
  if (raw === undefined) return true;
  const v = raw.trim().toLowerCase();
  return !(v === '0' || v === 'false' || v === 'no');
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Pause as if reading the page that was just opened, scaled to how much text
 * it actually contains. Returns the ms actually slept (0 when skipped).
 */
export async function readingDwell(page: Page): Promise<number> {
  if (!pacingEnabled()) return 0;
  const maxMs = envInt('READING_DWELL_MAX_MS', DEFAULT_READING_DWELL_MAX_MS);
  if (maxMs <= 0) return 0;

  let chars = 0;
  try {
    // String form avoids requiring the DOM lib in tsconfig.
    chars = (await page.evaluate(
      'document.body ? document.body.innerText.length : 0',
    )) as number;
  } catch {
    // A page that will not report its own length still deserves a pause;
    // fall through with chars = 0 and take the floor.
  }

  const target = READING_BASE_MS + chars * READING_MS_PER_CHAR;
  const clamped = Math.min(maxMs, Math.max(READING_DWELL_MIN_MS, target));
  // Jitter so identical pages do not produce identical dwell times.
  const ms = gaussianInt(Math.round(clamped * 0.7), clamped);
  logger.info('pacing: reading dwell', { chars, ms });
  await sleep(ms);
  return ms;
}

// Process-global: the point is the shape of a whole session, so this must
// survive across tool calls and tabs.
let actionsSinceRest = 0;
let restThreshold = 0;

function rollRestThreshold(): number {
  const every = envInt('SESSION_REST_EVERY', DEFAULT_REST_EVERY);
  if (every <= 0) return 0;
  // Jitter the threshold too; resting on exactly every 40th action is its
  // own periodic signature.
  return gaussianInt(Math.max(1, Math.round(every * 0.7)), Math.round(every * 1.3));
}

/**
 * Count one physical action and, every so often, take a real break.
 * Returns the ms rested (0 when no rest was due).
 */
export async function maybeSessionRest(): Promise<number> {
  if (!pacingEnabled()) return 0;
  if (restThreshold === 0) {
    restThreshold = rollRestThreshold();
    if (restThreshold === 0) return 0;
  }

  actionsSinceRest += 1;
  if (actionsSinceRest < restThreshold) return 0;

  const minMs = envInt('SESSION_REST_MIN_MS', DEFAULT_REST_MIN_MS);
  const maxMs = envInt('SESSION_REST_MAX_MS', DEFAULT_REST_MAX_MS);
  actionsSinceRest = 0;
  restThreshold = rollRestThreshold();
  if (maxMs <= 0) return 0;

  const ms = gaussianInt(Math.min(minMs, maxMs), Math.max(minMs, maxMs));
  logger.info('pacing: session rest', { ms, nextRestAfter: restThreshold });
  await sleep(ms);
  return ms;
}

/** Test/diagnostic seam: reset the session-rest counters. */
export function resetSessionRest(): void {
  actionsSinceRest = 0;
  restThreshold = 0;
}

export interface ReverseScroll {
  direction: ScrollDirection;
  distancePx: number;
}

/**
 * Occasionally plan a small scroll back the other way — the correction a
 * person makes after overshooting something they wanted to look at. Returns
 * null most of the time; the caller executes the plan through the normal
 * scroll path so it gets the same segmentation and cooldown.
 */
export function planReverseScroll(
  direction: ScrollDirection,
  distancePx: number,
): ReverseScroll | null {
  if (!pacingEnabled()) return null;
  const prob = envFloat('REVERSE_SCROLL_PROB', DEFAULT_REVERSE_SCROLL_PROB);
  if (prob <= 0 || Math.random() >= prob) return null;

  const maxBack = Math.floor(distancePx * REVERSE_SCROLL_MAX_FRACTION);
  if (maxBack < REVERSE_SCROLL_MIN_PX) return null;

  return {
    direction: direction === 'down' ? 'up' : 'down',
    distancePx: gaussianInt(REVERSE_SCROLL_MIN_PX, maxBack),
  };
}
