// Phase 5 tests — take_screenshot: returns the raw image to the agent
// plus coordinate-mapping metadata.
//
// All tests run WITHOUT a real browser and WITHOUT any external API.
// The fake page returns a hand-built PNG buffer (with a known IHDR
// width/height) and a stubbed viewport probe.

import { test } from 'node:test';
import assert from 'node:assert/strict';

// Keep cooldown sub-millisecond in case any shared helper sleeps. The
// screenshot handler itself is NOT wrapped in withCooldown, but other
// imported modules read these on load.
process.env.COOLDOWN_MIN_MS = '1';
process.env.COOLDOWN_MAX_MS = '2';

import {
  handleTakeScreenshot,
  TakeScreenshotArgsSchema,
  decodeImageDimensions,
  createServer,
} from '../../dist/mcp/server.js';

// --- Helpers --------------------------------------------------------------

/** Build a minimal but header-valid PNG buffer with the given dimensions. */
function makePng(width, height) {
  const buf = Buffer.alloc(24);
  buf.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 0); // signature
  buf.writeUInt32BE(13, 8); // IHDR chunk length
  buf.write('IHDR', 12, 'ascii');
  buf.writeUInt32BE(width, 16);
  buf.writeUInt32BE(height, 20);
  return buf;
}

/** Fake Playwright page that drives captureScreenshotWithMeta. */
function makeShotPage({
  pngWidth = 2560,
  pngHeight = 1440,
  cssWidth = 1280,
  cssHeight = 720,
  dpr = 2,
  url = 'https://example.test/',
  title = 'Example',
} = {}) {
  const calls = { screenshot: [], evaluate: [] };
  return {
    calls,
    page: {
      async screenshot(opts) {
        calls.screenshot.push(opts);
        return makePng(pngWidth, pngHeight);
      },
      async evaluate(script) {
        calls.evaluate.push(script);
        return { cssWidth, cssHeight, dpr };
      },
      url() {
        return url;
      },
      async title() {
        return title;
      },
    },
  };
}

function findBlock(content, type) {
  return content.find((b) => b.type === type);
}

// --- decodeImageDimensions ------------------------------------------------

test('decodeImageDimensions: parses a PNG IHDR', () => {
  const b64 = makePng(800, 600).toString('base64');
  const dims = decodeImageDimensions(b64, 'image/png');
  assert.deepEqual(dims, { width: 800, height: 600 });
});

// --- handler: happy path --------------------------------------------------

test('take_screenshot: returns an image block + metadata text block', async () => {
  const { page } = makeShotPage({
    pngWidth: 2560,
    pngHeight: 1440,
    cssWidth: 1280,
    cssHeight: 720,
    dpr: 2,
    url: 'https://shop.test/cart',
    title: 'Cart',
  });

  const res = await handleTakeScreenshot({}, { page });
  assert.ok(!res.isError, 'not an error');
  assert.equal(res.content.length, 2, 'image + text');

  const img = findBlock(res.content, 'image');
  assert.ok(img, 'has image block');
  assert.equal(img.mimeType, 'image/png');
  assert.equal(img.data, makePng(2560, 1440).toString('base64'));

  const textBlock = findBlock(res.content, 'text');
  assert.ok(textBlock, 'has text block');
  const meta = JSON.parse(textBlock.text);
  assert.deepEqual(meta.viewport_css, { width: 1280, height: 720 });
  assert.deepEqual(meta.image_px, { width: 2560, height: 1440 });
  assert.equal(meta.device_scale_factor, 2);
  // The contract the agent relies on: image px = css px * scale factor.
  assert.equal(meta.image_px.width, meta.viewport_css.width * meta.device_scale_factor);
  assert.equal(meta.image_px.height, meta.viewport_css.height * meta.device_scale_factor);
  assert.equal(meta.url, 'https://shop.test/cart');
  assert.equal(meta.title, 'Cart');
  assert.equal(meta.truncated, false);
  assert.match(meta.coord_hint, /device_scale_factor/);
});

test('take_screenshot: device_scale_factor follows dpr for retina', async () => {
  const { page } = makeShotPage({
    pngWidth: 1280,
    pngHeight: 720,
    cssWidth: 1280,
    cssHeight: 720,
    dpr: 1,
  });
  const res = await handleTakeScreenshot({}, { page });
  const meta = JSON.parse(findBlock(res.content, 'text').text);
  assert.equal(meta.device_scale_factor, 1);
  assert.deepEqual(meta.image_px, { width: 1280, height: 720 });
});

// --- handler: no browser --------------------------------------------------

test('take_screenshot: returns browser_not_attached without a page', async () => {
  const res = await handleTakeScreenshot({}, {});
  assert.equal(res.isError, true);
  const payload = JSON.parse(res.content[0].text);
  assert.equal(payload.error, 'browser_not_attached');
});

test('take_screenshot: resolves the lazy getPage provider', async () => {
  const { page } = makeShotPage();
  const res = await handleTakeScreenshot({}, { getPage: async () => page });
  assert.ok(!res.isError);
  assert.equal(findBlock(res.content, 'image').type, 'image');
});

// --- args validation ------------------------------------------------------

test('TakeScreenshotArgsSchema: rejects unknown keys', () => {
  const r = TakeScreenshotArgsSchema.safeParse({ nope: 1 });
  assert.equal(r.success, false);
});

test('take_screenshot: rejects invalid arguments', async () => {
  const { page } = makeShotPage();
  const res = await handleTakeScreenshot({ full_page: 'yes' }, { page });
  assert.equal(res.isError, true);
  const payload = JSON.parse(res.content[0].text);
  assert.equal(payload.error, 'invalid_arguments');
});

// --- end-to-end through the server: registered ---------------------------

test('createServer: take_screenshot is registered and returns an image', async () => {
  const store = { insert: async () => {}, query: async () => [], close: async () => {} };
  const { page } = makeShotPage();
  const server = createServer({ store, page });
  const extra = { signal: new AbortController().signal };

  const listHandler = server._requestHandlers.get('tools/list');
  const list = await listHandler({ method: 'tools/list', params: {} }, extra);
  assert.ok(
    list.tools.some((t) => t.name === 'take_screenshot'),
    'take_screenshot listed',
  );
  assert.ok(
    !list.tools.some((t) => t.name === 'screenshot_and_locate'),
    'screenshot_and_locate must NOT be listed (removed; use the in-repo screen-locate skill)',
  );

  const callHandler = server._requestHandlers.get('tools/call');
  const res = await callHandler(
    { method: 'tools/call', params: { name: 'take_screenshot', arguments: {} } },
    extra,
  );
  assert.equal(findBlock(res.content, 'image').type, 'image');
});
