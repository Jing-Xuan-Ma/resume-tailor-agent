#!/usr/bin/env node
import { chromium } from 'playwright-core';
import { parseArgs } from 'node:util';
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';

const { values } = parseArgs({
  options: {
    out: { type: 'string' },
    endpoint: { type: 'string', default: 'http://127.0.0.1:9222' },
    'url-hint': { type: 'string', default: 'geo.c.yiling.top' },
    'url-match': { type: 'string' },
  },
});

const out = values.out;
if (!out) {
  console.error('missing --out');
  process.exit(1);
}

const browser = await chromium.connectOverCDP(values.endpoint);
const pages = browser.contexts().flatMap((c) => c.pages());
const hint = values['url-hint'];
const match = values['url-match'];

function scorePage(p) {
  const url = p.url() || '';
  if (match && url.includes(match)) return 100;
  if (hint && url.includes(hint)) return 10;
  if (!url.startsWith('chrome://')) return 1;
  return 0;
}

const page = [...pages].sort((a, b) => scorePage(b) - scorePage(a))[0];

if (!page) {
  console.error(JSON.stringify({ ok: false, error: 'no_page' }));
  process.exit(1);
}

await page.bringToFront();
await page.waitForTimeout(500);
const png = await page.screenshot({ type: 'png', fullPage: false });
await mkdir(dirname(out), { recursive: true });
await writeFile(out, png);
console.log(JSON.stringify({ ok: true, url: page.url(), out }));
// CDP 连接会挂住事件循环；切勿 browser.close()（会杀常驻 Chrome）。
process.exit(0);
