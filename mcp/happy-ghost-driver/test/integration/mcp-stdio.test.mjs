#!/usr/bin/env node
// Integration test: spawns the real MCP server over stdio and exercises
// initialize -> tools/list -> tools/call against a pre-populated SQLite db.
//
// Run via: npm run test:integration
//
// Not part of `npm test` because it relies on spawning a child process and
// piping JSON-RPC, which is flaky on shared CI runners.

import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

import Database from 'better-sqlite3';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '../..');
const SERVER_JS = join(ROOT, 'dist', 'mcp', 'run-server.js');

const NEXT_ID = (() => {
  let n = 0;
  return () => ++n;
})();

function writeLine(proc, obj) {
  proc.stdin.write(JSON.stringify(obj) + '\n');
}

function readJsonLines(proc, predicate, timeoutMs = 10_000) {
  return new Promise((resolvePromise, rejectPromise) => {
    let buffer = '';
    const timer = setTimeout(() => {
      rejectPromise(new Error(`timeout waiting for response (${predicate.toString()})`));
    }, timeoutMs);

    const onData = (chunk) => {
      buffer += chunk.toString('utf8');
      let nl;
      while ((nl = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (!line) continue;
        let msg;
        try {
          msg = JSON.parse(line);
        } catch {
          continue; // server logs go to stderr; skip non-JSON
        }
        if (predicate(msg)) {
          clearTimeout(timer);
          proc.stdout.off('data', onData);
          resolvePromise(msg);
          return;
        }
      }
    };
    proc.stdout.on('data', onData);
  });
}

async function run() {
  const dir = mkdtempSync(join(tmpdir(), 'ghost-driver-mcp-int-'));
  const dbPath = join(dir, 'test.db');
  mkdirSync(dirname(dbPath), { recursive: true });

  // Pre-populate the database with deterministic data.
  const seed = new Database(dbPath);
  seed.exec(`
    CREATE TABLE IF NOT EXISTS intercepted (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      url TEXT NOT NULL,
      status INTEGER,
      content_type TEXT,
      body TEXT,
      ts INTEGER NOT NULL
    );
  `);
  const insert = seed.prepare(
    `INSERT INTO intercepted (url, status, content_type, body, ts) VALUES (?, ?, ?, ?, ?)`,
  );
  insert.run(
    'https://api.example.com/v1/search?q=hello',
    200,
    'application/json',
    JSON.stringify({ q: 'hello', results: [1, 2, 3] }),
    Date.now(),
  );
  insert.run(
    'https://api.example.com/v1/users/42',
    200,
    'application/json',
    JSON.stringify({ id: 42, name: 'ada' }),
    Date.now(),
  );
  insert.run(
    'https://api.example.com/v1/text',
    200,
    'text/plain',
    'plain body',
    Date.now(),
  );
  seed.close();

  const proc = spawn(process.execPath, [SERVER_JS], {
    env: {
      ...process.env,
      // Pin sqlite: the app config may default STORE_BACKEND to mysql,
      // which would bypass the seeded temp db and hit a real database.
      STORE_BACKEND: 'sqlite',
      DB_PATH: dbPath,
      // Force the no-browser path deterministically: point at a closed
      // port and disable auto-launch so the lazy provider fails fast and
      // physical tools return browser_not_attached (the assertions below).
      CDP_ENDPOINT: 'http://127.0.0.1:1',
      AUTO_LAUNCH_CHROME: '0',
    },
    stdio: ['pipe', 'pipe', 'inherit'],
  });

  let failed = false;
  try {
    // 1) initialize
    const initId = NEXT_ID();
    writeLine(proc, {
      jsonrpc: '2.0',
      id: initId,
      method: 'initialize',
      params: {
        protocolVersion: '2025-06-18',
        capabilities: {},
        clientInfo: { name: 'integration-test', version: '0.0.1' },
      },
    });
    const initResp = await readJsonLines(proc, (m) => m.id === initId);
    assert.ok(initResp.result, 'initialize returned a result');
    assert.ok(
      initResp.result.capabilities &&
        Object.prototype.hasOwnProperty.call(initResp.result.capabilities, 'tools'),
      'server advertises tools capability',
    );

    // Send initialized notification (no id).
    writeLine(proc, { jsonrpc: '2.0', method: 'notifications/initialized' });

    // 2) tools/list
    const listId = NEXT_ID();
    writeLine(proc, {
      jsonrpc: '2.0',
      id: listId,
      method: 'tools/list',
    });
    const listResp = await readJsonLines(proc, (m) => m.id === listId);
    const toolNames = listResp.result.tools.map((t) => t.name);
    assert.ok(
      toolNames.includes('query_intercepted_network_data'),
      `tools/list must include query_intercepted_network_data, got: ${JSON.stringify(toolNames)}`,
    );

    // Server exposes 14 tools: query + 4 physical + 1 keypress + 1 screenshot +
    // 3 text extraction/clipboard + 4 tab/navigation. We assert on the full set
    // here so a regression that drops (or resurrects) a tool is caught before the
    // agent ever calls it. Note: screenshot_and_locate was removed on purpose —
    // visual locating is delegated to the in-repo screen-locate skill.
    const expectedTools = [
      'query_intercepted_network_data',
      'get_page_accessibility_tree',
      'physical_click',
      'physical_type',
      'physical_scroll',
      'take_screenshot',
      'extract_text_at',
      'extract_assistant_reply',
      'read_clipboard',
      'physical_keypress',
      'browser_navigate',
      'list_tabs',
      'select_tab',
      'close_tab',
    ];
    assert.equal(
      toolNames.length,
      expectedTools.length,
      `expected ${expectedTools.length} tools, got ${toolNames.length}: ${JSON.stringify(toolNames)}`,
    );
    for (const name of expectedTools) {
      assert.ok(
        toolNames.includes(name),
        `tools/list must include ${name}, got: ${JSON.stringify(toolNames)}`,
      );
    }

    // Phase 3: physical tools must NOT accept selector-style params.
    // We statically assert that the click tool's input schema has only
    // x/y properties (no `selector` / `css` / `xpath`).
    const clickTool = listResp.result.tools.find((t) => t.name === 'physical_click');
    assert.ok(clickTool, 'physical_click tool is listed');
    const clickProps = Object.keys(clickTool.inputSchema.properties || {});
    assert.deepEqual(
      clickProps.slice().sort(),
      ['x', 'y'],
      `physical_click schema must only have x/y properties, got: ${JSON.stringify(clickProps)}`,
    );
    assert.equal(clickTool.inputSchema.additionalProperties, false);

    // Phase 3: physical tools with no browser attached must return a
    // structured browser_not_attached error rather than crashing.
    const clickCallId = NEXT_ID();
    writeLine(proc, {
      jsonrpc: '2.0',
      id: clickCallId,
      method: 'tools/call',
      params: {
        name: 'physical_click',
        arguments: { x: 10, y: 20 },
      },
    });
    const clickCallResp = await readJsonLines(proc, (m) => m.id === clickCallId);
    assert.ok(clickCallResp.result?.isError, 'physical_click must error when no browser');
    const clickErr = JSON.parse(clickCallResp.result.content[0].text);
    assert.equal(
      clickErr.error,
      'browser_not_attached',
      `expected browser_not_attached, got: ${JSON.stringify(clickErr)}`,
    );

    // take_screenshot must also error gracefully when no browser is
    // attached.
    const shotCallId = NEXT_ID();
    writeLine(proc, {
      jsonrpc: '2.0',
      id: shotCallId,
      method: 'tools/call',
      params: {
        name: 'take_screenshot',
        arguments: {},
      },
    });
    const shotCallResp = await readJsonLines(proc, (m) => m.id === shotCallId);
    assert.ok(shotCallResp.result?.isError, 'take_screenshot must error when no browser');
    const shotErr = JSON.parse(shotCallResp.result.content[0].text);
    assert.equal(
      shotErr.error,
      'browser_not_attached',
      `expected browser_not_attached, got: ${JSON.stringify(shotErr)}`,
    );

    // 3) tools/call -> matching rows
    const callId = NEXT_ID();
    writeLine(proc, {
      jsonrpc: '2.0',
      id: callId,
      method: 'tools/call',
      params: {
        name: 'query_intercepted_network_data',
        arguments: { url_pattern: '%/v1/search%' },
      },
    });
    const callResp = await readJsonLines(proc, (m) => m.id === callId);
    assert.ok(!callResp.result?.isError, 'tool call should not error');
    const text = callResp.result.content[0].text;
    const payload = JSON.parse(text);
    assert.equal(payload.count, 1, 'one matching row');
    assert.equal(payload.items[0].url, 'https://api.example.com/v1/search?q=hello');
    assert.deepEqual(payload.items[0].body, { q: 'hello', results: [1, 2, 3] });

    // 4) tools/call -> text body returned as string
    const callTextId = NEXT_ID();
    writeLine(proc, {
      jsonrpc: '2.0',
      id: callTextId,
      method: 'tools/call',
      params: {
        name: 'query_intercepted_network_data',
        arguments: { url_pattern: '%/v1/text%' },
      },
    });
    const callTextResp = await readJsonLines(proc, (m) => m.id === callTextId);
    const textPayload = JSON.parse(callTextResp.result.content[0].text);
    assert.equal(textPayload.items[0].body, 'plain body');
    assert.equal(textPayload.items[0].truncated, false);

    console.log('\n[integration] all assertions passed.\n');
  } catch (err) {
    failed = true;
    console.error('\n[integration] FAILED:', err);
  } finally {
    proc.stdin.end();
    try {
      proc.kill('SIGTERM');
    } catch {
      // ignore
    }
    rmSync(dir, { recursive: true, force: true });
  }

  if (failed) {
    process.exit(1);
  }
}

run().catch((err) => {
  console.error('[integration] unexpected', err);
  process.exit(1);
});
