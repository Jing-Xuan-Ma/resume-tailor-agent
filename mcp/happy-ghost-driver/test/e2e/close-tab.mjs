#!/usr/bin/env node
// E2E test for PageProvider.closeTab(), the tool added after the
// geo-qa-runner skill's doubao run left orphaned background tabs
// (citation links open in a new tab with no way to clean them up).
//
// Covers two cases:
//   1. Closing a background (non-active) tab leaves the active page alone.
//   2. Closing the currently-active tab clears the cached page so the next
//      getPage() picks a fresh one instead of operating on a closed target.
//
// Run: node test/e2e/close-tab.mjs   (Chrome must be up on :9222,
// e.g. `bash scripts/dev-env.sh start --chrome-only`)

import { chromium } from 'playwright-core';
import { createPageProvider } from '../../dist/attach/provider.js';

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

async function main() {
  const provider = createPageProvider({ endpoint: CDP });

  step('open two tabs: background + active');
  const bg = await provider.navigate('https://example.com/', { newTab: true });
  const active = await provider.navigate('https://example.org/', { newTab: true });
  console.log('    bg:', bg?.url, ' active:', active?.url);

  const tabsBefore = await provider.listTabs();
  const bgIndex = tabsBefore.findIndex((t) => t.url === bg.url);
  const activeIndex = tabsBefore.findIndex((t) => t.url === active.url);
  if (bgIndex < 0 || activeIndex < 0) {
    fail(`could not find both tabs in listTabs(): ${JSON.stringify(tabsBefore)}`);
    return cleanup(provider);
  }
  ok(`found both tabs (bgIndex=${bgIndex}, activeIndex=${activeIndex})`);

  step('close the background tab; active page must be unaffected');
  const closeBgRes = await provider.closeTab(bgIndex);
  if (closeBgRes?.ok && closeBgRes.closedUrl === bg.url) {
    ok(`closeTab reported closedUrl=${closeBgRes.closedUrl}`);
  } else {
    fail(`unexpected closeTab result: ${JSON.stringify(closeBgRes)}`);
  }
  const page = await provider.getPage();
  if (page && page.url() === active.url && !page.isClosed()) {
    ok('active page still live and unchanged after closing the background tab');
  } else {
    fail(`active page unexpectedly affected: url=${page?.url()}`);
  }

  step('close_tab on an out-of-range index returns null (tab_not_found)');
  const badRes = await provider.closeTab(999);
  if (badRes === null) {
    ok('out-of-range index returned null as expected');
  } else {
    fail(`expected null, got ${JSON.stringify(badRes)}`);
  }

  step('close the now-active tab; provider must recover a fresh page afterwards');
  const tabsBeforeActiveClose = await provider.listTabs();
  const stillActiveIndex = tabsBeforeActiveClose.findIndex((t) => t.url === active.url);
  await provider.closeTab(stillActiveIndex);
  const recovered = await provider.getPage();
  if (recovered && !recovered.isClosed()) {
    ok(`provider recovered a live page after its active tab was closed (url=${recovered.url()})`);
  } else {
    fail('provider failed to recover a live page after closing the active tab');
  }

  await cleanup(provider);
}

async function cleanup(provider) {
  await provider.dispose();
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
