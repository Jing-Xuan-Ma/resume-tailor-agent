// Phase 3 tests — physical control / ghost hand.
//
// All tests run WITHOUT a real browser. The handlers' action surface is
// injected as a mock; the cooldown helper is tested with sub-ms bounds
// so the suite finishes in milliseconds. The underlying physical-layer
// functions (typeText, scroll) are exercised via mock page objects.
//
// Coverage areas:
//   - cooldown bounds + env override
//   - flattenA11y dedup + cap
//   - physical handlers: invalid args, missing page, happy path
//   - typeText: per-char keyboard.type (spy on mock page.keyboard)
//   - scroll: per-segment wheel (spy on mock page.mouse.wheel)

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  handleGetA11yTree,
  handlePhysicalClick,
  handlePhysicalType,
  handlePhysicalScroll,
  GetA11yArgsSchema,
  PhysicalClickArgsSchema,
  PhysicalTypeArgsSchema,
  PhysicalScrollArgsSchema,
} from '../../dist/mcp/server.js';
import { flattenA11y } from '../../dist/percept/a11y.js';
import {
  randomSleep,
  getCooldownBounds,
  withCooldown,
} from '../../dist/physical/cooldown.js';
import { typeText } from '../../dist/physical/keyboard.js';
import { scroll } from '../../dist/physical/scroll.js';

// Set sub-millisecond cooldown bounds so every withCooldown test
// resolves in <5ms. (Default is 1000-3000ms.)
process.env.COOLDOWN_MIN_MS = '1';
process.env.COOLDOWN_MAX_MS = '2';

function decodePayload(result) {
  assert.ok(result && Array.isArray(result.content), 'content array present');
  assert.equal(result.content.length, 1, 'exactly one text block');
  return JSON.parse(result.content[0].text);
}

/** Build a mock PhysicalActions that records every call. */
function makeMockActions(overrides = {}) {
  const calls = {
    click: [],
    type: [],
    scroll: [],
    getA11y: [],
  };
  return {
    calls,
    actions: {
      async click(x, y) {
        calls.click.push({ x, y });
        overrides.onClick?.(x, y);
      },
      async type(text, opts) {
        calls.type.push({ text, replace: opts?.replace });
        return overrides.onType ? overrides.onType(text, opts) : text.length;
      },
      async scroll(direction, distancePx) {
        calls.scroll.push({ direction, distancePx });
        overrides.onScroll?.(direction, distancePx);
      },
      async getA11y(maxNodes) {
        calls.getA11y.push({ maxNodes });
        return overrides.onA11y ? overrides.onA11y(maxNodes) : [];
      },
    },
  };
}

// --- Schema validation ---------------------------------------------------

test('schema: physical_click rejects negative x', () => {
  const r = PhysicalClickArgsSchema.safeParse({ x: -1, y: 0 });
  assert.equal(r.success, false);
});

test('schema: physical_click rejects missing y', () => {
  const r = PhysicalClickArgsSchema.safeParse({ x: 1 });
  assert.equal(r.success, false);
});

test('schema: physical_click rejects extra selector field (no selectors allowed)', () => {
  // CRITICAL: confirm the physical-click schema does not accept a
  // selector-style property. Any string named "selector" / "css" /
  // "xpath" must be rejected by .strict().
  const r = PhysicalClickArgsSchema.safeParse({ x: 1, y: 1, selector: '#foo' });
  assert.equal(r.success, false, '.strict() must reject unknown properties');
});

test('schema: physical_click accepts positive coords', () => {
  const r = PhysicalClickArgsSchema.safeParse({ x: 100, y: 250.5 });
  assert.equal(r.success, true);
});

test('schema: physical_type rejects empty text', () => {
  const r = PhysicalTypeArgsSchema.safeParse({ text: '' });
  assert.equal(r.success, false);
});

test('schema: physical_type rejects oversized text (>2000)', () => {
  const r = PhysicalTypeArgsSchema.safeParse({ text: 'x'.repeat(2001) });
  assert.equal(r.success, false);
});

test('schema: physical_type accepts optional replace flag', () => {
  const r = PhysicalTypeArgsSchema.safeParse({ text: '博物馆文创', replace: true });
  assert.equal(r.success, true);
  assert.equal(r.data.replace, true);
});

test('schema: physical_scroll rejects invalid direction', () => {
  const r = PhysicalScrollArgsSchema.safeParse({ direction: 'sideways', distance_px: 100 });
  assert.equal(r.success, false);
});

