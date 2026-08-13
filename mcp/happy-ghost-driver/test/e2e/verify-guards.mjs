// Closed-loop verification of the account-safety guards against a real Chrome.
//
//   bash scripts/launch-chrome.sh && node test/e2e/verify-guards.mjs
//
// Needs a live CDP on :9222. Uses a sandboxed ledger, budget config and submit
// archive under $TMPDIR, so it never spends the operator's real quota or writes
// to ~/.ghost-driver.
//
// Covers the parts that unit tests cannot: whether the foreground signal is
// real, whether a submit actually produces a dwell and an archived screenshot,
// and whether a refused action stays out of the ledger.

import { mkdtempSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const sandbox = mkdtempSync(join(tmpdir(), 'ghost-verify-'));
const budgetPath = join(sandbox, 'budget.json');
writeFileSync(
  budgetPath,
  JSON.stringify({
    enabled: true,
    rampUpDays: 0,
    writeIntentMinChars: 10,
    // 'all' so the foreground check is exercised for every action. This is
    // testable because bringToFront() gives Chrome OS focus on macOS.
    requireWindowFocus: 'all',
    nightGuard: { enabled: false, startHour: 1, endHour: 7 },
    submitDwellMs: { min: 300, max: 600 },
    limits: {
      read: { perHour: 500, perDay: 5000 },
      light: { perHour: 2, perDay: 500 }, // tiny, to prove exhaustion
      write: { perHour: 5, perDay: 20 },
    },
    domains: {},
  }),
);
process.env.GHOST_BUDGET_CONFIG = budgetPath;
process.env.GHOST_LEDGER_PATH = join(sandbox, 'ledger.db');
process.env.GHOST_SUBMIT_ARCHIVE_DIR = join(sandbox, 'submits');
process.env.PACING_ENABLED = '0';
process.env.COOLDOWN_MIN_MS = '1';
process.env.COOLDOWN_MAX_MS = '2';

const { chromium } = await import('playwright-core');
const { handlePhysicalClick, handlePhysicalScroll, handlePhysicalType } = await import(
  '../../dist/mcp/server.js'
);
const { verifyStealth, stealthEnabled } = await import('../../dist/physical/stealth.js');
const { countActions, recentActions } = await import('../../dist/guard/ledger.js');
const { noteTyping, peekWriteIntent } = await import('../../dist/guard/write-intent.js');

const results = [];
function check(name, pass, extra = '') {
  results.push({ name, pass, extra });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${extra ? `  — ${extra}` : ''}`);
}
const payload = (r) => JSON.parse(r.content[0].text);

const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
const ctx = browser.contexts()[0];

// Two tabs on a harmless origin: one foreground, one background.
const front = await ctx.newPage();
await front.goto('https://example.com/', { waitUntil: 'domcontentloaded' });
const back = await ctx.newPage();
await back.goto('https://example.com/?bg=1', { waitUntil: 'domcontentloaded' });

// Playwright forces every page to report itself focused; PageProvider disables
// that in production. This harness drives the handlers directly, so it has to
// do the same or the foreground guard has no signal to read.
for (const p of [front, back]) {
  const s = await ctx.newCDPSession(p);
  await s.send('Emulation.setFocusEmulationEnabled', { enabled: false });
}

// `back` was created last, so it is the frontmost one; bring `front` forward.
await front.bringToFront();
await new Promise((r) => setTimeout(r, 700));

const probe = "({ v: document.visibilityState, f: document.hasFocus() })";
console.log(
  '  front:',
  JSON.stringify(await front.evaluate(probe)),
  ' back:',
  JSON.stringify(await back.evaluate(probe)),
);

// 1) No stealth by default.
check('stealth disabled by default', stealthEnabled() === false);
const report = await verifyStealth(front);
check(
  'navigator.webdriver is not true without stealth',
  report && report.webdriver !== true,
  `webdriver=${JSON.stringify(report?.webdriver)}`,
);

// 2) Foreground guard refuses the background tab.
const bgClick = await handlePhysicalClick({ x: 50, y: 50 }, { page: back });
check(
  'background tab click refused as not_foreground',
  bgClick.isError === true && payload(bgClick).error === 'not_foreground',
  payload(bgClick).error,
);

// 3) Visible tab is allowed, and lands in the ledger.
const before = countActions({ domain: 'example.com', sinceTs: 0 });
const okScroll = await handlePhysicalScroll({ direction: 'down', distance_px: 200 }, { page: front });
check('visible tab scroll allowed', okScroll.isError !== true, JSON.stringify(payload(okScroll)));
const after = countActions({ domain: 'example.com', sinceTs: 0 });
check('scroll recorded in ledger', after === before + 1, `${before} -> ${after}`);

// 4) Typing arms write intent; the following click becomes a gated submit.
const typed = await handlePhysicalType({ text: 'a fairly long comment body' }, { page: front });
check('type allowed', typed.isError !== true, JSON.stringify(payload(typed)));
check('write intent armed after typing', peekWriteIntent(front) !== null);

const submitClick = await handlePhysicalClick({ x: 60, y: 60 }, { page: front });
const submitPayload = payload(submitClick);
check(
  'click after typing is classified as a submit',
  submitClick.isError !== true && submitPayload.submit === true,
  JSON.stringify(submitPayload),
);
const writeCount = countActions({ domain: 'example.com', writeClass: 'write', sinceTs: 0 });
check('submit billed to the write tier', writeCount === 1, `write rows=${writeCount}`);
const archiveDir = process.env.GHOST_SUBMIT_ARCHIVE_DIR;
const archived = existsSync(archiveDir) ? readdirSync(archiveDir) : [];
check('submit screenshot archived', archived.length === 1, archived.join(','));

// 5) Light quota is perHour=2. So far only the `type` was billed to light (the
// submit went to write, and the refused background click was never recorded),
// so one more click is allowed and the one after it must be refused.
const lightBefore = countActions({ domain: 'example.com', writeClass: 'light', sinceTs: 0 });
const fillQuota = await handlePhysicalClick({ x: 70, y: 70 }, { page: front });
check(
  'click within light quota still allowed',
  fillQuota.isError !== true,
  `light used ${lightBefore} -> ${countActions({ domain: 'example.com', writeClass: 'light', sinceTs: 0 })}/2`,
);

const overQuota = await handlePhysicalClick({ x: 80, y: 80 }, { page: front });
check(
  'light quota exhaustion refuses further clicks',
  overQuota.isError === true && payload(overQuota).error === 'budget_exceeded',
  JSON.stringify(payload(overQuota).detail ?? payload(overQuota)),
);

// A refused action must not be billed, or a rejection loop would keep
// inflating the ledger and permanently lock the domain out.
check(
  'refused action is not recorded in the ledger',
  countActions({ domain: 'example.com', writeClass: 'light', sinceTs: 0 }) === 2,
  `light rows=${countActions({ domain: 'example.com', writeClass: 'light', sinceTs: 0 })}`,
);

console.log('\n--- ledger contents ---');
for (const row of recentActions(10)) {
  console.log(
    `  ${new Date(row.ts).toISOString()} ${row.domain} ${row.actionType}/${row.writeClass} ${row.detail ?? ''}`,
  );
}

await back.close();
await front.close();
await browser.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
if (failed.length > 0) {
  console.log('FAILED:', failed.map((f) => f.name).join('; '));
  process.exit(1);
}
