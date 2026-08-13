// Account-safety guard tests.
//
// These cover the logic that decides whether an action is allowed to happen
// at all. It is the one part of the system where a silent regression is
// expensive in a way code cannot undo: a quota that stops counting, or a
// submit gate that stops firing, is only discovered when an account is
// already restricted.
//
// Everything here runs without a browser. The ledger and budget config are
// redirected into a temp dir so the tests never touch the operator's real
// ~/.ghost-driver state or spend their real quota.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const sandbox = mkdtempSync(join(tmpdir(), 'ghost-guard-test-'));
const ledgerPath = join(sandbox, 'ledger.db');
const budgetPath = join(sandbox, 'budget.json');

// Tight limits so quota exhaustion is reachable in a test, and a night window
// that can be driven deterministically via the nowHour override.
writeFileSync(
  budgetPath,
  JSON.stringify({
    enabled: true,
    rampUpDays: 0,
    writeIntentMinChars: 10,
    requireWindowFocus: 'write',
    nightGuard: { enabled: true, startHour: 1, endHour: 7 },
    limits: {
      read: { perHour: 3, perDay: 100 },
      light: { perHour: 100, perDay: 100 },
      write: { perHour: 2, perDay: 2 },
    },
    domains: {
      'deepseek.com': { submitClass: 'light' },
    },
  }),
);

process.env.GHOST_LEDGER_PATH = ledgerPath;
process.env.GHOST_BUDGET_CONFIG = budgetPath;
// Pacing sleeps for minutes by design; irrelevant to these assertions.
process.env.PACING_ENABLED = '0';
// Same reason the other suites do this: the production 1-3s cooldown bookends
// every physical action, which would put this file into the tens of seconds.
process.env.COOLDOWN_MIN_MS = '1';
process.env.COOLDOWN_MAX_MS = '2';

const { domainOf } = await import('../../dist/guard/types.js');
const { checkPolicy, loadBudgetConfig, resetBudgetConfig, submitClassFor, effectiveLimit } =
  await import('../../dist/guard/budget.js');
const { recordAction, countActions, closeLedger } = await import('../../dist/guard/ledger.js');
const { noteTyping, peekWriteIntent, consumeWriteIntent, restoreWriteIntent, clearWriteIntent } =
  await import('../../dist/guard/write-intent.js');
const { handlePhysicalType } = await import('../../dist/mcp/server.js');

test.after(() => {
  closeLedger();
  rmSync(sandbox, { recursive: true, force: true });
});

// --- Domain grouping -----------------------------------------------------

test('domainOf: subdomains collapse to one quota bucket', () => {
  // One account spans www/creator/edith, so they must share a budget.
  assert.equal(domainOf('https://www.xiaohongshu.com/explore'), 'xiaohongshu.com');
  assert.equal(domainOf('https://creator.xiaohongshu.com/publish'), 'xiaohongshu.com');
  assert.equal(domainOf('https://edith.xiaohongshu.com/api/x'), 'xiaohongshu.com');
});

test('domainOf: bare host and garbage input degrade safely', () => {
  assert.equal(domainOf('https://example.com/'), 'example.com');
  assert.equal(domainOf('not a url'), 'unknown');
});

// --- Config loading ------------------------------------------------------

test('budget config: file values override defaults', () => {
  resetBudgetConfig();
  const cfg = loadBudgetConfig();
  assert.equal(cfg.writeIntentMinChars, 10);
  assert.equal(cfg.limits.write.perHour, 2);
});

test('budget config: documentation keys in JSON do not become config', () => {
  const withComment = join(sandbox, 'commented.json');
  writeFileSync(
    withComment,
    JSON.stringify({ _comment: ['not a setting'], writeIntentMinChars: 42 }),
  );
  const prev = process.env.GHOST_BUDGET_CONFIG;
  process.env.GHOST_BUDGET_CONFIG = withComment;
  resetBudgetConfig();
  const cfg = loadBudgetConfig();
  assert.equal(cfg.writeIntentMinChars, 42);
  assert.equal('_comment' in cfg, false, 'unknown keys must be dropped');
  process.env.GHOST_BUDGET_CONFIG = prev;
  resetBudgetConfig();
});

test('budget: per-domain submitClass overrides the default write tier', () => {
  resetBudgetConfig();
  // Asking DeepSeek a question is using the product, not publishing.
  assert.equal(submitClassFor('deepseek.com'), 'light');
  // Anything not called out is treated as publishing.
  assert.equal(submitClassFor('xiaohongshu.com'), 'write');
});

// --- Night guard ---------------------------------------------------------

test('night guard: blocks write inside the window', () => {
  resetBudgetConfig();
  const r = checkPolicy({ domain: 'example.com', writeClass: 'write', nowHour: 3 });
  assert.ok(r, 'expected a rejection at 03:00');
  assert.equal(r.error, 'night_guard');
});

test('night guard: allows write outside the window', () => {
  resetBudgetConfig();
  const r = checkPolicy({ domain: 'example.com', writeClass: 'write', nowHour: 14 });
  assert.equal(r, null);
});

test('night guard: does not block reading at night', () => {
  resetBudgetConfig();
  // A night owl reading a feed at 3am is entirely normal; only irreversible
  // actions are suspicious at that hour.
  const r = checkPolicy({ domain: 'example.com', writeClass: 'read', nowHour: 3 });
  assert.equal(r, null);
});

// --- Quota ---------------------------------------------------------------

