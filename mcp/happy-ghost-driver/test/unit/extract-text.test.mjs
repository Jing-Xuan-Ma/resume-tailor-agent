// Unit tests for full-text extraction helpers and MCP handlers.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  mergeScrollCaptures,
  pickLastMessageGroup,
  dedupeRepeatedContent,
  stripTrailingFollowUps,
  stripUiNoiseLines,
  refineAssistantReplyText,
  stripAfterUserMessage,
  handleExtractTextAt,
  handleExtractAssistantReply,
  handleReadClipboard,
  handlePhysicalKeypress,
  ExtractTextAtArgsSchema,
  ExtractAssistantReplyArgsSchema,
  PhysicalKeypressArgsSchema,
} from '../../dist/mcp/server.js';

process.env.COOLDOWN_MIN_MS = '1';
process.env.COOLDOWN_MAX_MS = '2';

function decodePayload(result) {
  assert.ok(result && Array.isArray(result.content));
  return JSON.parse(result.content[0].text);
}

function makeMockPage(evalResult) {
  return {
    evaluate: async () => evalResult,
  };
}

function makeMockActions(overrides = {}) {
  const calls = { pressKeys: [] };
  return {
    calls,
    actions: {
      async click() {},
      async type() {
        return 0;
      },
      async pressKeys(keys) {
        calls.pressKeys.push(keys);
        overrides.onPressKeys?.(keys);
      },
      async scroll() {},
      async getA11y() {
        return [];
      },
    },
  };
}

// --- Pure helpers --------------------------------------------------------

test('mergeScrollCaptures: merges overlapping scroll slices', () => {
  const a = 'Hello world this is a long assistant reply.';
  const b = 'long assistant reply. And here is more text at the end.';
  const merged = mergeScrollCaptures([a, b]);
  assert.equal(
    merged,
    'Hello world this is a long assistant reply. And here is more text at the end.',
  );
});

test('mergeScrollCaptures: empty input returns empty string', () => {
  assert.equal(mergeScrollCaptures([]), '');
  assert.equal(mergeScrollCaptures(['', '  ']), '');
});

test('pickLastMessageGroup: takes last triple-newline group', () => {
  const full = 'sidebar noise\n\nuser question here\n\n\nassistant part one\n\nassistant part two';
  const reply = pickLastMessageGroup(full);
  assert.equal(reply, 'assistant part one\n\nassistant part two');
});

test('pickLastMessageGroup: strips user_message when provided', () => {
  const full = 'noise\n\nwhat is GEO?\n\nGEO is generative engine optimization.';
  const reply = pickLastMessageGroup(full, 'what is GEO?');
  assert.equal(reply, 'GEO is generative engine optimization.');
});

test('dedupeRepeatedContent: collapses duplicated body', () => {
  const unit = 'A'.repeat(400);
  const dup = unit + unit;
  assert.equal(dedupeRepeatedContent(dup), unit);
});

test('stripUiNoiseLines: removes chrome lines', () => {
  const raw = '正文第一段\n深度思考\n智能搜索\n正文第二段';
  assert.equal(stripUiNoiseLines(raw), '正文第一段\n正文第二段');
});

test('stripTrailingFollowUps: removes trailing question chips', () => {
  const raw =
    '推荐书单如下\n\n《测试》\n\n推荐一些古言探案小说的精彩片段\n古言探案小说的受众群体一般有哪些特点？';
  const out = stripTrailingFollowUps(raw);
  assert.match(out, /推荐书单/);
  assert.doesNotMatch(out, /受众群体/);
});

test('stripAfterUserMessage: badge wins over sidebar title collision', () => {
  const raw =
    '置顶\n女扮男装权谋古言推荐\n两书对比推荐\n已阅读 12 个网页\n\n想找类似《庆余年》那种女扮男装……';
  const out = stripAfterUserMessage(raw, '女扮男装权谋古言推荐');
  assert.match(out, /想找类似《庆余年》/);
  assert.doesNotMatch(out, /^置顶/);
});

