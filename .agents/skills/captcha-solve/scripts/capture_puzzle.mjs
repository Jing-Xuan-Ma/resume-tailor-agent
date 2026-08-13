#!/usr/bin/env node
/**
 * 验证码裁图基建：CDP 截视口 → 按 CSS 盒裁 puzzle → 落盘后立刻退出。
 *
 * 不杀常驻 Chrome（禁止 browser.close）。供 Agent 在 captcha 闭环第 2 步调用。
 *
 * 用法（在仓库根）:
 *   node .agents/skills/captcha-solve/scripts/capture_puzzle.mjs \
 *     --left 694 --top 353.5 --width 340 --height 212 \
 *     --url-match lifeattiktok \
 *     --out-puzzle .debug/shots/captcha-puzzle.png
 */
import { chromium } from 'playwright-core';
import { parseArgs } from 'node:util';
import { writeFileSync, unlinkSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';

const { values } = parseArgs({
  options: {
    left: { type: 'string' },
    top: { type: 'string' },
    width: { type: 'string' },
    height: { type: 'string' },
    'viewport-w': { type: 'string', default: '1728' },
    endpoint: { type: 'string', default: 'http://127.0.0.1:9222' },
    'url-match': { type: 'string', default: '' },
    'out-full': { type: 'string', default: '.debug/shots/captcha-full-live.png' },
    'out-puzzle': { type: 'string', default: '.debug/shots/captcha-puzzle.png' },
  },
});

function num(name, raw) {
  const v = Number(raw);
  if (!Number.isFinite(v)) {
    console.error(JSON.stringify({ ok: false, error: `bad_${name}`, value: raw }));
    process.exit(2);
  }
  return v;
}

const left = num('left', values.left);
const top = num('top', values.top);
const width = num('width', values.width);
const height = num('height', values.height);
const viewportW = num('viewport-w', values['viewport-w']);
const outFull = resolve(process.cwd(), values['out-full']);
const outPuzzle = resolve(process.cwd(), values['out-puzzle']);

let exitCode = 0;
try {
  const browser = await chromium.connectOverCDP(values.endpoint);
  const pages = browser.contexts().flatMap((c) => c.pages());
  const match = values['url-match'];
  const page =
    (match && pages.find((p) => (p.url() || '').includes(match))) ||
    pages.find((p) => !/^chrome:\/\//.test(p.url() || '')) ||
    pages[0];
  if (!page) {
    console.error(JSON.stringify({ ok: false, error: 'no_page' }));
    exitCode = 1;
  } else {
    await page.bringToFront();
    const png = await page.screenshot({ type: 'png', fullPage: false });
    await mkdir(dirname(outFull), { recursive: true });
    await mkdir(dirname(outPuzzle), { recursive: true });
    await writeFile(outFull, png);

    const imgW = png.length >= 24 ? png.readUInt32BE(16) : viewportW * 2;
    const dsf = imgW / viewportW || 2;
    const l = Math.round(left * dsf);
    const t = Math.round(top * dsf);
    const w = Math.round(width * dsf);
    const h = Math.round(height * dsf);

    const tmp = `/tmp/captcha_crop_${process.pid}.py`;
    writeFileSync(
      tmp,
      [
        'from PIL import Image',
        `im = Image.open(${JSON.stringify(outFull)})`,
        `im.crop((${l}, ${t}, ${l + w}, ${t + h})).save(${JSON.stringify(outPuzzle)})`,
        "print('ok')",
        '',
      ].join('\n'),
    );
    const r = spawnSync('python3', [tmp], { encoding: 'utf8' });
    try {
      unlinkSync(tmp);
    } catch {
      /* ignore */
    }
    if (r.status !== 0) {
      console.error(
        JSON.stringify({
          ok: false,
          error: 'crop_failed',
          stderr: (r.stderr || '').slice(0, 400),
        }),
      );
      exitCode = 1;
    } else {
      console.log(
        JSON.stringify({
          ok: true,
          url: page.url(),
          out_full: outFull,
          out_puzzle: outPuzzle,
          dsf,
          crop_px: { left: l, top: t, width: w, height: h },
        }),
      );
    }
  }
} catch (err) {
  console.error(
    JSON.stringify({
      ok: false,
      error: 'capture_failed',
      message: err instanceof Error ? err.message : String(err),
    }),
  );
  exitCode = 1;
} finally {
  // CDP 连接会挂住事件循环；切勿 browser.close()（会杀常驻 Chrome）。
  process.exit(exitCode);
}
