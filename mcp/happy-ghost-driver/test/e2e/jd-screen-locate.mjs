#!/usr/bin/env node
// E2E: JD.com search via screen-locate (UI-TARS) + ghost-driver-mcp.
// Flow: take_screenshot -> locate.py -> physical_click/type -> verify.
//
// Run: npm run test:e2e:jd   (or: node test/e2e/jd-screen-locate.mjs)

import { spawn, execFileSync } from 'node:child_process';
import { createWriteStream, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const SERVER_JS = join(ROOT, 'dist', 'mcp', 'run-server.js');
const CDP = 'http://127.0.0.1:9222';
const SITE_URL = 'https://www.jd.com/';
const QUERY = '篮球';
const LOCATE_SCRIPT =
  process.env.SCREEN_LOCATE_SCRIPT ||
  join(ROOT, '.cursor/skills/screen-locate/scripts/locate.py');
const LOG_DIR = join(ROOT, '.debug', 'logs');
const SHOT_DIR = join(ROOT, '.debug', 'shots');

const ts = () => new Date().toISOString().replace(/[:.]/g, '-');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function step(msg) {
  console.log(`\n\u001b[36m▶ ${msg}\u001b[0m`);
}
function ok(msg) {
  console.log(`\u001b[32m  ✓ ${msg}\u001b[0m`);
}
function info(msg) {
  console.log(`    ${msg}`);
}
function fail(msg) {
  console.log(`\u001b[31m  ✗ ${msg}\u001b[0m`);
}

async function cdp(path, method = 'GET') {
  const res = await fetch(`${CDP}${path}`, { method });
  if (!res.ok) throw new Error(`CDP ${method} ${path} -> ${res.status}`);
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function waitForCdp(timeoutMs = 12000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      await cdp('/json/version');
      return true;
    } catch {
      await sleep(400);
    }
  }
  return false;
}

let nextId = 0;
function rpc(proc, method, params) {
  const id = ++nextId;
  proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
  return waitFor(proc, (m) => m.id === id);
}
function notify(proc, method, params) {
  proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n');
}
function waitFor(proc, predicate, timeoutMs = 120000) {
  return new Promise((res, rej) => {
    const t = setTimeout(() => {
      proc.stdout.off('data', onData);
      rej(new Error('RPC timeout'));
    }, timeoutMs);
    const onData = (chunk) => {
      proc._buf = (proc._buf || '') + chunk.toString('utf8');
      let nl;
      while ((nl = proc._buf.indexOf('\n')) >= 0) {
        const line = proc._buf.slice(0, nl).trim();
        proc._buf = proc._buf.slice(nl + 1);
        if (!line) continue;
        let msg;
        try {
          msg = JSON.parse(line);
        } catch {
          continue;
        }
        if (predicate(msg)) {
          clearTimeout(t);
          proc.stdout.off('data', onData);
          res(msg);
          return;
        }
      }
    };
    proc.stdout.on('data', onData);
  });
}

function parseToolResponse(resp) {
  const content = resp?.result?.content ?? [];
  const isError = resp?.result?.isError === true;
  const image = content.find((b) => b.type === 'image');
  const textBlock = content.find((b) => b.type === 'text');
  let payload = null;
  if (textBlock?.text) {
    try {
      payload = JSON.parse(textBlock.text);
    } catch {
      payload = { raw: textBlock.text };
    }
  }
  return { isError, content, image, payload };
}

function toolResult(resp) {
  const txt = resp?.result?.content?.[0]?.text;
  const payload = txt ? JSON.parse(txt) : null;
  return { isError: resp?.result?.isError === true, payload };
}

async function takeScreenshot(proc, label) {
  const resp = await rpc(proc, 'tools/call', {
    name: 'take_screenshot',
    arguments: {},
  });
  const parsed = parseToolResponse(resp);
  if (parsed.isError) {
    throw new Error(`take_screenshot failed: ${JSON.stringify(parsed.payload)}`);
  }
  if (!parsed.image?.data) {
    throw new Error('take_screenshot: no image block in response');
  }
  const shotPath = join(SHOT_DIR, `${label}-${ts()}.png`);
  writeFileSync(shotPath, Buffer.from(parsed.image.data, 'base64'));
  ok(`screenshot saved -> ${shotPath}`);
  info(`meta: ${JSON.stringify(parsed.payload)}`);
  return { shotPath, meta: parsed.payload };
}

