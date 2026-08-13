/**
 * Phase 3 — Physical scroll with momentum.
 *
 * A real scroll wheel is not a single `wheel(0, 1500)` event; the user
 * flicks the wheel several times in quick succession. We split a total
 * distance into 3-7 random segments and fire `page.mouse.wheel(0, dy)`
 * for each, sleeping a Gaussian-random delay between segments to mimic the
 * natural cadence of a trackpad flick.
 *
 * Direction is sign-mapped here: 'down' -> positive deltaY (scrolls
 * content up), 'up' -> negative deltaY.
 */

import type { Page } from 'playwright-core';

import { logger } from '../util/logger.js';
import { gaussianInt } from './rand.js';

export type ScrollDirection = 'up' | 'down';

export const SCROLL_SEGMENTS_MIN = 3;
export const SCROLL_SEGMENTS_MAX = 7;
export const SCROLL_SEGMENT_DELAY_MIN_MS = 30;
export const SCROLL_SEGMENT_DELAY_MAX_MS = 80;
export const MAX_SCROLL_DISTANCE_PX = 100_000;

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Scroll the page in the given direction by `distancePx` pixels,
 * dispatched as a sequence of small wheel events.
 *
 * The per-segment delta is randomized (not just total/segments) and the
 * inter-segment delay follows a Gaussian distribution — important for
 * bot detection that analyses the statistical shape of event timing.
 */
export async function scroll(
  page: Page,
  direction: ScrollDirection,
  distancePx: number,
  opts: { segmentsMin?: number; segmentsMax?: number; delayMinMs?: number; delayMaxMs?: number } = {},
): Promise<void> {
  if (direction !== 'up' && direction !== 'down') {
    throw new Error(`scroll: direction must be 'up' or 'down', got ${String(direction)}`);
  }
  if (!Number.isFinite(distancePx) || distancePx < 0) {
    throw new Error(`scroll: distancePx must be a non-negative finite number, got ${distancePx}`);
  }
  if (distancePx > MAX_SCROLL_DISTANCE_PX) {
    throw new Error(
      `scroll: distancePx ${distancePx} exceeds cap of ${MAX_SCROLL_DISTANCE_PX}`,
    );
  }

  const segmentsMin = opts.segmentsMin ?? SCROLL_SEGMENTS_MIN;
  const segmentsMax = opts.segmentsMax ?? SCROLL_SEGMENTS_MAX;
  const delayMin = opts.delayMinMs ?? SCROLL_SEGMENT_DELAY_MIN_MS;
  const delayMax = opts.delayMaxMs ?? SCROLL_SEGMENT_DELAY_MAX_MS;

  const sign = direction === 'down' ? 1 : -1;
  // Gaussian segment count, clamped to [segmentsMin, segmentsMax].
  const totalSegments = gaussianInt(segmentsMin, segmentsMax);

  // Random partition of distance into `totalSegments` positive parts.
  // We pick `totalSegments - 1` cut points in [0, distance], sort them,
  // and the per-segment distance is the gap between consecutive cuts.
  const cuts: number[] = [0];
  for (let i = 0; i < totalSegments - 1; i++) {
    cuts.push(Math.random() * distancePx);
  }
  cuts.push(distancePx);
  cuts.sort((a, b) => a - b);

  for (let i = 0; i < totalSegments; i++) {
    const segDist = cuts[i + 1]! - cuts[i]!;
    if (segDist <= 0) continue;
    const deltaY = sign * segDist;
    // Playwright's wheel signature: wheel(deltaX, deltaY).
    await page.mouse.wheel(0, deltaY);
    if (i < totalSegments - 1) {
      await sleep(gaussianInt(delayMin, delayMax));
    }
  }

  logger.info('physical_scroll complete', { direction, distancePx, segments: totalSegments });
}
