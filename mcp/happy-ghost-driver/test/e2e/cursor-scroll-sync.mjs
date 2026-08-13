#!/usr/bin/env node
// E2E regression test for the "ghost-cursor / Playwright mouse position
// desync" bug found while validating a GEO-check workflow against
// chat.deepseek.com.
//
// Bug: createPhysicalCursor() moves the mouse via ghost-cursor, which
// dispatches raw CDP Input.dispatchMouseEvent calls directly, bypassing
// Playwright's own Mouse state tracking. scroll() (physical_scroll) then
// calls page.mouse.wheel(), which fires at Playwright's *own* tracked
// position — still (0, 0) since it was never told the cursor moved. The
// wheel event lands wherever (0, 0) happens to be (e.g. the sidebar),
// not under the element the agent just clicked/hovered, so the intended
// container never scrolls.
//
// Fix: after ghost-cursor moves the mouse, also call page.mouse.move(x, y)
// (same coords -> no visible jump) purely to sync Playwright's tracker.
//
// This test builds a minimal repro page: two scrollable columns side by
// side. It moves the physical cursor into the *right* column, then calls
// scroll(), and asserts the right column scrolled while the left one
// (never hovered) did not.
//
// Run: node test/e2e/cursor-scroll-sync.mjs   (Chrome must be up on :9222,
// e.g. `bash scripts/dev-env.sh start --chrome-only`)

import { chromium } from 'playwright-core';
import { createPhysicalCursor } from '../../dist/physical/cursor.js';
import { scroll } from '../../dist/physical/scroll.js';

const CDP = process.env.CDP_ENDPOINT || 'http://127.0.0.1:9222';

function step(msg) {
  console.log(`\n\u001b[36m▶ ${msg}\u001b[0m`);
}
function ok(msg) {
  console.log(`\u001b[32m  ✓ ${msg}\u001b[0m`);
}
function fail(msg) {
  console.log(`\u001b[31m  ✗ ${msg}\u001b[0m`);
  process.exitCode = 1;
}

const HTML = `
<!doctype html>
<html><body style="margin:0">
  <div id="left" style="position:absolute;left:0;top:0;width:200px;height:200px;overflow:auto;border:1px solid #000;">
    <div style="height:1000px;">left content</div>
  </div>
  <div id="right" style="position:absolute;left:220px;top:0;width:200px;height:200px;overflow:auto;border:1px solid #000;">
    <div style="height:1000px;">right content</div>
  </div>
</body></html>
`;

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();
  await page.setViewportSize({ width: 800, height: 600 });
  await page.setContent(HTML);

  const scrollTops = () =>
    page.evaluate(() => ({
      left: document.getElementById('left').scrollTop,
      right: document.getElementById('right').scrollTop,
    }));

  step('physical cursor moves into the RIGHT column, then physical_scroll fires');
  const cursor = createPhysicalCursor(page);
  await cursor.move(320, 100); // centre of #right
  await scroll(page, 'down', 300);
  await new Promise((r) => setTimeout(r, 200));

  const after = await scrollTops();
  console.log('    scrollTops after:', after);
  if (after.right > 0 && after.left === 0) {
    ok(`right column scrolled (scrollTop=${after.right}), left untouched`);
  } else {
    fail(`expected right>0 and left===0, got ${JSON.stringify(after)}`);
  }

  await page.close();
  await browser.close();

  if (process.exitCode) {
    console.log('\n\u001b[31mFAILED\u001b[0m');
  } else {
    console.log('\n\u001b[32mALL PASSED\u001b[0m');
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
