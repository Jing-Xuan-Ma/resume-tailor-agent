#!/usr/bin/env node
// End-to-end closed-loop test, fully self-owned (no Cursor reload needed).
//
// Lifecycle this script controls by itself:
//   1. Clean slate: stop any existing Chrome/standalone-MCP.
//   2. Launch Chrome (CDP :9222) and open a single google.com tab.
//   3. Spawn the project's MCP server over stdio (loads current dist/).
//   4. Drive the search via MCP tools only:
//        get_page_accessibility_tree -> locate search box
//        physical_click(x,y) -> focus it
//        physical_type("中国最美乡村\n") -> type + Enter
//   5. Verify the page navigated to a Google results URL.
//   6. Tear everything down.
//
// MCP stderr (the structured logs) is mirrored to stdout (prefixed [mcp])
// and appended to .debug/logs/closed-loop-<ts>.log for later inspection.
//
// Run: npm run test:e2e   (or: node test/e2e/closed-loop.mjs)

import { spawn, execFileSync } from 'node:child_process';
import { createWriteStream, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const SERVER_JS = join(ROOT, 'dist', 'mcp', 'run-server.js');
const CDP = 'http://127.0.0.1:9222';
// Site/query/verify are env-configurable so the same harness can target
// any search site. Defaults reproduce the Google smoke test.
const SITE_URL = process.env.E2E_URL || 'https://www.google.com/ncr';
const QUERY = process.env.E2E_QUERY || '中国最美乡村';
// Regex (matched against the tab URL) that proves the search ran.
const RESULT_RE = new RegExp(process.env.E2E_RESULT_RE || '[?&](q|wd|query)=|/search|/s\\?');
const LOG_DIR = join(ROOT, '.debug', 'logs');

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

// --- MCP stdio client ----------------------------------------------------

let nextId = 0;
function rpc(proc, method, params) {
  const id = ++nextId;
  proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
  return waitFor(proc, (m) => m.id === id);
}
function notify(proc, method, params) {
  proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n');
}
function waitFor(proc, predicate, timeoutMs = 30000) {
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
function toolResult(resp) {
  const txt = resp?.result?.content?.[0]?.text;
  const payload = txt ? JSON.parse(txt) : null;
  return { isError: resp?.result?.isError === true, payload };
}

function pickSearchBox(nodes) {
  const inputs = nodes.filter((n) =>
    ['combobox', 'searchbox', 'textbox'].includes((n.role || '').toLowerCase()),
  );
  if (inputs.length === 0) return null;
  const named = inputs.find((n) => /search|搜索|查询/i.test(n.name || ''));
  if (named) return named;
  // Otherwise the widest input in the upper half of the page.
  return inputs
    .filter((n) => n.y < 500)
    .sort((a, b) => (b.width || 0) - (a.width || 0))[0] || inputs[0];
}

// --- Main ----------------------------------------------------------------

async function main() {
  mkdirSync(LOG_DIR, { recursive: true });
  const logPath = join(LOG_DIR, `closed-loop-${ts()}.log`);
  const logStream = createWriteStream(logPath, { flags: 'a' });
  console.log(`MCP logs -> ${logPath}`);

  step('1/6 Clean slate (stop existing Chrome + standalone MCP)');
  try {
    execFileSync('bash', ['scripts/dev-env.sh', 'stop'], { cwd: ROOT, stdio: 'ignore' });
  } catch {
    /* ignore */
  }
  await sleep(500);
  ok('stopped');

  step(`2/6 Launch Chrome and open a single tab: ${SITE_URL}`);
  execFileSync('bash', ['scripts/launch-chrome.sh'], { cwd: ROOT, stdio: 'ignore' });
  if (!(await waitForCdp())) throw new Error('Chrome CDP did not come up');
  ok('Chrome CDP reachable');
  const opened = await cdp(`/json/new?${SITE_URL}`, 'PUT');
  info(`opened tab ${opened.id} -> ${opened.url}`);
  // Prune every other tab so the provider deterministically picks ours.
  const tabs = await cdp('/json');
  for (const t of tabs) {
    if (t.type === 'page' && t.id !== opened.id) {
      await cdp(`/json/close/${t.id}`).catch(() => {});
    }
  }
  await sleep(1500);
  ok('target tab isolated');

  step('3/6 Spawn MCP server (stdio)');
  const proc = spawn(process.execPath, [SERVER_JS], {
    cwd: ROOT,
    env: {
      ...process.env,
      DB_PATH: join(ROOT, 'data', 'intercepted.db'),
      CDP_ENDPOINT: CDP,
      AUTO_LAUNCH_CHROME: '1',
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
    clientInfo: { name: 'closed-loop', version: '0.0.1' },
  });
  notify(proc, 'notifications/initialized');
  ok('MCP initialized');

  let passed = false;
  try {
    step('4/6 Read accessibility tree and locate the search box');
    const a11y = toolResult(
      await rpc(proc, 'tools/call', {
        name: 'get_page_accessibility_tree',
        arguments: { max_nodes: 200 },
      }),
    );
    if (a11y.isError) throw new Error(`a11y error: ${JSON.stringify(a11y.payload)}`);
    info(`got ${a11y.payload.count} nodes`);
    const box = pickSearchBox(a11y.payload.items);
    if (!box) {
      info('a11y dump (first 20):');
      for (const n of a11y.payload.items.slice(0, 20)) {
        info(`  role=${n.role} name=${JSON.stringify(n.name)} @${n.x},${n.y} ${n.width}x${n.height}`);
      }
      throw new Error('no search box found in a11y tree');
    }
    ok(`search box: role=${box.role} name=${JSON.stringify(box.name)} @${box.x},${box.y}`);

    step('5/6 Click the box, type the query, submit');
    const click = toolResult(
      await rpc(proc, 'tools/call', {
        name: 'physical_click',
        arguments: { x: Math.round(box.x), y: Math.round(box.y) },
      }),
    );
    if (click.isError) throw new Error(`click error: ${JSON.stringify(click.payload)}`);
    ok(`clicked @${box.x},${box.y} (${click.payload.durationMs}ms)`);

    const type = toolResult(
      await rpc(proc, 'tools/call', {
        name: 'physical_type',
        arguments: { text: `${QUERY}\n` },
      }),
    );
    if (type.isError) throw new Error(`type error: ${JSON.stringify(type.payload)}`);
    ok(`typed ${type.payload.chars} chars + Enter (${type.payload.durationMs}ms)`);

    step('6/6 Verify navigation to a results page');
    let resultUrl = '';
    for (let i = 0; i < 12; i++) {
      await sleep(800);
      const list = await cdp('/json');
      const page = list.find((t) => t.type === 'page');
      resultUrl = page?.url || '';
      if (RESULT_RE.test(resultUrl)) break;
    }
    info(`current URL: ${decodeURIComponent(resultUrl)}`);
    if (RESULT_RE.test(resultUrl)) {
      ok('search executed — results page reached');
      passed = true;
    } else {
      fail('did not reach a results URL (page may show a consent/captcha interstitial)');
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
      ? '\n\u001b[32m=== CLOSED LOOP: PASS ===\u001b[0m'
      : '\n\u001b[31m=== CLOSED LOOP: FAIL ===\u001b[0m',
  );
  process.exit(passed ? 0 : 1);
}

main().catch((err) => {
  console.error('\n\u001b[31mclosed-loop fatal:\u001b[0m', err);
  process.exit(1);
});