test('schema: physical_scroll rejects zero distance', () => {
  const r = PhysicalScrollArgsSchema.safeParse({ direction: 'down', distance_px: 0 });
  assert.equal(r.success, false);
});

test('schema: get_a11y rejects negative max_nodes', () => {
  const r = GetA11yArgsSchema.safeParse({ max_nodes: -1 });
  assert.equal(r.success, false);
});

// --- Cooldown ------------------------------------------------------------

test('cooldown: env override yields sub-3ms random sleep', async () => {
  // COOLDOWN_MIN_MS=1, COOLDOWN_MAX_MS=2 was set at module load.
  // Sanity-check that the env override is honoured: with the default
  // production window (1000-3000ms) the elapsed time would be >= 1000ms,
  // so a 50ms upper bound is enough to prove the env vars took effect
  // while leaving generous slack for CI timer scheduling jitter.
  const start = Date.now();
  await randomSleep();
  const elapsed = Date.now() - start;
  assert.ok(elapsed <= 50, `randomSleep should be ~1-2ms under env override, took ${elapsed}ms`);
});

test('cooldown: explicit min/max bounds honoured', async () => {
  const start = Date.now();
  await randomSleep(10, 10);
  const elapsed = Date.now() - start;
  assert.ok(elapsed >= 8, `randomSleep(10,10) should be ~10ms, took ${elapsed}ms`);
});

test('cooldown: getCooldownBounds reads env', () => {
  const b = getCooldownBounds();
  assert.equal(b.minMs, 1);
  assert.equal(b.maxMs, 2);
});

test('cooldown: withCooldown runs action exactly once and returns its value', async () => {
  let calls = 0;
  const result = await withCooldown(async () => {
    calls += 1;
    return 'ok';
  });
  assert.equal(calls, 1);
  assert.equal(result, 'ok');
});

test('cooldown: withCooldown rethrows and still sleeps after', async () => {
  // We only assert that the rejection propagates; the post-sleep is
  // an internal detail but must not mask the error.
  await assert.rejects(
    () =>
      withCooldown(async () => {
        throw new Error('boom');
      }),
    /boom/,
  );
});

// --- flattenA11y --------------------------------------------------------

test('flattenA11y: dedups adjacent identical nodes', () => {
  const raw = [
    { role: 'button', name: 'OK', x: 1, y: 2, width: 10, height: 10 },
    { role: 'button', name: 'OK', x: 1, y: 2, width: 10, height: 10 },
    { role: 'button', name: 'OK', x: 1, y: 2, width: 10, height: 10 },
    { role: 'link', name: 'Cancel', x: 5, y: 6, width: 20, height: 5 },
  ];
  const out = flattenA11y(raw);
  assert.equal(out.length, 2);
  assert.equal(out[0].name, 'OK');
  assert.equal(out[1].name, 'Cancel');
});

test('flattenA11y: keeps non-adjacent duplicates', () => {
  const a = { role: 'button', name: 'OK', x: 1, y: 2, width: 10, height: 10 };
  const b = { role: 'link', name: 'X', x: 3, y: 4, width: 5, height: 5 };
  const out = flattenA11y([a, b, a]);
  assert.equal(out.length, 3, 'non-adjacent dup is preserved');
});

test('flattenA11y: caps to maxNodes', () => {
  const raw = [];
  for (let i = 0; i < 500; i++) {
    raw.push({ role: 'button', name: `b${i}`, x: i, y: i, width: 1, height: 1 });
  }
  const out = flattenA11y(raw, 10);
  assert.equal(out.length, 10);
});

// --- Handlers: missing page ---------------------------------------------

test('click handler: returns browser_not_attached when no page', async () => {
  const result = await handlePhysicalClick({ x: 1, y: 2 }, {});
  assert.equal(result.isError, true);
  const payload = decodePayload(result);
  assert.equal(payload.error, 'browser_not_attached');
});

test('type handler: returns browser_not_attached when no page', async () => {
  const result = await handlePhysicalType({ text: 'hi' }, {});
  assert.equal(result.isError, true);
  const payload = decodePayload(result);
  assert.equal(payload.error, 'browser_not_attached');
});

test('scroll handler: returns browser_not_attached when no page', async () => {
  const result = await handlePhysicalScroll({ direction: 'down', distance_px: 100 }, {});
  assert.equal(result.isError, true);
  const payload = decodePayload(result);
  assert.equal(payload.error, 'browser_not_attached');
});

test('a11y handler: returns browser_not_attached when no page', async () => {
  const result = await handleGetA11yTree({}, {});
  assert.equal(result.isError, true);
  const payload = decodePayload(result);
  assert.equal(payload.error, 'browser_not_attached');
});

