// Unit tests for the close_tab handler, added together with the
// last-tab guard: closing the final remaining page would take the whole
// Chrome window down, so the provider refuses and the handler must map
// that refusal to a structured `last_tab` error the agent can act on.
//
// All tests run WITHOUT a real browser: the TabController is faked.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { handleCloseTab } from '../../dist/mcp/server.js';

function parsePayload(res) {
  assert.equal(res.content.length, 1);
  assert.equal(res.content[0].type, 'text');
  return JSON.parse(res.content[0].text);
}

test('close_tab: no controller -> browser_not_attached error', async () => {
  const res = await handleCloseTab({ index: 0 }, {});
  assert.equal(res.isError, true);
  const payload = parsePayload(res);
  assert.equal(payload.error, 'browser_not_attached');
});

test('close_tab: invalid args -> invalid_arguments error', async () => {
  const controller = { closeTab: async () => ({ ok: true, closedUrl: 'x' }) };
  const res = await handleCloseTab({ index: -1 }, { controller });
  assert.equal(res.isError, true);
  const payload = parsePayload(res);
  assert.equal(payload.error, 'invalid_arguments');
});

test('close_tab: index out of range -> tab_not_found error', async () => {
  const controller = { closeTab: async () => null };
  const res = await handleCloseTab({ index: 99 }, { controller });
  assert.equal(res.isError, true);
  const payload = parsePayload(res);
  assert.equal(payload.error, 'tab_not_found');
});

test('close_tab: success -> {ok, closed_url}', async () => {
  const controller = {
    closeTab: async (index) => {
      assert.equal(index, 2);
      return { ok: true, closedUrl: 'https://example.com/qa' };
    },
  };
  const res = await handleCloseTab({ index: 2 }, { controller });
  assert.notEqual(res.isError, true);
  const payload = parsePayload(res);
  assert.deepEqual(payload, { ok: true, closed_url: 'https://example.com/qa' });
});

test('close_tab: provider refuses last tab -> last_tab error with url and hint', async () => {
  const controller = {
    closeTab: async () => ({ ok: false, reason: 'last_tab', url: 'https://example.com/last' }),
  };
  const res = await handleCloseTab({ index: 0 }, { controller });
  assert.equal(res.isError, true);
  const payload = parsePayload(res);
  assert.equal(payload.error, 'last_tab');
  assert.equal(payload.url, 'https://example.com/last');
  assert.match(payload.hint, /last remaining tab/i);
});
