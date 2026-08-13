import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
  openDb,
  closeDb,
  insertIntercepted,
  getInterceptStore,
} from '../../dist/db/store.js';
import {
  handleQueryIntercepted,
  transformRow,
  QueryInterceptedArgsSchema,
} from '../../dist/mcp/server.js';

function makeTempDbPath() {
  const dir = mkdtempSync(join(tmpdir(), 'ghost-driver-phase2-'));
  return join(dir, 'test.db');
}

function withDb(t, fn) {
  const path = makeTempDbPath();
  openDb(path);
  t.after(async () => {
    await closeDb();
    rmSync(join(path, '..'), { recursive: true, force: true });
  });
  return fn();
}

function queryCtx(extra = {}) {
  return {
    statsProvider: () => zeroStats,
    store: getInterceptStore(),
    ...extra,
  };
}

function decodeToolText(result) {
  assert.ok(result && Array.isArray(result.content), 'content array present');
  assert.equal(result.content.length, 1, 'exactly one text block');
  const block = result.content[0];
  assert.equal(block.type, 'text', 'block type is text');
  return JSON.parse(block.text);
}

const zeroStats = { captured: 0, skipped: 0, errors: 0 };
const noopStore = {
  insert: async () => {},
  query: async () => [],
  close: async () => {},
};

test('schema: rejects missing url_pattern', () => {
  const r = QueryInterceptedArgsSchema.safeParse({ limit: 5 });
  assert.equal(r.success, false);
});

test('schema: rejects empty url_pattern', () => {
  const r = QueryInterceptedArgsSchema.safeParse({ url_pattern: '' });
  assert.equal(r.success, false);
});

test('schema: rejects negative since_ts', () => {
  const r = QueryInterceptedArgsSchema.safeParse({
    url_pattern: '%',
    since_ts: -1,
  });
  assert.equal(r.success, false);
});

test('schema: rejects limit above 500', () => {
  const r = QueryInterceptedArgsSchema.safeParse({
    url_pattern: '%',
    limit: 501,
  });
  assert.equal(r.success, false);
});

test('schema: rejects unknown property', () => {
  const r = QueryInterceptedArgsSchema.safeParse({
    url_pattern: '%',
    bogus: 1,
  });
  assert.equal(r.success, false);
});

test('schema: accepts url_pattern only', () => {
  const r = QueryInterceptedArgsSchema.safeParse({ url_pattern: '%/search%' });
  assert.equal(r.success, true);
});

test('handler: returns matching rows for a LIKE pattern', async (t) => {
  return withDb(t, async () => {
    await insertIntercepted({
      url: 'https://api.test.com/search?q=a',
      status: 200,
      content_type: 'application/json',
      body: '{"q":"a"}',
    });
    await insertIntercepted({
      url: 'https://api.test.com/search?q=b',
      status: 200,
      content_type: 'application/json',
      body: '{"q":"b"}',
    });
    await insertIntercepted({
      url: 'https://api.test.com/users/1',
      status: 200,
      content_type: 'application/json',
      body: '{"id":1}',
    });

    const result = await handleQueryIntercepted({ url_pattern: '%search%' }, queryCtx());
    const payload = decodeToolText(result);
    assert.equal(payload.count, 2);
    assert.equal(payload.items.length, 2);
    assert.ok(payload.items.every((i) => i.url.includes('search')));
    assert.deepEqual(payload.stats, zeroStats);
  });
});

test('handler: respects limit argument', async (t) => {
  return withDb(t, async () => {
    for (let i = 0; i < 5; i++) {
      await insertIntercepted({
        url: `https://api.test.com/search?i=${i}`,
        status: 200,
        content_type: 'application/json',
        body: '{}',
      });
    }
    const result = await handleQueryIntercepted(
      { url_pattern: '%search%', limit: 2 },
      queryCtx(),
    );
    const payload = decodeToolText(result);
    assert.equal(payload.count, 2);
    assert.equal(payload.items.length, 2);
  });
});

test('handler: parses JSON-string body back into an object', async (t) => {
  return withDb(t, async () => {
    await insertIntercepted({
      url: 'https://api.test.com/x',
      status: 200,
      content_type: 'application/json',
      body: JSON.stringify({ hello: 'world', n: 42 }),
    });
    const result = await handleQueryIntercepted({ url_pattern: '%/x' }, queryCtx());
    const payload = decodeToolText(result);
    assert.equal(payload.count, 1);
    const item = payload.items[0];
    assert.equal(item.truncated, false);
    assert.deepEqual(item.body, { hello: 'world', n: 42 });
  });
});

test('handler: parses JSON-array body back into an array', async (t) => {
  return withDb(t, async () => {
    await insertIntercepted({
      url: 'https://api.test.com/list',
      status: 200,
      content_type: 'application/json',
      body: '[1,2,3]',
    });
    const result = await handleQueryIntercepted({ url_pattern: '%/list' }, queryCtx());
    const payload = decodeToolText(result);
    assert.deepEqual(payload.items[0].body, [1, 2, 3]);
  });
});