function runLocate(imagePath, instruction) {
  info(`locate: "${instruction}"`);
  const out = execFileSync(
    'uv',
    ['run', LOCATE_SCRIPT, '--image', imagePath, '--instruction', instruction, '--verbose'],
    { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 10 * 1024 * 1024 },
  );
  const result = JSON.parse(out);
  if (!result.found) {
    throw new Error(`locate not found: ${JSON.stringify(result)}`);
  }
  info(`locate thought: ${result.thought ?? '(none)'}`);
  info(`locate image coords: ${JSON.stringify(result.coordinates.image)}`);
  return result;
}

function imageToCss(imageX, imageY, deviceScaleFactor) {
  return {
    x: Math.round(imageX / deviceScaleFactor),
    y: Math.round(imageY / deviceScaleFactor),
  };
}

async function main() {
  mkdirSync(LOG_DIR, { recursive: true });
  mkdirSync(SHOT_DIR, { recursive: true });
  const logPath = join(LOG_DIR, `jd-screen-locate-${ts()}.log`);
  const logStream = createWriteStream(logPath, { flags: 'a' });
  console.log(`MCP logs -> ${logPath}`);

  step('1/9 Clean slate');
  try {
    execFileSync('bash', ['scripts/dev-env.sh', 'stop'], { cwd: ROOT, stdio: 'ignore' });
  } catch {
    /* ignore */
  }
  await sleep(500);
  ok('stopped');

  step(`2/9 Launch Chrome and open ${SITE_URL}`);
  execFileSync('bash', ['scripts/launch-chrome.sh'], { cwd: ROOT, stdio: 'ignore' });
  if (!(await waitForCdp())) throw new Error('Chrome CDP did not come up');
  ok('Chrome CDP reachable');
  const opened = await cdp(`/json/new?${encodeURIComponent(SITE_URL)}`, 'PUT');
  info(`opened tab ${opened.id} -> ${opened.url}`);
  const tabs = await cdp('/json');
  for (const t of tabs) {
    if (t.type === 'page' && t.id !== opened.id) {
      await cdp(`/json/close/${t.id}`).catch(() => {});
    }
  }
  await sleep(3000);
  ok('JD tab ready');

  step('3/9 Spawn MCP server');
  const proc = spawn(process.execPath, [SERVER_JS], {
    cwd: ROOT,
    env: {
      ...process.env,
      DB_PATH: join(ROOT, 'data', 'intercepted.db'),
      CDP_ENDPOINT: CDP,
      AUTO_LAUNCH_CHROME: '1',
      COOLDOWN_MIN_MS: '300',
      COOLDOWN_MAX_MS: '600',
    },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  proc.stderr.on('data', (c) => {
    const s = c.toString('utf8');
    logStream.write(s);
    process.stdout.write(s.replace(/^/gm, '\u001b[90m[mcp]\u001b[0m '));
  });
  await rpc(proc, 'initialize', {
    protocolVersion: '2025-06-18',
    capabilities: {},
    clientInfo: { name: 'jd-screen-locate', version: '0.0.1' },
  });
  notify(proc, 'notifications/initialized');
  ok('MCP initialized');

  let passed = false;
  try {
    step('4/9 take_screenshot + screen-locate 搜索框');
    const shot1 = await takeScreenshot(proc, 'jd-home');
    const dsf = shot1.meta.device_scale_factor ?? 1;
    const locate1 = runLocate(shot1.shotPath, '点击页面顶部的搜索输入框');
    const boxCss = imageToCss(
      locate1.coordinates.image.x,
      locate1.coordinates.image.y,
      dsf,
    );
    ok(`search box CSS coords: ${boxCss.x}, ${boxCss.y} (dsf=${dsf})`);

    step('5/9 physical_click 搜索框 + physical_type 篮球');
    const click1 = toolResult(
      await rpc(proc, 'tools/call', {
        name: 'physical_click',
        arguments: boxCss,
      }),
    );
    if (click1.isError) throw new Error(`click error: ${JSON.stringify(click1.payload)}`);
    ok(`clicked search box (${click1.payload.durationMs}ms)`);

    const typeRes = toolResult(
      await rpc(proc, 'tools/call', {
        name: 'physical_type',
        arguments: { text: QUERY },
      }),
    );
    if (typeRes.isError) throw new Error(`type error: ${JSON.stringify(typeRes.payload)}`);
    ok(`typed "${QUERY}" (${typeRes.payload.chars} chars)`);
    await sleep(800);

    step('6/9 take_screenshot + screen-locate 搜索按钮');
    const shot2 = await takeScreenshot(proc, 'jd-typed');
    const locate2 = runLocate(shot2.shotPath, '点击搜索按钮或放大镜图标');
    const btnCss = imageToCss(
      locate2.coordinates.image.x,
      locate2.coordinates.image.y,
      shot2.meta.device_scale_factor ?? dsf,
    );
    ok(`search button CSS coords: ${btnCss.x}, ${btnCss.y}`);

    const click2 = toolResult(
      await rpc(proc, 'tools/call', {
        name: 'physical_click',
        arguments: btnCss,
      }),
    );
    if (click2.isError) throw new Error(`search click error: ${JSON.stringify(click2.payload)}`);
    ok(`clicked search button (${click2.payload.durationMs}ms)`);

    step('7/9 Verify search results page');
    const RESULT_RE = /search\.jd\.com|keyword=|\/Search\?|wd=/i;
    let resultUrl = '';
    for (let i = 0; i < 15; i++) {
      await sleep(1000);
      const list = await cdp('/json');
      const page = list.find((t) => t.type === 'page');
      resultUrl = page?.url || '';
      if (RESULT_RE.test(resultUrl) || resultUrl.includes(encodeURIComponent(QUERY))) break;
    }
    info(`current URL: ${decodeURIComponent(resultUrl)}`);
    if (!RESULT_RE.test(resultUrl) && !resultUrl.includes(encodeURIComponent(QUERY))) {
      fail('did not reach JD search results URL');
      throw new Error('search results page not reached');
    }
    ok('JD search executed — results page reached');
    await sleep(2000);

    step('8/9 take_screenshot + screen-locate 第一个商品');
    const shot3 = await takeScreenshot(proc, 'jd-results');
    const dsf3 = shot3.meta.device_scale_factor ?? dsf;
    const locate3 = runLocate(
      shot3.shotPath,
      '点击搜索结果列表中第一个商品（商品图片或标题区域）',
    );
    const productCss = imageToCss(
      locate3.coordinates.image.x,
      locate3.coordinates.image.y,
      dsf3,
    );
    ok(`first product CSS coords: ${productCss.x}, ${productCss.y} (dsf=${dsf3})`);

    const click3 = toolResult(
      await rpc(proc, 'tools/call', {
        name: 'physical_click',
        arguments: productCss,
      }),
    );
    if (click3.isError) throw new Error(`product click error: ${JSON.stringify(click3.payload)}`);
    ok(`clicked first product (${click3.payload.durationMs}ms)`);

    step('9/9 Verify product detail page');
    const PRODUCT_RE = /item\.jd\.com|\/product\/|\/\d+\.html/i;
    let productUrl = '';
    for (let i = 0; i < 15; i++) {
      await sleep(1000);
      const list = await cdp('/json');
      const page = list.find((t) => t.type === 'page');
      productUrl = page?.url || '';
      if (PRODUCT_RE.test(productUrl)) break;
    }
    info(`current URL: ${decodeURIComponent(productUrl)}`);
    if (PRODUCT_RE.test(productUrl)) {
      ok('first product opened — detail page reached');
      passed = true;
    } else {
      fail('did not reach JD product detail URL');
    }
  } finally {
    step('Teardown');
    proc.stdin.end();
    try {
      proc.kill('SIGTERM');
    } catch {
      /* ignore */
    }
    await sleep(300);
    try {
      execFileSync('bash', ['scripts/dev-env.sh', 'stop'], { cwd: ROOT, stdio: 'ignore' });
    } catch {
      /* ignore */
    }
    logStream.end();
    ok('cleaned up');
  }

  console.log(
    passed
      ? '\n\u001b[32m=== JD SCREEN-LOCATE E2E: PASS ===\u001b[0m'
      : '\n\u001b[31m=== JD SCREEN-LOCATE E2E: FAIL ===\u001b[0m',
  );
  process.exit(passed ? 0 : 1);
}

main().catch((err) => {
  console.error('\n\u001b[31mjd-screen-locate fatal:\u001b[0m', err);
  process.exit(1);
});
