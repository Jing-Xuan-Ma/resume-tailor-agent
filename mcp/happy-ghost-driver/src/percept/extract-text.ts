/**
 * Read-only full-text extraction for chat UIs (geo-qa-runner and similar).
 *
 * Unlike get_page_accessibility_tree, these helpers return complete
 * innerText without the 200-char per-node cap. They run via page.evaluate
 * and do not dispatch input events — same cognition-layer boundary as a11y.
 */

import type { Page } from 'playwright-core';

import { logger } from '../util/logger.js';

export const DEFAULT_EXTRACT_MAX_CHARS = 100_000;
export const EXTRACT_TEXT_AT_MAX_CHARS = 50_000;

/** Lines that are clearly page chrome, not answer body. */
const NOISE_LINE_PATTERNS: RegExp[] = [
  /^快速模式$/,
  /^深度思考$/,
  /^智能搜索$/,
  /^内容由 AI 生成/,
  /^已阅读 \d+ 个网页$/,
  /^\d+ 个网页$/,
  /^搜索 \d+ 个关键词/,
  /^给 DeepSeek 发送消息$/,
  /^发消息/,
  /^AI 生成可能有误/,
  /^下载电脑版$/,
  /^开启新对话$/,
  /^⌘$/,
  /^K$/,
];

/** Merge scroll captures by longest suffix/prefix overlap. Exported for tests. */
export function mergeScrollCaptures(captures: string[]): string {
  const nonEmpty = captures.map((c) => c.trim()).filter(Boolean);
  if (nonEmpty.length === 0) return '';
  let merged = nonEmpty[0]!;
  for (let i = 1; i < nonEmpty.length; i++) {
    const next = nonEmpty[i]!;
    let overlap = 0;
    const maxO = Math.min(merged.length, next.length, 800);
    for (let o = maxO; o > 15; o--) {
      if (merged.slice(-o) === next.slice(0, o)) {
        overlap = o;
        break;
      }
    }
    merged = merged + next.slice(overlap);
  }
  return merged;
}

/** Remove paragraph-level duplicates (scroll-merge artifacts). Exported for tests. */
export function dedupeRepeatedContent(text: string): string {
  const t = text.trim();
  if (t.length < 300) return t;

  // Whole-body repeat: same block concatenated 2+ times (Doubao scroll-merge bug).
  const maxUnit = Math.floor(t.length / 2);
  for (let unitLen = Math.min(800, maxUnit); unitLen >= 180; unitLen -= 20) {
    const unit = t.slice(0, unitLen);
    const head = unit.slice(0, Math.min(120, unit.length));
    let pos = 0;
    let repeats = 0;
    while (pos + head.length <= t.length) {
      if (t.slice(pos, pos + head.length) !== head) break;
      repeats += 1;
      pos += unitLen;
    }
    if (repeats >= 2 && pos >= t.length * 0.75) {
      return unit.trim();
    }
  }

  const parts = t.split(/\n\n+/);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const p of parts) {
    const key = p.replace(/\s+/g, ' ').trim().slice(0, 160);
    if (key.length >= 24 && seen.has(key)) continue;
    if (key.length >= 24) seen.add(key);
    out.push(p);
  }
  let result = out.join('\n\n').trim();

  // 半重复：同一开头长段在文中出现两次（direct_dom 偶发）。
  if (result.length >= 400) {
    const head = result.slice(0, Math.min(100, result.length));
    const second = result.indexOf(head, head.length);
    if (second > 0 && second < result.length * 0.6) {
      result = result.slice(0, second).trim();
    }
  }
  return result;
}

/** Drop trailing platform "suggested question" lines. Exported for tests. */
export function stripTrailingFollowUps(text: string): string {
  const lines = text.trim().split('\n');
  let end = lines.length;
  while (end > 1) {
    const line = lines[end - 1]!.trim();
    if (!line) {
      end -= 1;
      continue;
    }
    const looksLikeChip =
      line.length <= 80 &&
      (line.endsWith('？') || line.endsWith('?') || line.endsWith('吗')) &&
      !line.includes('《') &&
      !line.startsWith('需要我');
    if (looksLikeChip) {
      end -= 1;
      continue;
    }
    break;
  }
  return lines.slice(0, end).join('\n').trim();
}