test('handler: returns body as string when not valid JSON', async (t) => {
  return withDb(t, async () => {
    await insertIntercepted({
      url: 'https://api.test.com/text',
      status: 200,
      content_type: 'text/plain',
      body: 'plain text body',
    });
    const result = await handleQueryIntercepted({ url_pattern: '%/text' }, queryCtx());
    const payload = decodeToolText(result);
    assert.equal(payload.items[0].body, 'plain text body');
    assert.equal(payload.items[0].truncated, false);
  });
});

test('handler: returns body as string when JSON-looking but malformed', async (t) => {
  return withDb(t, async () => {
    await insertIntercepted({
      url: 'https://api.test.com/broken',
      status: 200,
      content_type: 'application/json',
      body: '{"a": , "b": 2}',
    });
    const result = await handleQueryIntercepted({ url_pattern: '%/broken' }, queryCtx());
    const payload = decodeToolText(result);
    assert.equal(typeof payload.items[0].body, 'string');
    assert.equal(payload.items[0].body, '{"a": , "b": 2}');
  });
});

test('handler: truncates body exceeding 8KB and marks truncated=true', async (t) => {
  return withDb(t, async () => {
    const filler = 'x'.repeat(20_000);
    await insertIntercepted({
      url: 'https://api.test.com/huge',
      status: 200,
      content_type: 'text/plain',
      body: filler,
    });
    const result = await handleQueryIntercepted({ url_pattern: '%/huge' }, queryCtx());
    const payload = decodeToolText(result);
    const item = payload.items[0];
    assert.equal(item.truncated, true);
    assert.equal(typeof item.body, 'string');
    const bytes = Buffer.byteLength(String(item.body), 'utf8');
    assert.ok(bytes <= 8 * 1024, `truncated body must be <= 8KB, got ${bytes}`);
    assert.ok(String(item.body).endsWith('...[truncated]'), 'truncation suffix appended');
  });
});

test('handler: does NOT truncate a body exactly at 8KB', async (t) => {
  return withDb(t, async () => {
    const exact = 'a'.repeat(8192);
    await insertIntercepted({
      url: 'https://api.test.com/exact8k',
      status: 200,
      content_type: 'text/plain',
      body: exact,
    });
    const result = await handleQueryIntercepted({ url_pattern: '%/exact8k' }, queryCtx());
    const payload = decodeToolText(result);
    assert.equal(payload.items[0].truncated, false);
    assert.equal(payload.items[0].body, exact);
  });
});

test('handler: truncation preserves multi-byte UTF-8 boundaries', async (t) => {
  return withDb(t, async () => {
    const big = '😀'.repeat(5000);
    await insertIntercepted({
      url: 'https://api.test.com/emoji',
      status: 200,
      content_type: 'text/plain',
      body: big,
    });
    const result = await handleQueryIntercepted({ url_pattern: '%/emoji' }, queryCtx());
    const payload = decodeToolText(result);
    const item = payload.items[0];
    assert.equal(item.truncated, true);
    const body = String(item.body);
    const buf = Buffer.from(body, 'utf8');
    const decoded = buf.toString('utf8');
    assert.equal(body, decoded, 'no replacement chars / no corruption');
  });
});

test('handler: surfaces live sniffer stats from injected provider', async (t) => {
  return withDb(t, async () => {
    await insertIntercepted({
      url: 'https://api.test.com/x',
      status: 200,
      content_type: 'application/json',
      body: '{}',
    });
    const live = { captured: 42, skipped: 7, errors: 3 };
    const result = await handleQueryIntercepted(
      { url_pattern: '%' },
      queryCtx({ statsProvider: () => live }),
    );
    const payload = decodeToolText(result);
    assert.deepEqual(payload.stats, live);
  });
});

test('handler: statsProvider that throws falls back to zeros', async (t) => {
  return withDb(t, async () => {
    await insertIntercepted({
      url: 'https://api.test.com/x',
      status: 200,
      content_type: 'application/json',
      body: '{}',
    });
    const result = await handleQueryIntercepted(
      { url_pattern: '%' },
      queryCtx({ statsProvider: () => { throw new Error('boom'); } }),
    );
    const payload = decodeToolText(result);
    assert.deepEqual(payload.stats, zeroStats);
  });
});

test('handler: returns isError=true for invalid args', async () => {
  const result = await handleQueryIntercepted(
    { limit: 5 },
    { statsProvider: () => zeroStats, store: noopStore },
  );
  assert.equal(result.isError, true);
  assert.ok(Array.isArray(result.content));
});

test('transformRow: handles null body', () => {
  const out = transformRow({
    id: 1,
    url: 'https://x',
    status: 200,
    content_type: null,
    body: null,
    ts: 1,
  });
  assert.equal(out.body, null);
  assert.equal(out.truncated, false);
});

test('transformRow: empty body returns empty string', () => {
  const out = transformRow({
    id: 1,
    url: 'https://x',
    status: 200,
    content_type: null,
    body: '',
    ts: 1,
  });
  assert.equal(out.body, '');
  assert.equal(out.truncated, false);
});
