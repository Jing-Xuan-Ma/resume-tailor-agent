/**
 * Behaviour budget — the hard ceiling the agent cannot talk its way past.
 *
 * The risk that actually gets a personal account flagged is volume and
 * timing, not mouse curves: too many actions per hour, content published at
 * 4am, a week's worth of comments in ten minutes. Those are properties of a
 * *session*, so they cannot be enforced by a per-action cooldown, and they
 * must not live in a skill document — a prompt is a suggestion, and an agent
 * mid-task will exceed it. So the ceiling lives here, in the server, keyed
 * off the persisted ledger.
 *
 * Config: config/budget.json (optional; defaults below are used as-is when
 * absent). Env `GUARD_ENABLED=0` disables the whole thing, which exists for
 * tests and debugging, not for daily use.
 */

import { readFileSync, statSync } from 'node:fs';

import {
  budgetConfigPath,
  resolveProfileBirthMarker,
  resolveProfileDir,
} from '../config/paths.js';
import { logger } from '../util/logger.js';
import { countActions } from './ledger.js';
import type { GuardRejection, WriteClass } from './types.js';

export interface QuotaLimit {
  perHour: number;
  perDay: number;
}

export interface DwellRange {
  min: number;
  max: number;
}

export interface DomainPolicy {
  /** Risk tier to bill a submit on this domain to. */
  submitClass?: WriteClass;
  /** Pre-submit "check your work" pause for this domain. */
  submitDwellMs?: DwellRange;
  limits?: Partial<Record<WriteClass, Partial<QuotaLimit>>>;
}

export type FocusRequirement = 'off' | 'write' | 'all';

export interface BudgetConfig {
  enabled: boolean;
  /** Days over which a fresh profile's quotas ramp to full. */
  rampUpDays: number;
  /** Floor for the ramp factor, so a day-one profile is usable at all. */
  rampUpFloor: number;
  /** Typing at least this many chars arms the submit gate for that page. */
  writeIntentMinChars: number;
  requireWindowFocus: FocusRequirement;
  nightGuard: { enabled: boolean; startHour: number; endHour: number };
  submitDwellMs: DwellRange;
  limits: Record<WriteClass, QuotaLimit>;
  domains: Record<string, DomainPolicy>;
}

/**
 * Defaults sized for one person's real usage, not for throughput: reading is
 * effectively unlimited, interaction is generous, and publishing is scarce
 * because publishing is the irreversible part.
 */
const DEFAULT_CONFIG: BudgetConfig = {
  enabled: true,
  rampUpDays: 14,
  rampUpFloor: 0.3,
  writeIntentMinChars: 25,
  requireWindowFocus: 'write',
  nightGuard: { enabled: true, startHour: 1, endHour: 7 },
  submitDwellMs: { min: 5_000, max: 20_000 },
  limits: {
    read: { perHour: 600, perDay: 4_000 },
    light: { perHour: 120, perDay: 600 },
    write: { perHour: 6, perDay: 24 },
  },
  domains: {
    // AI chat products: "submitting" is asking a question, which is simply
    // how the product is used. Billed as light with a short dwell so GEO
    // runs are not throttled to uselessness.
    'deepseek.com': { submitClass: 'light', submitDwellMs: { min: 800, max: 2_500 } },
    'doubao.com': { submitClass: 'light', submitDwellMs: { min: 800, max: 2_500 } },
    'kimi.com': { submitClass: 'light', submitDwellMs: { min: 800, max: 2_500 } },
    'moonshot.cn': { submitClass: 'light', submitDwellMs: { min: 800, max: 2_500 } },
    'tongyi.com': { submitClass: 'light', submitDwellMs: { min: 800, max: 2_500 } },
    'chatgpt.com': { submitClass: 'light', submitDwellMs: { min: 800, max: 2_500 } },
  },
};

let cached: BudgetConfig | null = null;

