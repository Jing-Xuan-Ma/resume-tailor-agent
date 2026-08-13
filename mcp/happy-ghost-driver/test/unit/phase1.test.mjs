import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { EventEmitter } from 'node:events';

import {
  openDb,
  closeDb,
  insertIntercepted,
  queryIntercepted,
} from '../../dist/db/store.js';
import { startSniffer } from '../../dist/collect/sniffer.js';

function makeTempDbPath() {
  const dir = mkdtempSync(join(tmpdir(), 'ghost-driver-phase1-'));
  return join(dir, 'test.db');
}

async function flushAsync() {
  await new Promise((r) => setImmediate(r));
  await new Promise((r) => setImmediate(r));
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

test('store: queryIntercepted matches by LIKE pattern', async (t) => {
  return withDb(t, async () => {
    await insertIntercepted({
      url: 'https://api.test.com/search?q=hello',
      status: 200,
      content_type: 'application/json',
      body: '{"q":"hello"}',
    });
    await insertIntercepted({
      url: 'https://api.test.com/search?q=world',
      status: 200,
      content_type: 'application/json',
      body: '{"q":"world"}',
    });
    await insertIntercepted({
      url: 'https://api.test.com/user/123',
      status: 200,
      content_type: 'application/json',
      body: '{"id":123}',
    });

    const searchRows = await queryIntercepted({ urlPattern: '%search%' });
    assert.equal(searchRows.length, 2, 'should match 2 search URLs');
    assert.ok(
      searchRows.every((r) => r.url.includes('search')),
      'all rows should contain "search"',
    );

    const userRows = await queryIntercepted({ urlPattern: '%user%' });
    assert.equal(userRows.length, 1, 'should match 1 user URL');
  });
});

test('store: queryIntercepted respects limit', async (t) => {
  return withDb(t, async () => {
    for (let i = 0; i < 5; i++) {
      await insertIntercepted({
        url: `https://api.test.com/search?i=${i}`,
        status: 200,
        content_type: 'application/json',
        body: '{}',
      });
    }
    const limited = await queryIntercepted({ urlPattern: '%search%', limit: 2 });
    assert.equal(limited.length, 2, 'limit should cap at 2');
  });
});

test('store: queryIntercepted respects sinceTs', async (t) => {
  return withDb(t, async () => {
    await insertIntercepted({
      url: 'https://api.test.com/search?old=1',
      status: 200,
      content_type: 'application/json',
      body: '{}',
    });
    const future = Date.now() + 60_000;
    const rows = await queryIntercepted({
      urlPattern: '%search%',
      sinceTs: future,
    });
    assert.equal(rows.length, 0, 'future sinceTs should yield zero rows');
  });
});

test('store: queryIntercepted clamps limit above MAX_LIMIT', async (t) => {
  return withDb(t, async () => {
    await insertIntercepted({
      url: 'https://api.test.com/search?clamp=1',
      status: 200,
      content_type: 'application/json',
      body: '{}',
    });
    const rows = await queryIntercepted({
      urlPattern: '%search%',
      limit: 10_000,
    });
    assert.equal(rows.length, 1, 'should still work with absurd limit');
  });
});

test('store: queryIntercepted orders by ts DESC', async (t) => {
  return withDb(t, async () => {
    await insertIntercepted({
      url: 'https://api.test.com/search?first',
      status: 200,
      content_type: 'application/json',
      body: '{}',
    });
    await insertIntercepted({
      url: 'https://api.test.com/search?second',
      status: 200,
      content_type: 'application/json',
      body: '{}',
    });
    const rows = await queryIntercepted({ urlPattern: '%search%' });
    assert.ok(rows[0].ts >= rows[1].ts, 'first row should be newer or equal');
    assert.equal(rows[0].url, 'https://api.test.com/search?second');
  });
});

test('store: LIKE wildcard _ works', async (t) => {
  return withDb(t, async () => {
    await insertIntercepted({
      url: 'https://api.test.com/aXc',
      status: 200,
      content_type: 'application/json',
      body: '{}',
    });
    await insertIntercepted({
      url: 'https://api.test.com/abc',
      status: 200,
      content_type: 'application/json',
      body: '{}',
    });
    const rows = await queryIntercepted({ urlPattern: '%/a_c' });
    assert.equal(rows.length, 2, '_ matches any single char');
  });
});

function makeMockResponse({ url, status = 200, contentType = 'application/json', bodyText, jsonValue }) {
  return {
    url() {
      return url;
    },
    status() {
      return status;
    },
    headers() {
      return { 'content-type': contentType };
    },
    async json() {
      if (jsonValue !== undefined) return jsonValue;
      throw new Error('not json');
    },
    async text() {
      if (bodyText === undefined) throw new Error('no body');
      return bodyText;
    },
  };
}

function makeMockPage() {
  return new EventEmitter();
}

test('sniffer: captures matching JSON response', async (t) => {
  return withDb(t, async () => {
    const page = makeMockPage();
    const sniffer = startSniffer(page, {
      urlInclude: ['search'],
      contentTypes: ['application/json'],
    });
    page.emit(
      'response',
      makeMockResponse({
        url: 'https://x.com/api/search?q=a',
        jsonValue: { q: 'a' },
      }),
    );
    await flushAsync();
    const stats = sniffer.getStats();
    assert.equal(stats.captured, 1, 'one captured');
    assert.equal(stats.skipped, 0);
    assert.equal(stats.errors, 0);
    const rows = await queryIntercepted({ urlPattern: '%search%' });
    assert.equal(rows.length, 1);
    assert.equal(rows[0].url, 'https://x.com/api/search?q=a');
    assert.equal(rows[0].body, JSON.stringify({ q: 'a' }));
    sniffer.stop();
  });
});

test('sniffer: skips URL not in include list', async (t) => {
  return withDb(t, async () => {
    const page = makeMockPage();
    const sniffer = startSniffer(page, {
      urlInclude: ['search'],
      contentTypes: ['application/json'],
    });
    page.emit(
      'response',
      makeMockResponse({
        url: 'https://x.com/api/other',
        jsonValue: {},
      }),
    );
    await flushAsync();
    const stats = sniffer.getStats();
    assert.equal(stats.captured, 0);
    assert.equal(stats.skipped, 1);
    sniffer.stop();
  });
});

test('sniffer: skips URL in exclude list', async (t) => {
  return withDb(t, async () => {
    const page = makeMockPage();
    const sniffer = startSniffer(page, {
      urlExclude: ['static'],
      contentTypes: ['application/json'],
    });
    page.emit(
      'response',
      makeMockResponse({
        url: 'https://x.com/static/data.json',
        jsonValue: {},
      }),
    );
    await flushAsync();
    const stats = sniffer.getStats();
    assert.equal(stats.captured, 0);
    assert.equal(stats.skipped, 1);
    sniffer.stop();
  });
});

test('sniffer: skips when content-type not in allowed set', async (t) => {
  return withDb(t, async () => {
    const page = makeMockPage();
    const sniffer = startSniffer(page, {
      contentTypes: ['application/json'],
    });
    page.emit(
      'response',
      makeMockResponse({
        url: 'https://x.com/api/data',
        contentType: 'image/png',
        bodyText: 'binarydata',
      }),
    );
    await flushAsync();
    const stats = sniffer.getStats();
    assert.equal(stats.captured, 0);
    assert.equal(stats.skipped, 1);
    sniffer.stop();
  });
});

test('sniffer: discards oversized body', async (t) => {
  return withDb(t, async () => {
    const page = makeMockPage();
    const sniffer = startSniffer(page, {
      contentTypes: ['application/json'],
      maxBodyBytes: 8,
    });
    page.emit(
      'response',
      makeMockResponse({
        url: 'https://x.com/api/big',
        contentType: 'application/json',
        bodyText: 'x'.repeat(100),
      }),
    );
    await flushAsync();
    const stats = sniffer.getStats();
    assert.equal(stats.captured, 0, 'oversize not captured');
    assert.equal(stats.skipped, 1, 'oversize counted as skipped');
    sniffer.stop();
  });
});

test('sniffer: error in body read is isolated and counted', async (t) => {
  return withDb(t, async () => {
    const page = makeMockPage();
    const sniffer = startSniffer(page, {
      contentTypes: ['application/json'],
    });
    page.emit(
      'response',
      makeMockResponse({
        url: 'https://x.com/api/broken',
        contentType: 'application/json',
      }),
    );
    page.emit(
      'response',
      makeMockResponse({
        url: 'https://x.com/api/ok',
        jsonValue: { ok: true },
      }),
    );
    await flushAsync();
    const stats = sniffer.getStats();
    assert.equal(stats.captured, 1, 'valid response still captured');
    assert.equal(stats.errors, 1, 'broken response counted as error');
    sniffer.stop();
  });
});

test('sniffer: stop() removes the listener', () => {
  const page = makeMockPage();
  const noopStore = { insert: async () => {}, query: async () => [], close: async () => {} };
  const sniffer = startSniffer(page, { contentTypes: ['application/json'], store: noopStore });
  sniffer.stop();
  assert.equal(page.listenerCount('response'), 0, 'listener removed');
});

test('sniffer: handler survives thrown sync error (isolation)', async (t) => {
  return withDb(t, async () => {
    const page = makeMockPage();
    const sniffer = startSniffer(page, { contentTypes: ['application/json'] });
    page.emit('response', {
      url() {
        throw new Error('boom on url()');
      },
      status() {
        return 200;
      },
      headers() {
        return {};
      },
    });
    page.emit(
      'response',
      makeMockResponse({
        url: 'https://x.com/api/ok2',
        jsonValue: {},
      }),
    );
    await flushAsync();
    const stats = sniffer.getStats();
    assert.equal(stats.captured, 1, 'second response captured');
    assert.equal(stats.errors, 1, 'first one errored');
    sniffer.stop();
  });
});
