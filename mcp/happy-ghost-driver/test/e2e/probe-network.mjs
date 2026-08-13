#!/usr/bin/env node
/** Quick CDP navigation probe for ghost-driver Chrome */
import { chromium } from 'playwright-core';

const CDP = process.env.CDP_ENDPOINT || 'http://127.0.0.1:9222';
const targets = [
  { name: 'doubao', url: 'https://www.doubao.com/chat/' },
  { name: 'deepseek', url: 'https://chat.deepseek.com/' },
  { name: 'baidu', url: 'https://www.baidu.com/' },
];

const browser = await chromium.connectOverCDP(CDP);
const ctx = browser.contexts()[0];
console.log('contexts', browser.contexts().length, 'pages', ctx.pages().length);

for (const t of targets) {
  const page = await ctx.newPage();
  const started = Date.now();
  let status = 'ok';
  let detail = '';
  try {
    const resp = await page.goto(t.url, { timeout: 45000, waitUntil: 'domcontentloaded' });
    detail = `status=${resp?.status()} title=${JSON.stringify(await page.title())} url=${page.url()}`;
  } catch (e) {
    status = 'fail';
    detail = String(e.message || e);
  }
  console.log(`${t.name}: ${status} ${Date.now() - started}ms ${detail}`);
  await page.close().catch(() => {});
}

await browser.close().catch(() => {});
