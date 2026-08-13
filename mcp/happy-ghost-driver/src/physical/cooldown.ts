/**
 * Phase 3 — Cooldown / human pacing.
 *
 * README §7 hard-constraint: every physical action must be bookended by a
 * 1000-3000ms random sleep so the agent does not hammer the browser like
 * a bot. The cooldown here is enforced by `withCooldown`, which every
 * physical tool handler funnels through.
 *
 * The min/max bounds can be overridden via environment variables so tests
 * can run with sub-millisecond cooldowns:
 *   COOLDOWN_MIN_MS=1 COOLDOWN_MAX_MS=2 ...
 *
 * Defaults (production): 1000-3000 ms.  Uses Gaussian distribution so most
 * waits cluster around 2 s with occasional shorter/longer pauses.
 */

import { logger } from '../util/logger.js';
import { gaussianInt } from './rand.js';

const DEFAULT_MIN_MS = 1000;
const DEFAULT_MAX_MS = 3000;

/**
 * Read a non-negative integer env var. Returns undefined when missing,
 * NaN-ish, or negative.
 */
function readPositiveEnvInt(raw: string | undefined): number | undefined {
  if (raw === undefined || raw.trim() === '') return undefined;
  const n = Number(raw);
  if (!Number.isFinite(n) || !Number.isInteger(n) || n < 0) return undefined;
  return n;
}

/**
 * Resolve the configured cooldown window. Reads env on every call so tests
 * that mutate process.env between cases are honoured.
 */
export function getCooldownBounds(): { minMs: number; maxMs: number } {
  const minMs = readPositiveEnvInt(process.env.COOLDOWN_MIN_MS) ?? DEFAULT_MIN_MS;
  const maxMs = readPositiveEnvInt(process.env.COOLDOWN_MAX_MS) ?? DEFAULT_MAX_MS;
  if (minMs > maxMs) {
    // Be defensive: a misconfigured env should not crash the server, but
    // it must be loud enough to be noticed.
    logger.warn('COOLDOWN_MIN_MS > COOLDOWN_MAX_MS; swapping.', { minMs, maxMs });
    return { minMs: maxMs, maxMs: minMs };
  }
  return { minMs, maxMs };
}

/**
 * Sleep for a Gaussian-random duration clamped to [minMs, maxMs].
 *
 * Defaults to the production cooldown window (1s-3s) when called with no
 * args; callers that want a tighter window (e.g. tests) pass overrides.
 */
export function randomSleep(minMs: number = getCooldownBounds().minMs, maxMs: number = getCooldownBounds().maxMs): Promise<void> {
  const ms = gaussianInt(minMs, maxMs);
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Wrap an action with mandatory cooldown sleeps before AND after.
 *
 * Used by every physical tool handler so pacing is centralized here —
 * individual handlers cannot accidentally bypass the 1-3s rule.
 *
 * Returns whatever the inner action returns; propagates inner rejections
 * (but still sleeps after a failed action so we do not retry-storm).
 */
export async function withCooldown<T>(action: () => Promise<T>): Promise<T> {
  await randomSleep();
  let result: T;
  try {
    result = await action();
  } catch (err) {
    // Even on failure we respect the cooldown window — the next physical
    // action will not start until after the post-sleep.
    await randomSleep();
    throw err;
  }
  await randomSleep();
  return result;
}
