/**
 * Foreground guard — refuse to act on a page nobody is looking at.
 *
 * A human cannot click what is not on screen. Input dispatched into a
 * background tab is therefore both a clean automation signal for a site to
 * collect and a good way for an agent to silently act on the wrong page.
 *
 * WHICH SIGNAL ACTUALLY WORKS (measured, not assumed)
 *   `document.visibilityState` is NOT usable here. Under a CDP-attached
 *   Chrome it reports 'visible' for background tabs as well, so a check
 *   against it passes unconditionally — a guard that never fires.
 *
 *   `document.hasFocus()` IS usable, but only after Playwright's focus
 *   emulation is turned off (it otherwise forces every page to report itself
 *   as focused). PageProvider disables it per page; with that in place
 *   hasFocus() tracks the frontmost tab exactly.
 *
 *   So hasFocus is authoritative, and visibilityState is kept only as a
 *   secondary hard-fail for the cases where it does report 'hidden'.
 *
 * WHAT IT STILL CANNOT SEE
 *   Window occlusion. A Chrome window fully covered by another application
 *   still reports its active tab as focused if Chrome owns OS focus. Do not
 *   read a pass here as "the operator can see this".
 *
 * Requiring focus is not free: while the operator drives the agent from their
 * editor, Chrome legitimately does not own OS focus, so requiring it for
 * every action would make the tool unusable. The default
 * (`requireWindowFocus: "write"`) requires it only for the irreversible tier,
 * which forces the operator to actually be present at the moment content goes
 * out. Set "all" for the strictest posture, at the cost of having to leave
 * Chrome frontmost for the whole run.
 */

import type { Page } from 'playwright-core';

import { logger } from '../util/logger.js';
import { focusRequirement } from './budget.js';
import type { GuardRejection, WriteClass } from './types.js';

const PROBE_TIMEOUT_MS = 1_500;

export interface ForegroundState {
  /** From visibilityState. Only meaningful when false; see the note above. */
  visible: boolean;
  /** Authoritative "this is the tab in front" signal. */
  focused: boolean;
  /** True when the probe itself failed, so the flags are not trustworthy. */
  unknown: boolean;
}

/**
 * Read visibility/focus from the page. A page too busy to answer within
 * PROBE_TIMEOUT_MS reports `unknown`, which callers treat as "do not block":
 * a hung probe is a bad reason to refuse work.
 */
export async function probeForeground(page: Page): Promise<ForegroundState> {
  try {
    // String form avoids requiring the DOM lib in tsconfig (same pattern as
    // a11y.ts and provider.ts).
    const probe = page.evaluate(
      "({ visible: document.visibilityState === 'visible', focused: document.hasFocus() })",
    ) as Promise<{ visible: boolean; focused: boolean }>;
    const timeout = new Promise<null>((res) => setTimeout(() => res(null), PROBE_TIMEOUT_MS));
    const result = await Promise.race([probe, timeout]);
    if (!result) return { visible: false, focused: false, unknown: true };
    return { visible: result.visible === true, focused: result.focused === true, unknown: false };
  } catch (err) {
    logger.warn('foreground probe failed', {
      error: err instanceof Error ? err.message : String(err),
    });
    return { visible: false, focused: false, unknown: true };
  }
}

/** Gate an action on the page being in the foreground. Returns null to allow. */
export async function checkForeground(
  page: Page,
  writeClass: WriteClass,
): Promise<GuardRejection | null> {
  const state = await probeForeground(page);
  if (state.unknown) return null;

  if (!state.visible) {
    return {
      error: 'not_foreground',
      message:
        'The target tab reports itself as hidden (minimised or discarded), so this ' +
        'action was refused. Bring the tab to the front (select_tab) and retry.',
      detail: { visible: false, focused: state.focused },
    };
  }

  const requirement = focusRequirement();
  const focusRequired = requirement === 'all' || (requirement === 'write' && writeClass === 'write');
  if (focusRequired && !state.focused) {
    const why =
      writeClass === 'write'
        ? 'this action publishes content, and you should be present when it goes out'
        : 'requireWindowFocus is set to "all"';
    return {
      error: 'not_foreground',
      message:
        `The target tab does not have focus, and ${why}. Click into the Chrome ` +
        'window (and the right tab) and retry. Set requireWindowFocus to "off" in ' +
        'config/budget.json to lift this, at the cost of the strongest ' +
        'human-presence signal available.',
      detail: { visible: true, focused: false, requirement, writeClass },
    };
  }

  return null;
}