// --- Handlers: invalid args ---------------------------------------------

test('click handler: rejects negative coords', async () => {
  const result = await handlePhysicalClick({ x: -1, y: 0 }, makeMockActions().actions);
  assert.equal(result.isError, true);
});

test('type handler: rejects empty text', async () => {
  const result = await handlePhysicalType({ text: '' }, makeMockActions().actions);
  assert.equal(result.isError, true);
});

// --- Handlers: happy path with injected actions -------------------------

test('click handler: invokes injected action with coords and returns ok', async () => {
  const { calls, actions } = makeMockActions();
  const result = await handlePhysicalClick({ x: 42, y: 99 }, { actions });
  assert.equal(result.isError, undefined);
  assert.equal(calls.click.length, 1);
  assert.deepEqual(calls.click[0], { x: 42, y: 99 });
  const payload = decodePayload(result);
  assert.equal(payload.ok, true);
  assert.equal(payload.x, 42);
  assert.equal(payload.y, 99);
  assert.ok(payload.durationMs >= 0);
});

test('type handler: invokes injected type and returns chars count', async () => {
  const { calls, actions } = makeMockActions();
  const result = await handlePhysicalType({ text: 'hello' }, { actions });
  assert.equal(result.isError, undefined);
  assert.equal(calls.type.length, 1);
  assert.equal(calls.type[0].text, 'hello');
  assert.equal(calls.type[0].replace, undefined);
  const payload = decodePayload(result);
  assert.equal(payload.ok, true);
  assert.equal(payload.chars, 5);
  assert.equal(payload.replaced, false);
});

test('type handler: passes replace=true to injected type', async () => {
  const { calls, actions } = makeMockActions();
  const result = await handlePhysicalType(
    { text: '博物馆文创', replace: true },
    { actions },
  );
  assert.equal(result.isError, undefined);
  assert.equal(calls.type.length, 1);
  assert.equal(calls.type[0].replace, true);
  const payload = decodePayload(result);
  assert.equal(payload.replaced, true);
});

test('scroll handler: invokes injected scroll with direction+distance', async () => {
  const { calls, actions } = makeMockActions();
  const result = await handlePhysicalScroll(
    { direction: 'up', distance_px: 500 },
    { actions },
  );
  assert.equal(result.isError, undefined);
  assert.equal(calls.scroll.length, 1);
  assert.deepEqual(calls.scroll[0], { direction: 'up', distancePx: 500 });
  const payload = decodePayload(result);
  assert.equal(payload.ok, true);
  assert.equal(payload.direction, 'up');
  assert.equal(payload.distancePx, 500);
});

test('a11y handler: invokes injected getA11y and returns count+items', async () => {
  const fakeNodes = [
    { role: 'button', name: 'OK', x: 1, y: 2, width: 10, height: 10 },
    { role: 'link', name: 'Home', x: 5, y: 6, width: 30, height: 12 },
  ];
  const { calls, actions } = makeMockActions({
    onA11y: () => fakeNodes,
  });
  const result = await handleGetA11yTree({}, { actions });
  assert.equal(result.isError, undefined);
  assert.equal(calls.getA11y.length, 1);
  const payload = decodePayload(result);
  assert.equal(payload.count, 2);
  assert.deepEqual(payload.items, fakeNodes);
});

test('a11y handler: forwards max_nodes to action', async () => {
  const { calls, actions } = makeMockActions({ onA11y: () => [] });
  await handleGetA11yTree({ max_nodes: 50 }, { actions });
  assert.equal(calls.getA11y[0].maxNodes, 50);
});

// --- Error surfacing ----------------------------------------------------

test('click handler: converts thrown action error into structured error', async () => {
  const { actions } = makeMockActions({
    onClick: () => { throw new Error('cursor busted'); },
  });
  const result = await handlePhysicalClick({ x: 1, y: 1 }, { actions });
  assert.equal(result.isError, true);
  const payload = decodePayload(result);
  assert.equal(payload.error, 'click_failed');
  assert.match(payload.message, /cursor busted/);
});

test('a11y handler: converts thrown getA11y error into structured error', async () => {
  const { actions } = makeMockActions({
    onA11y: () => { throw new Error('evaluate failed'); },
  });
  const result = await handleGetA11yTree({}, { actions });
  assert.equal(result.isError, true);
  const payload = decodePayload(result);
  assert.equal(payload.error, 'a11y_failed');
});

// --- Physical-layer unit tests (mock page) ------------------------------
// These exercise the real typeText / scroll implementations against a
// mock page, so we know that "per-character delay" and "segmented wheel"
// actually happen — not just that handlers route to the right callback.