/** Remove known UI chrome lines. Exported for tests. */
export function stripUiNoiseLines(text: string): string {
  return text
    .split('\n')
    .filter((line) => {
      const t = line.trim();
      if (!t) return true;
      return !NOISE_LINE_PATTERNS.some((re) => re.test(t));
    })
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/**
 * Post-process raw container text into assistant reply body.
 * Exported for tests.
 */
export function refineAssistantReplyText(fullText: string, userMessage?: string): string {
  let text = pickLastMessageGroup(fullText, userMessage);
  text = stripUiNoiseLines(text);
  text = dedupeRepeatedContent(text);
  text = stripTrailingFollowUps(text);
  return text.trim();
}

/**
 * Split conversation text into message groups by large vertical gaps
 * (proxy: triple newline or more). Take the last group as assistant reply.
 * Exported for tests.
 */
export function pickLastMessageGroup(fullText: string, userMessage?: string): string {
  let text = fullText.trim();
  if (!text) return '';

  if (userMessage && userMessage.trim()) {
    text = stripAfterUserMessage(text, userMessage.trim());
  }

  // Drop content before the latest user bubble when thread includes sidebar titles.
  const groups = text.split(/\n{3,}/).map((g) => g.trim()).filter(Boolean);
  if (groups.length === 0) return text;

  // Prefer the last group that looks like an assistant answer (not a one-line title).
  for (let i = groups.length - 1; i >= 0; i--) {
    const g = groups[i]!;
    if (g.length >= 80 || g.includes('《') || g.includes('\n')) {
      return g;
    }
  }
  return groups[groups.length - 1]!;
}

/** Try exact then partial user-message strip. Exported for tests. */
export function stripAfterUserMessage(text: string, userMessage: string): string {
  // 长匹配（>= 80 字）直接采纳；短匹配可能是真实的简短回答，也可能是
  // sidebar 标题后的残渣，先按优先级记为回退候选，扫完再用。
  let fallback: string | null = null;
  const consider = (after: string): string | null => {
    if (after.length >= 80) return after;
    if (after.length >= 8 && fallback === null) fallback = after;
    return null;
  };

  // 联网搜索 badge 是最可靠的 assistant 正文起点（优先于 userMessage，
  // 避免 sidebar 历史标题与 tab 标题相同导致 lastIndexOf 误匹配）。
  const badge = text.match(/(?:已阅读 \d+ 个网页|搜索 \d+ 个关键词[^\n]*)/);
  if (badge && badge.index !== undefined) {
    const hit = consider(text.slice(badge.index + badge[0].length).trim());
    if (hit) return hit;
  }

  const needles = [userMessage.trim()];
  const firstLine = userMessage.split('\n')[0]!.trim();
  if (firstLine.length >= 4 && firstLine !== needles[0]) {
    needles.push(firstLine);
  }

  for (const needle of needles) {
    if (!needle) continue;
    // 从后往前找，跳过 sidebar 里「标题后几乎没内容」的误匹配。
    let searchFrom = text.length;
    while (searchFrom >= 0) {
      const idx = text.lastIndexOf(needle, searchFrom);
      if (idx < 0) break;
      const hit = consider(text.slice(idx + needle.length).trim());
      if (hit) return hit;
      searchFrom = idx - 1; // 必须前移，否则 lastIndexOf 会重复命中同一位置死循环
    }
  }

  return fallback ?? text;
}

const EXTRACT_TEXT_AT_SCRIPT = `
(x, y, maxChars) => {
  const el = document.elementFromPoint(x, y);
  if (!el) return { ok: false, reason: 'no_element_at_point' };
  let node = el;
  let best = { text: '', depth: -1 };
  for (let i = 0; i < 10 && node; i++) {
    const t = (node.innerText || node.textContent || '').trim();
    if (t.length > best.text.length) {
      best = { text: t, depth: i };
    }
    if (t.length >= 200) break;
    node = node.parentElement;
  }
  if (!best.text) return { ok: false, reason: 'empty_text' };
  let text = best.text;
  let truncated = false;
  if (text.length > maxChars) {
    text = text.slice(0, maxChars) + '...[truncated]';
    truncated = true;
  }
  return { ok: true, text, char_count: text.length, depth: best.depth, truncated };
}
`;

const EXTRACT_ASSISTANT_REPLY_SCRIPT = `
() => {
  const MIN_INPUT_TOP_RATIO = 0.25;

  function findInputAnchor() {
    const candidates = [];
    for (const el of document.querySelectorAll(
      'textarea, input:not([type=hidden]):not([type=checkbox]):not([type=radio]), [contenteditable="true"], [role="textbox"]'
    )) {
      const rect = el.getBoundingClientRect();
      if (rect.width < 80 || rect.height < 20) continue;
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') continue;
      if (rect.top < window.innerHeight * MIN_INPUT_TOP_RATIO) continue;
      candidates.push({ el, top: rect.top, left: rect.left, area: rect.width * rect.height });
    }
    candidates.sort((a, b) => b.top - a.top || b.area - a.area);
    return candidates[0]?.el ?? null;
  }

  function isScrollable(el) {
    const s = getComputedStyle(el);
    const oy = s.overflowY;
    if (oy !== 'auto' && oy !== 'scroll' && oy !== 'overlay') return false;
    return el.scrollHeight > el.clientHeight + 8;
  }

  function findMessageContainer(input) {
    const inputRect = input ? input.getBoundingClientRect() : null;
    const inputTop = inputRect?.top ?? window.innerHeight - 120;
    const minLeft = inputRect ? Math.max(0, inputRect.left - 80) : window.innerWidth * 0.18;

    for (const sel of ['main', '[role="main"]']) {
      const el = document.querySelector(sel);
      if (!el) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 280 || r.height < 120) continue;
      if (r.left < minLeft - 60) continue;
      if (inputTop > 0 && r.bottom > inputTop + 100) continue;
      return el;
    }

    let node = input?.parentElement ?? null;
    let inputScrollAncestor = null;
    while (node && node !== document.body) {
      const r = node.getBoundingClientRect();
      if (r.left >= minLeft - 40 && r.height > 100 && isScrollable(node)) {
        inputScrollAncestor = node;
      }
      node = node.parentElement;
    }
    if (inputScrollAncestor) return inputScrollAncestor;

    node = input?.parentElement ?? null;
    while (node && node !== document.body) {
      const r = node.getBoundingClientRect();
      if (r.left >= minLeft - 40 && r.height > 150 && !isScrollable(node)) {
        // Non-scroll wrapper around thread — prefer it over page-level scroll.
        return node;
      }
      node = node.parentElement;
    }

    const containers = [];
    for (const el of document.querySelectorAll('*')) {
      if (!isScrollable(el)) continue;
      const rect = el.getBoundingClientRect();
      if (rect.height < 120 || rect.width < 280) continue;
      if (inputTop > 0 && rect.bottom > inputTop + 80) continue;
      if (rect.left < minLeft - 60) continue;
      containers.push({ el, area: rect.width * rect.height });
    }
    containers.sort((a, b) => b.area - a.area);
    if (containers.length > 0) return containers[0].el;
    return document.scrollingElement || document.documentElement;
  }

  function mergeCaptures(captures) {
    const nonEmpty = captures.map(c => c.trim()).filter(Boolean);
    if (nonEmpty.length === 0) return '';
    let merged = nonEmpty[0];
    for (let i = 1; i < nonEmpty.length; i++) {
      const next = nonEmpty[i];
      let overlap = 0;
      const maxO = Math.min(merged.length, next.length, 800);
      for (let o = maxO; o > 15; o--) {
        if (merged.slice(-o) === next.slice(0, o)) {
          overlap = o;
          break;
        }
      }
      merged = merged + next.slice(overlap);
    }
    return merged;
  }

  function extractLastMessageDirect(container, inputTop) {
    const candidates = [];
    for (const el of container.querySelectorAll('div, article, section, main')) {
      const rect = el.getBoundingClientRect();
      if (rect.bottom > inputTop - 10) continue;
      if (rect.height < 40) continue;
      const t = (el.innerText || '').trim();
      if (t.length < 80) continue;
      let dominated = false;
      for (const child of el.children) {
        const ct = (child.innerText || '').trim();
        if (ct.length >= t.length * 0.92) {
          dominated = true;
          break;
        }
      }
      if (dominated) continue;
      candidates.push({ text: t, top: rect.top, len: t.length });
    }
    if (candidates.length === 0) return '';
    // Longest substantial block above input (avoid tiny trailing paragraph leaf).
    candidates.sort((a, b) => b.len - a.len);
    for (const c of candidates) {
      if (c.len >= 200) return c.text;
    }
    candidates.sort((a, b) => b.top - a.top);
    return candidates[0].text;
  }

  function scrollCollect(container) {
    const originalScrollTop = container.scrollTop;
    const step = Math.max(Math.floor(container.clientHeight * 0.85), 200);
    const maxSteps = Math.min(Math.ceil(container.scrollHeight / step) + 3, 80);
    const captures = [];
    for (let i = 0; i < maxSteps; i++) {
      container.scrollTop = Math.min(i * step, container.scrollHeight);
      void container.offsetHeight;
      captures.push((container.innerText || '').trim());
      if (container.scrollTop + container.clientHeight >= container.scrollHeight - 8) break;
    }
    container.scrollTop = originalScrollTop;
    return { merged: mergeCaptures(captures), steps: captures.length };
  }

  const input = findInputAnchor();
  const inputTop = input ? input.getBoundingClientRect().top : window.innerHeight - 120;
  const container = findMessageContainer(input);
  const directText = extractLastMessageDirect(container, inputTop);
  const { merged, steps } = scrollCollect(container);

  if (!merged && !directText) {
    return { ok: false, reason: 'no_text_in_container' };
  }

  return {
    ok: true,
    raw_text: merged || directText,
    direct_text: directText,
    scroll_steps: steps,
    container_tag: container.tagName,
  };
}
`;

export interface ExtractTextAtResult {
  ok: boolean;
  text?: string;
  char_count?: number;
  depth?: number;
  truncated?: boolean;
  reason?: string;
}

export interface ExtractAssistantReplyRaw {
  ok: boolean;
  raw_text?: string;
  direct_text?: string;
  scroll_steps?: number;
  container_tag?: string;
  reason?: string;
}

export interface ExtractAssistantReplyResult {
  ok: boolean;
  text: string;
  char_count: number;
  method: 'scroll_collect' | 'direct_dom';
  scroll_steps: number;
  truncated: boolean;
  reason?: string;
}

export async function extractTextAt(
  page: Page,
  x: number,
  y: number,
  maxChars: number = EXTRACT_TEXT_AT_MAX_CHARS,
): Promise<ExtractTextAtResult> {
  const raw = await page.evaluate(
    `(${EXTRACT_TEXT_AT_SCRIPT})(${x}, ${y}, ${maxChars})`,
  );
  return raw as ExtractTextAtResult;
}

export async function extractAssistantReplyRaw(
  page: Page,
): Promise<ExtractAssistantReplyRaw> {
  const raw = await page.evaluate(`(${EXTRACT_ASSISTANT_REPLY_SCRIPT})()`);
  return raw as ExtractAssistantReplyRaw;
}

function chooseSourceText(
  raw: ExtractAssistantReplyRaw,
  userMessage?: string,
): {
  text: string;
  method: 'scroll_collect' | 'direct_dom';
} {
  const scrollRefined = raw.raw_text
    ? refineAssistantReplyText(raw.raw_text, userMessage)
    : '';
  const directRefined = raw.direct_text
    ? refineAssistantReplyText(raw.direct_text, userMessage)
    : '';

  if (directRefined.length >= 150) {
    const scrollMuchLonger =
      scrollRefined.length > 0 && scrollRefined.length > directRefined.length * 1.8;
    const directIsMajority =
      !scrollRefined || directRefined.length >= scrollRefined.length * 0.45;
    if (
      !scrollRefined ||
      (directIsMajority && !scrollMuchLonger) ||
      (scrollMuchLonger && directRefined.length >= 300)
    ) {
      return { text: directRefined, method: 'direct_dom' };
    }
  }
  return {
    text: scrollRefined || directRefined,
    method: 'scroll_collect',
  };
}

export async function extractAssistantReply(
  page: Page,
  opts: { userMessage?: string; user_message?: string; maxChars?: number } = {},
): Promise<ExtractAssistantReplyResult> {
  const maxChars = opts.maxChars ?? DEFAULT_EXTRACT_MAX_CHARS;
  const userMessage = opts.userMessage ?? opts.user_message;
  const raw = await extractAssistantReplyRaw(page);
  if (!raw.ok || (!raw.raw_text && !raw.direct_text)) {
    logger.warn('extract_assistant_reply: no text', { reason: raw.reason });
    return {
      ok: false,
      text: '',
      char_count: 0,
      method: 'scroll_collect',
      scroll_steps: raw.scroll_steps ?? 0,
      truncated: false,
      reason: raw.reason ?? 'extraction_failed',
    };
  }

  let { text, method } = chooseSourceText(raw, userMessage);

  let truncated = false;
  if (text.length > maxChars) {
    text = text.slice(0, maxChars) + '...[truncated]';
    truncated = true;
  }

  return {
    ok: text.length > 0,
    text,
    char_count: text.length,
    method,
    scroll_steps: raw.scroll_steps ?? 0,
    truncated,
    ...(text.length === 0 ? { reason: 'empty_after_trim' } : {}),
  };
}