test('refineAssistantReplyText: end-to-end cleanup', () => {
  const unit = '《书》介绍'.padEnd(220, '字');
  const noisy = `快速模式\n\n用户问题\n\n\n${unit}\n深度思考\n${unit}\n推荐一些其他问题？`;
  const out = refineAssistantReplyText(noisy, '用户问题');
  assert.match(out, /《书》/);
  assert.doesNotMatch(out, /深度思考/);
  assert.doesNotMatch(out, /推荐一些其他问题/);
});

// --- Schemas -------------------------------------------------------------

test('schema: extract_text_at requires x and y', () => {
  assert.equal(ExtractTextAtArgsSchema.safeParse({ x: 1 }).success, false);
  assert.equal(ExtractTextAtArgsSchema.safeParse({ x: 1, y: 2 }).success, true);
});

test('schema: physical_keypress requires keys', () => {
  assert.equal(PhysicalKeypressArgsSchema.safeParse({}).success, false);
  assert.equal(PhysicalKeypressArgsSchema.safeParse({ keys: 'Meta+c' }).success, true);
});

test('schema: extract_assistant_reply accepts user_message', () => {
  const r = ExtractAssistantReplyArgsSchema.safeParse({ user_message: 'hello' });
  assert.equal(r.success, true);
});

// --- Handlers: not attached --------------------------------------------

test('extract_text_at: browser_not_attached without page', async () => {
  const r = await handleExtractTextAt({ x: 1, y: 2 }, {});
  assert.equal(r.isError, true);
  assert.equal(decodePayload(r).error, 'browser_not_attached');
});

test('extract_assistant_reply: browser_not_attached without page', async () => {
  const r = await handleExtractAssistantReply({}, {});
  assert.equal(r.isError, true);
  assert.equal(decodePayload(r).error, 'browser_not_attached');
});

test('read_clipboard: browser_not_attached without page', async () => {
  const r = await handleReadClipboard({}, {});
  assert.equal(r.isError, true);
  assert.equal(decodePayload(r).error, 'browser_not_attached');
});

test('physical_keypress: browser_not_attached without actions/page', async () => {
  const r = await handlePhysicalKeypress({ keys: 'Meta+c' }, {});
  assert.equal(r.isError, true);
  assert.equal(decodePayload(r).error, 'browser_not_attached');
});

// --- Handlers: happy path with mock page ---------------------------------

test('extract_text_at: returns full text at coordinates', async () => {
  const page = makeMockPage({
    ok: true,
    text: 'x'.repeat(500),
    char_count: 500,
    depth: 2,
    truncated: false,
  });
  const r = await handleExtractTextAt({ x: 100, y: 200 }, { page });
  const payload = decodePayload(r);
  assert.equal(payload.ok, true);
  assert.equal(payload.char_count, 500);
  assert.equal(payload.depth, 2);
});

test('extract_assistant_reply: scroll_collect with user_message trim', async () => {
  const page = makeMockPage({
    ok: true,
    raw_text: 'UI chrome\n\n用户问题\n\n\n这是完整回答正文，超过两百字也不会被 a11y 截断。',
    scroll_steps: 3,
    container_tag: 'DIV',
  });
  const r = await handleExtractAssistantReply(
    { user_message: '用户问题' },
    { page },
  );
  const payload = decodePayload(r);
  assert.equal(payload.ok, true);
  assert.equal(payload.method, 'scroll_collect');
  assert.match(payload.text, /完整回答正文/);
  assert.equal(payload.scroll_steps, 3);
});

test('physical_keypress: invokes injected pressKeys', async () => {
  const { calls, actions } = makeMockActions();
  const r = await handlePhysicalKeypress({ keys: 'Meta+c' }, { actions });
  assert.equal(r.isError, undefined);
  assert.deepEqual(calls.pressKeys, ['Meta+c']);
  assert.equal(decodePayload(r).ok, true);
});
