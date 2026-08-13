#!/usr/bin/env node
// E2E regression test for two A11y perception gaps found while improving
// the geo-qa-runner skill against chat.deepseek.com's citation UI:
//
// 1. DeepSeek's "9 个网页" citation-count toggle is a bare <span> with a
//    React onClick — no <button>, no role attribute. get_page_accessibility_tree
//    silently dropped it (no implicit/explicit role => filtered as noise),
//    so the agent had no role/name to click it by. Fix: an element with
//    cursor:pointer AND its own direct text node (not just descendant
//    text, which would also flag every ancestor wrapper) is now promoted
//    to a synthetic role: 'button'.
// 2. Once the citation sidebar is open, its <a href> cards only exposed
//    visible text (title+date+snippet) via `name`, never the actual URL.
//    Fix: A11yNode now carries an optional `url` (el.href) for real
//    anchor elements.
//
// Run: node test/e2e/a11y-clickable-div-and-href.mjs (Chrome up on :9222)

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
  <div id="card" style="cursor:pointer;padding:20px;border:1px solid #000;">
    <img src="/favicon.ico" />
    <span id="label" style="cursor:pointer;">9 个网页</span>
  </div>
  <a id="cite" href="https://example.com/some-article?x=1">中工网 2025/09/01 一篇文章标题</a>
</body></html>
`;

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();
  await page.setContent(HTML);

  const nodes = await getPageAccessibilityTree(page, { maxNodes: 200 });

  step('bare <span> with cursor:pointer + own text -> promoted to role:button');
  const badge = nodes.find((n) => n.name === '9 个网页');
  if (badge && badge.role === 'button') {
    ok(`found as {role: 'button', name: '9 个网页'} at (${badge.x}, ${badge.y})`);
  } else {
    fail(`expected a button node named '9 个网页', got: ${JSON.stringify(badge)}`);
  }

  step('the pointer-cursor wrapper <div> (no direct text of its own) must NOT also be flagged');
  const wrapperDuped = nodes.filter((n) => n.name.includes('9 个网页')).length;
  if (wrapperDuped === 1) {
    ok('exactly one node reports this label (no ancestor-wrapper duplication)');
  } else {
    fail(`expected exactly 1 matching node, got ${wrapperDuped}`);
  }

  step('<a href> exposes a real url field');
  const cite = nodes.find((n) => n.role === 'link' && n.name.includes('中工网'));
  if (cite && cite.url === 'https://example.com/some-article?x=1') {
    ok(`url captured: ${cite.url}`);
  } else {
    fail(`expected url 'https://example.com/some-article?x=1', got: ${JSON.stringify(cite)}`);
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