/** Minimal mock of a Playwright page for keyboard/wheel tests. */
function makeMockPage() {
  const keyboard = {
    typedChars: [],
    pressedKeys: [],
    type(ch) {
      keyboard.typedChars.push(ch);
      return Promise.resolve();
    },
    press(key) {
      keyboard.pressedKeys.push(key);
      return Promise.resolve();
    },
  };
  const mouse = {
    wheelCalls: [], // [{ deltaX, deltaY }]
    wheel(deltaX, deltaY) {
      mouse.wheelCalls.push({ deltaX, deltaY });
      return Promise.resolve();
    },
  };
  return { keyboard, mouse };
}

test('typeText: types each character one at a time via keyboard.type', async () => {
  const page = makeMockPage();
  // Use 0-delay bounds so the test runs fast.
  const n = await typeText(page, 'abc', { minDelayMs: 0, maxDelayMs: 1 });
  assert.equal(n, 3);
  assert.deepEqual(page.keyboard.typedChars, ['a', 'b', 'c']);
  assert.equal(page.keyboard.pressedKeys.length, 0, 'no Enter for plain text');
});

test('typeText: newline maps to keyboard.press("Enter")', async () => {
  const page = makeMockPage();
  await typeText(page, 'a\nb', { minDelayMs: 0, maxDelayMs: 1 });
  // a then Enter then b
  assert.deepEqual(page.keyboard.typedChars, ['a', 'b']);
  assert.deepEqual(page.keyboard.pressedKeys, ['Enter']);
});

test('typeText: replace=true selects all before typing', async () => {
  const page = makeMockPage();
  const mod = process.platform === 'darwin' ? 'Meta' : 'Control';
  await typeText(page, '新词', { minDelayMs: 0, maxDelayMs: 0, replace: true });
  assert.deepEqual(page.keyboard.pressedKeys[0], `${mod}+a`);
  assert.deepEqual(page.keyboard.typedChars, ['新', '词']);
});

test('typeText: rejects text over cap', async () => {
  const page = makeMockPage();
  await assert.rejects(
    () => typeText(page, 'x'.repeat(2001), { minDelayMs: 0, maxDelayMs: 1 }),
    /exceeds cap/,
  );
});

test('scroll: splits distance into multiple wheel events', async () => {
  const page = makeMockPage();
  await scroll(page, 'down', 1000, {
    segmentsMin: 3,
    segmentsMax: 3,
    delayMinMs: 0,
    delayMaxMs: 1,
  });
  // Should have made between 1 and 3 wheel calls (some segments may be
  // zero-sized and skipped), but always >= 1 and the deltas sum back
  // to the requested distance.
  assert.ok(page.mouse.wheelCalls.length >= 1, 'at least one wheel call');
  assert.ok(page.mouse.wheelCalls.length <= 3, 'at most three wheel calls');
  const totalDeltaY = page.mouse.wheelCalls.reduce((s, c) => s + c.deltaY, 0);
  assert.ok(
    Math.abs(totalDeltaY - 1000) < 0.001,
    `sum of deltaY should equal distancePx=1000, got ${totalDeltaY}`,
  );
  // All deltaY positive for 'down'.
  assert.ok(
    page.mouse.wheelCalls.every((c) => c.deltaY > 0),
    'every segment has positive deltaY for down',
  );
});

test('scroll: up direction yields negative deltaY', async () => {
  const page = makeMockPage();
  await scroll(page, 'up', 500, {
    segmentsMin: 2,
    segmentsMax: 2,
    delayMinMs: 0,
    delayMaxMs: 1,
  });
  const totalDeltaY = page.mouse.wheelCalls.reduce((s, c) => s + c.deltaY, 0);
  assert.ok(
    Math.abs(totalDeltaY + 500) < 0.001,
    `sum of deltaY should equal -distancePx=-500, got ${totalDeltaY}`,
  );
  assert.ok(
    page.mouse.wheelCalls.every((c) => c.deltaY < 0),
    'every segment has negative deltaY for up',
  );
});

test('scroll: rejects invalid direction', async () => {
  const page = makeMockPage();
  await assert.rejects(
    // Cast to any-ish: the runtime guard rejects before any page call.
    () => scroll(page, 'sideways' /* invalid */, 100),
    /direction must be 'up' or 'down'/,
  );
});

test('scroll: rejects distance over cap', async () => {
  const page = makeMockPage();
  await assert.rejects(
    () => scroll(page, 'down', 100_001),
    /exceeds cap/,
  );
});
