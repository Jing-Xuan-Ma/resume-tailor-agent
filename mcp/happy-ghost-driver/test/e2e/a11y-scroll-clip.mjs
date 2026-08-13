#!/usr/bin/env node
// E2E regression test for the "inner scrollable container clipping" bug
// found while validating a GEO-check workflow against chat.deepseek.com.
//
// Bug: get_page_accessibility_tree only checked an element's centre point
// against window.innerWidth/innerHeight. It did not check whether the
// element was clipped by an ancestor with its own overflow:auto/scroll
// (e.g. a chat app's message list scrolling independently of the page).
// That let scrolled-out items linger in results and could drop large
// elements (e.g. big <table>s) whose own unclipped extent exceeds the
// window even while their visible slice is on-screen.
//
// This test builds a minimal repro page directly in the already-running
// dev Chrome (CDP :9222), with an inner overflow:auto container holding
// three stacked blocks ("first"/"middle"/"last"). It asserts that only
// the block actually scrolled into view is reported by
// getPageAccessibilityTree, at three different scrollTop positions.
//
// Run: node test/e2e/a11y-scroll-clip.mjs   (Chrome must be up on :9222,
// e.g. `bash scripts/dev-env.sh start --chrome-only`)

import { chromium } from 'playwright-core';
import { getPageAccessibilityTree } from '../../dist/percept/a11y.js';

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
  <div id="scrollbox" style="width:300px;height:150px;overflow:auto;border:1px solid #000;">
    <div style="height:150px;display:flex;align-items:center;justify-content:center;">
      <button>first-block</button>
    </div>
    <div style="height:150px;display:flex;align-items:center;justify-content:center;">
      <button>middle-block</button>
    </div>
    <div style="height:150px;display:flex;align-items:center;justify-content:center;">
      <button>last-block</button>
    </div>
  </div>
</body></html>
`;

async function namesOf(page) {
  const nodes = await getPageAccessibilityTree(page, { maxNodes: 200 });
  return nodes.filter((n) => n.role === 'button').map((n) => n.name);
}

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();
  await page.setContent(HTML);

  step('scrollTop=0 -> only first-block should be visible');
  let names = await namesOf(page);
  console.log('    got:', names);
  if (names.includes('first-block') && !names.includes('middle-block') && !names.includes('last-block')) {
    ok('first-block only');
  } else {
    fail(`expected only [first-block], got [${names.join(', ')}]`);
  }

  step('scroll to middle-block -> only middle-block should be visible');
  await page.evaluate(() => {
    document.getElementById('scrollbox').scrollTop = 150;
  });
  names = await namesOf(page);
  console.log('    got:', names);
  if (names.includes('middle-block') && !names.includes('first-block') && !names.includes('last-block')) {
    ok('middle-block only');
  } else {
    fail(`expected only [middle-block], got [${names.join(', ')}]`);
  }

  step('scroll to last-block -> only last-block should be visible');
  await page.evaluate(() => {
    document.getElementById('scrollbox').scrollTop = 300;
  });
  names = await namesOf(page);
  console.log('    got:', names);
  if (names.includes('last-block') && !names.includes('first-block') && !names.includes('middle-block')) {
    ok('last-block only');
  } else {
    fail(`expected only [last-block], got [${names.join(', ')}]`);
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