test('quota: exhausting the hourly read cap refuses further actions', () => {
  resetBudgetConfig();
  const domain = 'quota-read.example';
  const now = Date.now();
  // read.perHour is 3 in the test config.
  for (let i = 0; i < 3; i++) {
    recordAction({
      ts: now,
      domain,
      actionType: 'navigate',
      writeClass: 'read',
      url: `https://${domain}/${i}`,
      detail: null,
    });
  }
  assert.equal(countActions({ domain, writeClass: 'read', sinceTs: now - 1000 }), 3);

  const r = checkPolicy({ domain, writeClass: 'read', nowHour: 14, nowTs: now });
  assert.ok(r, 'expected refusal once the cap is reached');
  assert.equal(r.error, 'budget_exceeded');
  assert.equal(r.detail.used, 3);
  assert.equal(r.detail.cap, 3);
});

test('quota: separate domains keep separate budgets', () => {
  resetBudgetConfig();
  const now = Date.now();
  // The previous test exhausted quota-read.example; an unrelated site must
  // be unaffected, otherwise one busy site would lock out everything.
  const r = checkPolicy({ domain: 'fresh.example', writeClass: 'read', nowHour: 14, nowTs: now });
  assert.equal(r, null);
});

test('quota: old actions fall outside the window and stop counting', () => {
  resetBudgetConfig();
  const domain = 'aged.example';
  const twoHoursAgo = Date.now() - 2 * 3600_000;
  for (let i = 0; i < 5; i++) {
    recordAction({
      ts: twoHoursAgo,
      domain,
      actionType: 'navigate',
      writeClass: 'read',
      url: `https://${domain}/${i}`,
      detail: null,
    });
  }
  const r = checkPolicy({ domain, writeClass: 'read', nowHour: 14 });
  assert.equal(r, null, 'actions from two hours ago must not consume this hour');
});

test('quota: rampUpDays=0 disables scaling so configured caps apply verbatim', () => {
  resetBudgetConfig();
  const limit = effectiveLimit('example.com', 'write');
  assert.equal(limit.perHour, 2);
  assert.equal(limit.perDay, 2);
});

// --- Write intent --------------------------------------------------------

/** WeakMap-keyed by page object; any stable object works as a stand-in. */
function fakePage(url = 'https://www.xiaohongshu.com/publish') {
  return { url: () => url };
}

test('write intent: short text does not arm the gate', () => {
  resetBudgetConfig();
  const page = fakePage();
  // A search query must not be billed as publishing.
  assert.equal(noteTyping(page, 5, 'https://x.example'), false);
  assert.equal(peekWriteIntent(page), null);
});

test('write intent: composing arms the gate', () => {
  resetBudgetConfig();
  const page = fakePage();
  assert.equal(noteTyping(page, 40, 'https://x.example'), true);
  assert.ok(peekWriteIntent(page));
});

test('write intent: consume clears it, so a second click is not a submit', () => {
  resetBudgetConfig();
  const page = fakePage();
  noteTyping(page, 40, 'https://x.example');
  const intent = consumeWriteIntent(page);
  assert.ok(intent);
  assert.equal(consumeWriteIntent(page), null);
});

test('write intent: restore preserves the original arming time', () => {
  resetBudgetConfig();
  const page = fakePage();
  noteTyping(page, 40, 'https://x.example');
  const intent = consumeWriteIntent(page);
  restoreWriteIntent(page, intent);
  const back = peekWriteIntent(page);
  assert.ok(back);
  // A rejection loop must not be able to extend the TTL indefinitely.
  assert.equal(back.armedAt, intent.armedAt);
});

test('write intent: clearing on navigate drops the pending submit', () => {
  resetBudgetConfig();
  const page = fakePage();
  noteTyping(page, 40, 'https://x.example');
  clearWriteIntent(page);
  assert.equal(peekWriteIntent(page), null);
});

// --- physical_type trailing-newline split -------------------------------

function mockActions() {
  const calls = { type: [], pressKeys: [] };
  return {
    calls,
    actions: {
      async click() {},
      async type(text, opts) {
        calls.type.push({ text, replace: opts?.replace });
        return text.length;
      },
      async pressKeys(keys) {
        calls.pressKeys.push(keys);
      },
      async scroll() {},
      async getA11y() {
        return [];
      },
    },
  };
}

function payloadOf(result) {
  return JSON.parse(result.content[0].text);
}

test('physical_type: trailing newline is split out from the typed body', async () => {
  // typeText maps '\n' to Enter, so without this split a single
  // physical_type("post\n") would compose AND publish in one ungated call.
  const { calls, actions } = mockActions();
  const result = await handlePhysicalType({ text: 'hello world' + '\n' }, { actions });
  assert.notEqual(result.isError, true);
  assert.deepEqual(
    calls.type.map((c) => c.text),
    ['hello world'],
    'the newline must not reach typeText',
  );
  assert.deepEqual(calls.pressKeys, ['Enter'], 'Enter is dispatched as its own action');
});

test('physical_type: reported chars still include the trailing newline', async () => {
  const { actions } = mockActions();
  const result = await handlePhysicalType({ text: 'abcd\n' }, { actions });
  // Splitting is an internal safety detail; the caller's accounting of what
  // it asked to be typed should not change because of it.
  assert.equal(payloadOf(result).chars, 5);
});

test('physical_type: embedded newlines are left intact for multi-line content', async () => {
  const { calls, actions } = mockActions();
  await handlePhysicalType({ text: 'line one\nline two' }, { actions });
  assert.deepEqual(calls.type.map((c) => c.text), ['line one\nline two']);
  assert.equal(calls.pressKeys.length, 0);
});
