import { homedir } from 'node:os';
import { join, resolve } from 'node:path';

// --- Repo-relative config files ------------------------------------------

// Resolved at CALL time, not import time: tests chdir into a sandbox
// before touching config files, and an import-time constant would keep
// pointing at the repo's real config/ (which a test once clobbered).
export function configDir(): string {
  return resolve(process.cwd(), 'config');
}

export function configKeyPath(): string {
  return resolve(configDir(), '.key');
}

export function configPlainPath(): string {
  return resolve(configDir(), 'app.config.json');
}

export function configEncPath(): string {
  return resolve(configDir(), 'app.config.enc.json');
}

export function configExamplePath(): string {
  return resolve(configDir(), 'app.config.example.json');
}

/** Behaviour budget for the account-safety guards. Optional; defaults apply. */
export function budgetConfigPath(): string {
  const raw = process.env.GHOST_BUDGET_CONFIG;
  if (raw && raw.trim() !== '') return raw.trim();
  return resolve(configDir(), 'budget.json');
}

// --- Persistent identity state -------------------------------------------
//
// Everything below must survive reboots and OS temp-dir cleanup. The Chrome
// profile IS the logged-in identity: if it is lost, the next run looks like a
// brand-new device to the site, which is the signal that gets personal
// accounts flagged. So these default under $HOME, never under $TMPDIR.
//
// Chrome 136+ refuses --remote-debugging-port when pointed at the default
// Chrome data directory, so a dedicated-but-persistent profile is the only
// supported shape. See scripts/launch-chrome.sh, which honours the same env
// vars with the same defaults.

/** Root for profile, ledger and backups. Override with GHOST_HOME. */
export function ghostHome(): string {
  const raw = process.env.GHOST_HOME;
  if (raw && raw.trim() !== '') return raw.trim();
  return join(homedir(), '.ghost-driver');
}

/**
 * The Chrome user-data-dir we drive. Override with GHOST_PROFILE_DIR.
 * Must match scripts/launch-chrome.sh.
 */
export function resolveProfileDir(): string {
  const raw = process.env.GHOST_PROFILE_DIR;
  if (raw && raw.trim() !== '') return raw.trim();
  return join(ghostHome(), 'chrome-profile');
}

/**
 * Marker written by launch-chrome.sh when a profile is first created. Its
 * contents are the profile's birth date, which the budget guard uses to ramp
 * quotas up over a new account's warm-up period.
 */
export function resolveProfileBirthMarker(): string {
  return join(resolveProfileDir(), '.ghost-created-at');
}

/** Local action ledger. Always SQLite, always local — never the MySQL store. */
export function resolveLedgerPath(): string {
  const raw = process.env.GHOST_LEDGER_PATH;
  if (raw && raw.trim() !== '') return raw.trim();
  return join(ghostHome(), 'ledger.db');
}

/** Where pre-submit screenshots are archived for after-the-fact review. */
export function resolveSubmitArchiveDir(): string {
  const raw = process.env.GHOST_SUBMIT_ARCHIVE_DIR;
  if (raw && raw.trim() !== '') return raw.trim();
  return resolve(process.cwd(), '.debug', 'submits');
}
