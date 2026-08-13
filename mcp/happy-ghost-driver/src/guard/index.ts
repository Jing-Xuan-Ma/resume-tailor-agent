/**
 * Guard orchestration — one entry point every physical action passes through.
 *
 * Centralising this is the point: a guard that individual handlers can forget
 * to call is not a ceiling, it is a suggestion. Handlers get exactly one
 * function, and it either returns permission or a rejection to surface.
 *
 * The guards only engage when a real page is driving. Unit tests inject a
 * mock action surface with no page, and an action with no page cannot be
 * unsafe: there is no account, no domain, and no quota to spend.
 */

import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import type { Page } from 'playwright-core';

import { resolveSubmitArchiveDir } from '../config/paths.js';
import { gaussianInt } from '../physical/rand.js';
import { maybeSessionRest } from '../physical/pacing.js';
import { logger } from '../util/logger.js';
import { checkPolicy, guardEnabled, submitClassFor, submitDwellFor } from './budget.js';
import { checkForeground } from './foreground.js';
import { recordAction } from './ledger.js';
import { consumeWriteIntent, restoreWriteIntent } from './write-intent.js';
import { domainOf } from './types.js';
import type { ActionType, GuardRejection, WriteClass } from './types.js';

export interface GuardRequest {
  /** Null for injected/mock action surfaces; guards then no-op. */
  page: Page | null;
  actionType: ActionType;
  /** Risk tier when no write intent is pending. */
  baseClass: WriteClass;
  /**
   * Whether a pending write intent should be consumed by this action.
   * True for click/Enter (the gestures that submit), false for scroll.
   */
  canSubmit?: boolean;
  /** Short, non-sensitive note for the ledger (never typed content). */
  detail?: string;
}

export type GuardOutcome =
  | { ok: true; writeClass: WriteClass; domain: string; submit: boolean }
  | { ok: false; rejection: GuardRejection };

/**
 * Run every gate for one action, and record it once permitted.
 *
 * The ledger write happens BEFORE the action executes, deliberately: by the
 * time an action throws, its input events may already have reached the page,
 * so quota must count attempts rather than successes. Undercounting is the
 * one error mode that defeats the purpose.
 */
export async function guardAction(req: GuardRequest): Promise<GuardOutcome> {
  const { page } = req;
  if (!page || !guardEnabled()) {
    return { ok: true, writeClass: req.baseClass, domain: 'unknown', submit: false };
  }

  const url = page.url();
  const domain = domainOf(url);

  // A pending write intent promotes this action from "a click" to "the
  // submit", which changes both the tier it is billed to and the pacing.
  const intent = req.canSubmit === true ? consumeWriteIntent(page) : null;
  const submit = intent !== null;
  const actionType: ActionType = submit ? 'submit' : req.actionType;
  const writeClass: WriteClass = submit ? submitClassFor(domain) : req.baseClass;

  /**
   * Refusing an action must leave the page exactly as the agent left it: the
   * composed text is still in the field, so the next attempt is still the
   * submit. Without this, one rejected click would silently downgrade the
   * retry to an ungated "light" click.
   */
  const refuse = (rejection: GuardRejection): GuardOutcome => {
    if (intent) restoreWriteIntent(page, intent);
    logger.warn(`guard: ${actionType} refused`, { domain, writeClass, error: rejection.error });
    return { ok: false, rejection };
  };

  const rejection = checkPolicy({ domain, writeClass });
  if (rejection) return refuse(rejection);

  await maybeSessionRest();

  // Probed after any rest so the answer describes the moment of the action.
  const foreground = await checkForeground(page, writeClass);
  if (foreground) return refuse(foreground);

  if (submit) {
    await runSubmitGate(page, domain, intent!.chars);
  }

  recordAction({
    ts: Date.now(),
    domain,
    actionType,
    writeClass,
    url,
    detail: req.detail ?? null,
  });

  return { ok: true, writeClass, domain, submit };
}

/**
 * Gate a navigation.
 *
 * Separate from guardAction because a navigation is the one action with no
 * page to inspect yet — there is nothing to check for visibility, and the
 * domain that matters is the destination, not wherever we happen to be. It
 * still counts against the destination's read quota so that "open 400 pages
 * in an hour" is caught.
 */
export async function guardNavigation(url: string): Promise<GuardOutcome> {
  if (!guardEnabled()) {
    return { ok: true, writeClass: 'read', domain: 'unknown', submit: false };
  }
  const domain = domainOf(url);
  const rejection = checkPolicy({ domain, writeClass: 'read' });
  if (rejection) {
    logger.warn('guard: navigate refused', { domain, error: rejection.error });
    return { ok: false, rejection };
  }
  await maybeSessionRest();
  recordAction({
    ts: Date.now(),
    domain,
    actionType: 'navigate',
    writeClass: 'read',
    url,
    detail: null,
  });
  return { ok: true, writeClass: 'read', domain, submit: false };
}

/**
 * The pre-submit pause and archive.
 *
 * A person who just composed something looks at it before publishing. Going
 * from last keystroke to Publish in 200ms is not a rhythm a human produces,
 * and it is also the moment where an agent mistake becomes public and
 * permanent. The archived screenshot is what makes that reviewable after the
 * fact instead of a mystery.
 */
async function runSubmitGate(page: Page, domain: string, chars: number): Promise<void> {
  const dwell = submitDwellFor(domain);
  const ms = gaussianInt(Math.min(dwell.min, dwell.max), Math.max(dwell.min, dwell.max));
  logger.info('guard: submit gate', { domain, chars, dwellMs: ms });

  await archiveSubmit(page, domain);
  await new Promise((r) => setTimeout(r, ms));
}

/** Best-effort screenshot of what is about to be published. Never throws. */
async function archiveSubmit(page: Page, domain: string): Promise<void> {
  try {
    const dir = resolveSubmitArchiveDir();
    mkdirSync(dir, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const file = join(dir, `${stamp}_${domain}.png`);
    await page.screenshot({ path: file });
    logger.info('guard: submit archived', { file });
  } catch (err) {
    // An unarchivable submit is still allowed through: the dwell and the
    // quota are the safety mechanism, the screenshot is the audit nicety.
    logger.warn('guard: submit archive failed', {
      error: err instanceof Error ? err.message : String(err),
    });
  }
}

/** Build the MCP error payload for a rejection. */
export function rejectionPayload(rejection: GuardRejection): {
  error: string;
  message: string;
  detail?: Record<string, unknown>;
} {
  return {
    error: rejection.error,
    message: rejection.message,
    ...(rejection.detail ? { detail: rejection.detail } : {}),
  };
}

export { domainOf } from './types.js';
export type { ActionType, GuardRejection, WriteClass } from './types.js';
