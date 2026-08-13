#!/usr/bin/env node
import { chromium } from 'playwright-core';
import { extractAssistantReply } from '../../dist/percept/extract-text.js';

const CDP = process.env.CDP_ENDPOINT || 'http://127.0.0.1:9222';
const targets = [
  { name: 'deepseek', urlPart: '3279a1f2', user: '女扮男装权谋古言推荐' },
  { name: 'doubao', urlPart: '38433763930157826', user: '古言查案小说推荐' },
];

const browser = await chromium.connectOverCDP(CDP);
const ctx = browser.contexts()[0];
let failed = false;

for (const t of targets) {
  const page = ctx.pages().find((p) => p.url().includes(t.urlPart));
  if (!page) {
    console.log(t.name, 'SKIP no tab');
    continue;
  }
  await page.bringToFront();
  const r = await extractAssistantReply(page, { userMessage: t.user });
  const noise = /深度思考|快速模式|AI-核能|置顶|两书对比/.test(r.text);
  const dup = (r.text.match(/段成式志异笔记/g) || []).length;
  console.log(`=== ${t.name} ===`);
  console.log('method:', r.method, 'chars:', r.char_count, 'steps:', r.scroll_steps);
  console.log('head:', r.text.slice(0, 80).replace(/\n/g, ' '));
  console.log('noise:', noise, 'dup_book:', dup);
  if (noise || r.char_count < 200) failed = true;
}

process.exit(failed ? 1 : 0);
