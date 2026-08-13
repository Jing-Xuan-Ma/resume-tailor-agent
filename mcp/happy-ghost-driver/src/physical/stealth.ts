/**
 * Optional automation-fingerprint masking. OFF BY DEFAULT — see below.
 *
 * WHY OFF BY DEFAULT
 *   We attach over CDP to a Chrome that was NOT started with
 *   --enable-automation, so `navigator.webdriver` is already `false` and
 *   `window.chrome` is already the real one. The patches below therefore
 *   change nothing a detector cares about, while replacing native getters
 *   with JS functions and monkey-patching `Function.prototype.toString` —
 *   both of which are themselves detectable. On a genuine machine with a
 *   genuine profile, touching less is safer than disguising more.
 *
 *   Enable only when a specific site is provably probing one of these
 *   vectors, via `ENABLE_STEALTH=1`.
 *
 * WHAT THIS CANNOT DO
 *   It cannot hide that the browser is driven over CDP. Playwright enables
 *   the Runtime domain, and every `page.evaluate()` (a11y tree, text
 *   extraction) depends on it. That is a property of the architecture, not
 *   something an init script can mask.
 *
 * Applied via `context.addInitScript()` so overrides land before page JS.
 * Note that addInitScript does NOT report script errors: a malformed script
 * fails silently in the page. That is why verifyStealth() exists.
 */

import type { BrowserContext, Page } from 'playwright-core';

import { logger } from '../util/logger.js';

const STEALTH_JS = `
(() => {
// -- navigator.webdriver --------------------------------------------------
try {
  Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true,
  });
} catch (_) { /* already non-configurable on some Chrome versions */ }

// -- Permissions API: make "notifications" look denied ---------------------
try {
  const origQuery = window.Permissions.prototype.query;
  const patchedQuery = function query(parameters) {
    if (parameters && parameters.name === 'notifications') {
      return Promise.resolve({ state: 'denied', onchange: null });
    }
    return origQuery.call(this, parameters);
  };

  // Hide the patch from Function.prototype.toString probes. Only the
  // functions we actually replaced are masked; everything else keeps its
  // real source so we do not break libraries that inspect their own code.
  const nativeSource = new WeakMap();
  nativeSource.set(patchedQuery, 'function query() { [native code] }');

  const origToString = Function.prototype.toString;
  const maskedToString = function toString() {
    const faked = nativeSource.get(this);
    return faked !== undefined ? faked : origToString.call(this);
  };
  nativeSource.set(maskedToString, 'function toString() { [native code] }');

  window.Permissions.prototype.query = patchedQuery;
  Function.prototype.toString = maskedToString;
} catch (_) {}
})();
`;

/** True when the operator explicitly opted in via ENABLE_STEALTH=1. */
export function stealthEnabled(): boolean {
  const raw = process.env.ENABLE_STEALTH;
  if (raw === undefined) return false;
  const v = raw.trim().toLowerCase();
  return v === '1' || v === 'true' || v === 'yes';
}

/**
 * Apply stealth overrides to a BrowserContext. Callers should gate this on
 * stealthEnabled(); it is a no-op-safe operation but never desirable by
 * default.
 */
export function applyStealth(context: BrowserContext): void {
  context.addInitScript(STEALTH_JS);
  logger.info('stealth: init script registered (opt-in via ENABLE_STEALTH)');
}

export interface FingerprintReport {
  webdriver: unknown;
  stealthRequested: boolean;
}

/**
 * Log what the page actually exposes. Purely diagnostic: it answers "is my
 * fingerprint what I think it is?" instead of leaving the operator to
 * assume an init script took effect. Never throws.
 */
export async function verifyStealth(page: Page): Promise<FingerprintReport | null> {
  const stealthRequested = stealthEnabled();
  try {
    // String form avoids requiring the DOM lib in tsconfig (same pattern as
    // a11y.ts and provider.ts).
    const webdriver = await page.evaluate('({ webdriver: navigator.webdriver })');
    const report: FingerprintReport = {
      webdriver: (webdriver as { webdriver: unknown }).webdriver,
      stealthRequested,
    };
    logger.info('stealth: fingerprint self-check', report);
    if (report.webdriver === true) {
      logger.warn(
        'stealth: navigator.webdriver is TRUE — this Chrome was started with automation flags; ' +
          'sites can trivially detect it. Relaunch via scripts/launch-chrome.sh.',
      );
    }
    return report;
  } catch (err) {
    logger.warn('stealth: fingerprint self-check failed', {
      error: err instanceof Error ? err.message : String(err),
    });
    return null;
  }
}