function numberOr(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function isFocusRequirement(value: unknown): value is FocusRequirement {
  return value === 'off' || value === 'write' || value === 'all';
}

function mergeLimit(base: QuotaLimit, override: Partial<QuotaLimit> | undefined): QuotaLimit {
  if (!override) return base;
  return {
    perHour: typeof override.perHour === 'number' ? override.perHour : base.perHour,
    perDay: typeof override.perDay === 'number' ? override.perDay : base.perDay,
  };
}

/** Load and cache config. Malformed JSON falls back to defaults, loudly. */
export function loadBudgetConfig(): BudgetConfig {
  if (cached) return cached;
  let merged: BudgetConfig = {
    ...DEFAULT_CONFIG,
    nightGuard: { ...DEFAULT_CONFIG.nightGuard },
    submitDwellMs: { ...DEFAULT_CONFIG.submitDwellMs },
    limits: {
      read: { ...DEFAULT_CONFIG.limits.read },
      light: { ...DEFAULT_CONFIG.limits.light },
      write: { ...DEFAULT_CONFIG.limits.write },
    },
    domains: { ...DEFAULT_CONFIG.domains },
  };

  const path = budgetConfigPath();
  try {
    const raw = JSON.parse(readFileSync(path, 'utf8')) as Partial<BudgetConfig>;
    // Fields are picked explicitly rather than spread, so documentation keys
    // in the JSON (and typos) cannot silently become config.
    merged = {
      enabled: typeof raw.enabled === 'boolean' ? raw.enabled : merged.enabled,
      rampUpDays: numberOr(raw.rampUpDays, merged.rampUpDays),
      rampUpFloor: numberOr(raw.rampUpFloor, merged.rampUpFloor),
      writeIntentMinChars: numberOr(raw.writeIntentMinChars, merged.writeIntentMinChars),
      requireWindowFocus: isFocusRequirement(raw.requireWindowFocus)
        ? raw.requireWindowFocus
        : merged.requireWindowFocus,
      nightGuard: { ...merged.nightGuard, ...(raw.nightGuard ?? {}) },
      submitDwellMs: { ...merged.submitDwellMs, ...(raw.submitDwellMs ?? {}) },
      limits: {
        read: mergeLimit(merged.limits.read, raw.limits?.read),
        light: mergeLimit(merged.limits.light, raw.limits?.light),
        write: mergeLimit(merged.limits.write, raw.limits?.write),
      },
      domains: { ...merged.domains, ...(raw.domains ?? {}) },
    };
    logger.info('budget config loaded', { path });
  } catch (err) {
    const code = (err as { code?: string }).code;
    if (code !== 'ENOENT') {
      logger.warn('budget config unreadable; using defaults', {
        path,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  if (process.env.GUARD_ENABLED !== undefined) {
    const v = process.env.GUARD_ENABLED.trim().toLowerCase();
    merged.enabled = !(v === '0' || v === 'false' || v === 'no');
  }

  cached = merged;
  return cached;
}

/** Test seam: drop the cache so a changed config/env is picked up. */
export function resetBudgetConfig(): void {
  cached = null;
}

export function guardEnabled(): boolean {
  return loadBudgetConfig().enabled;
}

export function writeIntentMinChars(): number {
  return loadBudgetConfig().writeIntentMinChars;
}

export function focusRequirement(): FocusRequirement {
  return loadBudgetConfig().requireWindowFocus;
}

/** Per-domain policy, falling back to global defaults. */
export function domainPolicy(domain: string): DomainPolicy {
  return loadBudgetConfig().domains[domain] ?? {};
}

/** Which tier a submit on this domain is billed to. */
export function submitClassFor(domain: string): WriteClass {
  return domainPolicy(domain).submitClass ?? 'write';
}

/** How long to pause before a submit on this domain. */
export function submitDwellFor(domain: string): DwellRange {
  return domainPolicy(domain).submitDwellMs ?? loadBudgetConfig().submitDwellMs;
}

/**
 * Age of the Chrome profile in days, or null when it cannot be determined.
 *
 * Prefers the marker written by launch-chrome.sh on profile creation; falls
 * back to the directory's own timestamps for profiles adopted by hand.
 */
export function profileAgeDays(): number | null {
  const now = Date.now();
  try {
    const raw = readFileSync(resolveProfileBirthMarker(), 'utf8').trim();
    const parsed = Date.parse(raw);
    if (Number.isFinite(parsed)) return (now - parsed) / 86_400_000;
  } catch {
    // No marker (pre-existing or hand-adopted profile) — try the directory.
  }
  try {
    const st = statSync(resolveProfileDir());
    const birth = st.birthtimeMs > 0 ? st.birthtimeMs : st.mtimeMs;
    return (now - birth) / 86_400_000;
  } catch {
    return null;
  }
}

/**
 * Quota scaling for a young profile. A fresh profile is a new device; doing
 * full-volume automation on day one is the pattern that gets accounts
 * flagged, so quotas start low and ramp linearly to full.
 *
 * Unknown age ramps to 1.0 rather than clamping to the floor: we cannot
 * distinguish "brand new" from "adopted a mature profile", and the absolute
 * quotas below still apply either way.
 */
export function rampFactor(): number {
  const cfg = loadBudgetConfig();
  const age = profileAgeDays();
  if (age === null) return 1;
  if (cfg.rampUpDays <= 0) return 1;
  const raw = age / cfg.rampUpDays;
  return Math.min(1, Math.max(cfg.rampUpFloor, raw));
}

/** Effective limit for a tier on a domain, after per-domain and ramp scaling. */
export function effectiveLimit(domain: string, writeClass: WriteClass): QuotaLimit {
  const cfg = loadBudgetConfig();
  const base = mergeLimit(cfg.limits[writeClass], domainPolicy(domain).limits?.[writeClass]);
  const factor = rampFactor();
  // Never scale a configured limit to zero; that would read as "broken"
  // rather than "throttled" at the call site.
  return {
    perHour: Math.max(1, Math.ceil(base.perHour * factor)),
    perDay: Math.max(1, Math.ceil(base.perDay * factor)),
  };
}

function inNightWindow(hour: number, startHour: number, endHour: number): boolean {
  // Windows may wrap midnight (e.g. 23 -> 6).
  if (startHour === endHour) return false;
  if (startHour < endHour) return hour >= startHour && hour < endHour;
  return hour >= startHour || hour < endHour;
}

export interface PolicyCheck {
  domain: string;
  writeClass: WriteClass;
  /** Local hour override for tests. */
  nowHour?: number;
  nowTs?: number;
}

/**
 * The gate. Returns null when the action may proceed, or a structured
 * rejection the handler surfaces verbatim to the agent.
 */
export function checkPolicy(check: PolicyCheck): GuardRejection | null {
  const cfg = loadBudgetConfig();
  if (!cfg.enabled) return null;

  const now = check.nowTs ?? Date.now();
  const hour = check.nowHour ?? new Date(now).getHours();

  // Night guard applies only to the irreversible tier: reading at 3am is
  // plausible for a night owl, publishing on a schedule is not.
  if (
    cfg.nightGuard.enabled &&
    check.writeClass === 'write' &&
    inNightWindow(hour, cfg.nightGuard.startHour, cfg.nightGuard.endHour)
  ) {
    return {
      error: 'night_guard',
      message:
        `Write actions are blocked between ${cfg.nightGuard.startHour}:00 and ` +
        `${cfg.nightGuard.endHour}:00 local time (currently ${hour}:00). Publishing ` +
        `on a schedule a human would be asleep for is a strong automation signal. ` +
        `Defer this until daytime.`,
      detail: { hour, window: cfg.nightGuard },
    };
  }

  const limit = effectiveLimit(check.domain, check.writeClass);
  const hourAgo = now - 3_600_000;
  const dayAgo = now - 86_400_000;

  const usedHour = countActions({
    domain: check.domain,
    writeClass: check.writeClass,
    sinceTs: hourAgo,
  });
  if (usedHour >= limit.perHour) {
    return rejectQuota(check, 'hour', usedHour, limit.perHour);
  }

  const usedDay = countActions({
    domain: check.domain,
    writeClass: check.writeClass,
    sinceTs: dayAgo,
  });
  if (usedDay >= limit.perDay) {
    return rejectQuota(check, 'day', usedDay, limit.perDay);
  }

  return null;
}

function rejectQuota(
  check: PolicyCheck,
  window: 'hour' | 'day',
  used: number,
  cap: number,
): GuardRejection {
  const age = profileAgeDays();
  const factor = rampFactor();
  return {
    error: 'budget_exceeded',
    message:
      `${check.writeClass} quota for ${check.domain} is exhausted for this ${window} ` +
      `(${used}/${cap}). This ceiling exists to keep the account's activity inside a ` +
      `human envelope — do not retry, and do not switch domains to work around it. ` +
      `Stop this task and report the limit to the operator.`,
    detail: {
      domain: check.domain,
      writeClass: check.writeClass,
      window,
      used,
      cap,
      profileAgeDays: age === null ? null : Math.round(age * 10) / 10,
      rampFactor: Math.round(factor * 100) / 100,
    },
  };
}
