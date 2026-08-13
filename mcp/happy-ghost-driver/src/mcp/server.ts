import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import type { Page } from 'playwright-core';
import { z } from 'zod';

import type { InterceptedRow, InterceptStore } from '../db/types.js';
import type { SnifferStats } from '../collect/sniffer.js';
import { logger } from '../util/logger.js';
import {
  getPageAccessibilityTree,
  A11Y_MAX_NODES,
} from '../percept/a11y.js';
import type { A11yNode } from '../percept/a11y.js';
import { createPhysicalCursor } from '../physical/cursor.js';
import type { PhysicalCursor } from '../physical/cursor.js';
import { typeText, pressKeys, MAX_TYPE_CHARS } from '../physical/keyboard.js';
import {
  readClipboardText,
  writeClipboardText,
  getLastClipboardWriteChars,
  MAX_CLIPBOARD_CHARS,
} from '../percept/clipboard.js';
import { setInputFiles } from '../percept/set-input-files.js';
import {
  extractTextAt,
  extractAssistantReply,
  DEFAULT_EXTRACT_MAX_CHARS,
  EXTRACT_TEXT_AT_MAX_CHARS,
} from '../percept/extract-text.js';
import { scroll, MAX_SCROLL_DISTANCE_PX } from '../physical/scroll.js';
import type { ScrollDirection } from '../physical/scroll.js';
import { withCooldown } from '../physical/cooldown.js';
import { captureScreenshotWithMeta } from '../percept/screenshot.js';
import type { ScreenshotWithMeta } from '../percept/screenshot.js';
import { guardAction, guardNavigation, rejectionPayload } from '../guard/index.js';
import type { GuardRejection } from '../guard/index.js';
import { clearWriteIntent, noteTyping } from '../guard/write-intent.js';
import { planReverseScroll, readingDwell } from '../physical/pacing.js';

// --- Constants -----------------------------------------------------------

const SERVER_NAME = 'ghost-driver-mcp';
const SERVER_VERSION = '0.0.1';

const TOOL_NAME_QUERY = 'query_intercepted_network_data';
const TOOL_NAME_A11Y = 'get_page_accessibility_tree';
const TOOL_NAME_CLICK = 'physical_click';
const TOOL_NAME_TYPE = 'physical_type';
const TOOL_NAME_SCROLL = 'physical_scroll';
const TOOL_NAME_SCREENSHOT = 'take_screenshot';
const TOOL_NAME_EXTRACT_TEXT_AT = 'extract_text_at';
const TOOL_NAME_EXTRACT_ASSISTANT_REPLY = 'extract_assistant_reply';
const TOOL_NAME_READ_CLIPBOARD = 'read_clipboard';
const TOOL_NAME_WRITE_CLIPBOARD = 'write_clipboard';
const TOOL_NAME_SET_INPUT_FILES = 'set_input_files';
const TOOL_NAME_KEYPRESS = 'physical_keypress';
const TOOL_NAME_NAVIGATE = 'browser_navigate';
const TOOL_NAME_LIST_TABS = 'list_tabs';
const TOOL_NAME_SELECT_TAB = 'select_tab';
const TOOL_NAME_CLOSE_TAB = 'close_tab';

const TOOL_DESCRIPTION_QUERY =
  '查询最近拦截到的、URL 匹配给定 SQL LIKE 模式的网络响应数据。' +
  'pattern 使用 SQL LIKE 通配符：% 匹配任意字符（包括空串），_ 匹配单个字符。' +
  '注意：这不是正则表达式。返回结构化 JSON，body 字段如果原本是合法 JSON 会被还原为对象。';

const TOOL_DESCRIPTION_A11Y =
  '获取当前页面的无障碍树（A11y tree），返回元素列表。' +
  '每个元素包含：role（无障碍角色，如 button/link/textbox）、' +
  'name（可读名称）、x/y（元素中心点坐标，CSS 像素，原点为视口左上角）、' +
  'width/height（元素尺寸）。' +
  '重要：本工具**不返回任何 CSS selector / XPath / locator**，只返回坐标和元数据。' +
  'AI 应基于 role+name 决定要操作的元素，然后将该元素的 x/y 传给 physical_click。';

const TOOL_DESCRIPTION_CLICK =
  '在指定坐标处执行拟人化鼠标点击。坐标原点为视口左上角，单位为 CSS 像素。' +
  '点击前会先用 ghost-cursor 的贝塞尔曲线移动鼠标到目标位置，' +
  '然后 mousedown -> 短延迟（50-150ms）-> mouseup，模拟人类按键节奏。' +
  '重要：本工具**不接受 selector / XPath / locator**，只接受像素坐标。' +
  '请先用 get_page_accessibility_tree 拿到目标元素的 x/y。';

const TOOL_DESCRIPTION_TYPE =
  '在当前已获得焦点的输入元素上逐字符输入文本。' +
  '每个字符之间插入随机延迟（50-200ms），模拟人类打字节奏。' +
  '换行符（\\n）会被映射为 Enter 按键。' +
  'replace=true 时先全选（macOS Meta+A / 其他平台 Control+A）再输入，用于换搜词时覆盖旧内容。' +
  `上限 ${MAX_TYPE_CHARS} 字，适合标题/摘要/标签搜索；` +
  '长文正文请用 write_clipboard + Meta+v，勿逐字打。' +
  '重要：本工具不负责聚焦——请先调用 physical_click 点击输入框。';

const TOOL_DESCRIPTION_SCROLL =
  '模拟人类滚动滚轮。distance_px 毫米的总滚动量会被拆分为 3-7 段，' +
  '每段之间间隔 30-80ms，模拟动量滚动而非一次性 wheel 事件。' +
  'direction 为 "up" 或 "down"。';

const TOOL_DESCRIPTION_SCREENSHOT =
  '对当前页面截图，并把图片作为 image 内容块直接回传给调用方（供 agent 自带的多模态视觉模型识别）。' +
  '本工具**不调用任何外部视觉 API、不消耗配额**，' +
  '只负责把图片和坐标换算元数据交给 agent，由 agent 自己看图定位' +
  '（需要视觉定位坐标时，配合项目内 .cursor/skills/screen-locate skill 使用）。' +
  '这是“看图 → 定位 → physical_click”自动驾驶闭环的感知入口。' +
  '返回内容：一个 image 块（base64 图片）+ 一个 text 块（JSON 元数据）。' +
  '元数据含 url、title、viewport_css(CSS 像素视口尺寸)、image_px(图片真实像素尺寸)、device_scale_factor。' +
  '关键坐标换算：从图片上读到的像素坐标，需 ÷ device_scale_factor 得到 CSS 像素坐标，再传给 physical_click。' +
  '重要：本工具不返回 selector / XPath，只返回图片与坐标元数据。';

const TOOL_DESCRIPTION_EXTRACT_TEXT_AT =
  '读取视口坐标 (x,y) 处元素及其祖先的完整 innerText（无 200 字截断）。' +
  '只读感知工具，不触发 DOM 事件。用于 A11y name 被截断时长段/表格补全，' +
  '或已知回答区坐标时的定点全文提取。';

const TOOL_DESCRIPTION_EXTRACT_ASSISTANT_REPLY =
  '在 AI 聊天页提取最新 assistant 回答全文。只读：在页面内程序滚动主消息容器、' +
  '合并各段 innerText，再取最后一条消息（可选传入 user_message 剔除用户提问）。' +
  '不受 A11y 200 字/节点 cap 限制，是 geo-qa 长回答的首选采集路径。';

const TOOL_DESCRIPTION_READ_CLIPBOARD =
  '读取系统剪贴板纯文本（macOS pbpaste / 其它平台等价命令）。' +
  '配合 physical_click 点平台「复制」按钮或 physical_keypress(Meta+c) 使用。' +
  '只读，无 cooldown。';

const TOOL_DESCRIPTION_WRITE_CLIPBOARD =
  '写入系统剪贴板纯文本（macOS pbcopy / 其它平台等价命令）。' +
  '用于长文注入：write_clipboard(正文) → physical_click 聚焦编辑区 → ' +
  'physical_keypress(Meta+v) 粘贴。正文勿用 physical_type（有字数上限且慢）。' +
  '粘贴会按剪贴板字数武装写意图闸门。无 cooldown。';

const TOOL_DESCRIPTION_SET_INPUT_FILES =
  '向页面 <input type="file"> 注入本地文件（绝对路径）。' +
  '封面图、正文插图、DOCX/MD 文件导入等场景使用；' +
  '这是对「禁止 CSS selector」规则的刻意例外——file input 通常对 A11y 不可见。' +
  '默认 selector 为 input[type="file"]（取第一个）；可按渠道手册传入更精确 selector。' +
  '注入后需用 a11y/截图确认上传完成，勿假定对话框会弹出。';

const TOOL_DESCRIPTION_KEYPRESS =
  '在当前页面焦点上按下键位组合（Playwright 格式，如 Meta+c、Control+a、Meta+v）。' +
  '用于复制/粘贴快捷键等；请先 physical_click 聚焦目标区域。' +
  'Meta+v / Control+v 粘贴后会按最近 write_clipboard 字数武装写意图闸门。';

const TOOL_DESCRIPTION_NAVIGATE =
  '在浏览器中打开一个 URL。默认在当前活动标签页导航；new_tab=true 时新开标签页。' +
  '导航完成后该标签页成为后续工具（a11y/点击/输入）操作的活动页。' +
  '返回 {ok, url, title}。这是 agent 自主打开页面的首选方式，无需外部手动开标签。';

const TOOL_DESCRIPTION_LIST_TABS =
  '列出当前浏览器所有内容标签页（http/https），按打开顺序返回 ' +
  '[{index, url, title, active, visible}]。active=当前工具操作的页，visible=前台可见页。' +
  '用于在多标签场景下查看有哪些页、决定切换到哪个。';

const TOOL_DESCRIPTION_SELECT_TAB =
  '把 list_tabs 返回的某个 index 对应的标签页设为活动页，并置于前台。' +
  '之后的 a11y/点击/输入都作用在该页。返回 {ok, url, title}。';

const TOOL_DESCRIPTION_CLOSE_TAB =
  '关闭 list_tabs 返回的某个 index 对应的标签页（例如任务完成后的清理、点击引用来源时被动新开的背景标签）。' +
  '如果被关的正是当前活动页，下一次操作会按 browser_navigate 的选页规则自动挑一个新的活动页' +
  '（优先前台可见的标签，其次最新的内容标签，都没有则新开一个空白页）。' +
  '保护规则：若该标签是浏览器最后一个存活页面，会拒绝关闭并返回 last_tab 错误' +
  '（关掉它会连带关闭整个浏览器，破坏常驻）——此时保留该标签即可，无需处理。' +
  '注意：每关一个标签后其余标签的 index 会前移，连续关多个时每次都要重新 list_tabs。' +
  '返回 {ok, closed_url}；index 越界返回 tab_not_found。';

const DEFAULT_LIMIT = 50;
const TOOL_MAX_LIMIT = 500;
const MAX_BODY_BYTES = 8 * 1024; // 8KB cap per item body before truncation
const TRUNCATE_SUFFIX = '...[truncated]';

const EMPTY_STATS: Readonly<SnifferStats> = Object.freeze({
  captured: 0,
  skipped: 0,
  errors: 0,
});

// --- Tool schemas (Phase 2) ----------------------------------------------

/**
 * Input schema for the query_intercepted_network_data tool.
 * Exported so tests / tooling can reuse the exact validation rules.
 */
export const QueryInterceptedArgsSchema = z
  .object({
    url_pattern: z
      .string()
      .min(1, 'url_pattern must be a non-empty SQL LIKE pattern'),
    limit: z
      .number()
      .int('limit must be an integer')
      .positive('limit must be positive')
      .max(TOOL_MAX_LIMIT, `limit must be <= ${TOOL_MAX_LIMIT}`)
      .optional(),
    since_ts: z
      .number()
      .int('since_ts must be an integer (millisecond epoch)')
      .nonnegative('since_ts must be >= 0')
      .optional(),
  })
  .strict();

export type QueryInterceptedArgs = z.infer<typeof QueryInterceptedArgsSchema>;

// --- Tool schemas (Phase 3) ----------------------------------------------

export const GetA11yArgsSchema = z
  .object({
    interesting_only: z
      .boolean()
      .optional()
      .describe('Reserved for forward compatibility; current implementation always filters to named/role-bearing nodes.'),
    max_nodes: z
      .number()
      .int('max_nodes must be an integer')
      .positive('max_nodes must be positive')
      .max(A11Y_MAX_NODES, `max_nodes must be <= ${A11Y_MAX_NODES}`)
      .optional(),
  })
  .strict();

export type GetA11yArgs = z.infer<typeof GetA11yArgsSchema>;

export const PhysicalClickArgsSchema = z
  .object({
    x: z
      .number()
      .nonnegative('x must be a non-negative number (CSS pixels from viewport left)'),
    y: z
      .number()
      .nonnegative('y must be a non-negative number (CSS pixels from viewport top)'),
  })
  .strict();

export type PhysicalClickArgs = z.infer<typeof PhysicalClickArgsSchema>;

export const PhysicalTypeArgsSchema = z
  .object({
    text: z
      .string()
      .min(1, 'text must be non-empty')
      .max(MAX_TYPE_CHARS, `text must be <= ${MAX_TYPE_CHARS} characters`),
    replace: z
      .boolean()
      .optional()
      .describe(
        'If true, select all in the focused field before typing (overwrites existing text).',
      ),
  })
  .strict();

export type PhysicalTypeArgs = z.infer<typeof PhysicalTypeArgsSchema>;

export const WriteClipboardArgsSchema = z
  .object({
    text: z
      .string()
      .min(1, 'text must be non-empty')
      .max(MAX_CLIPBOARD_CHARS, `text must be <= ${MAX_CLIPBOARD_CHARS} characters`),
  })
  .strict();

export type WriteClipboardArgs = z.infer<typeof WriteClipboardArgsSchema>;

export const SetInputFilesArgsSchema = z
  .object({
    path: z
      .string()
      .min(1, 'path must be non-empty')
      .describe('Absolute path to a local file that exists on disk.'),
    selector: z
      .string()
      .min(1)
      .optional()
      .describe(
        'CSS selector for <input type="file">. Default: input[type="file"] (first match).',
      ),
  })
  .strict();

export type SetInputFilesArgs = z.infer<typeof SetInputFilesArgsSchema>;

export const PhysicalScrollArgsSchema = z
  .object({
    direction: z
      .enum(['up', 'down'])
      .describe('Scroll direction: "up" scrolls content down, "down" scrolls content up.'),
    distance_px: z
      .number()
      .int('distance_px must be an integer')
      .positive('distance_px must be positive')
      .max(MAX_SCROLL_DISTANCE_PX, `distance_px must be <= ${MAX_SCROLL_DISTANCE_PX}`),
  })
  .strict();

export type PhysicalScrollArgs = z.infer<typeof PhysicalScrollArgsSchema>;

// --- Tool schemas (Phase 4) ----------------------------------------------

export const TakeScreenshotArgsSchema = z
  .object({
    full_page: z
      .boolean()
      .optional()
      .describe('Capture the full scrollable document instead of the viewport.'),
    max_bytes: z
      .number()
      .int('max_bytes must be an integer')
      .positive('max_bytes must be positive')
      .max(8 * 1024 * 1024, 'max_bytes must be <= 8 MiB')
      .optional()
      .describe('Soft cap on screenshot base64 length. Defaults to 1 MiB.'),
  })
  .strict();

export type TakeScreenshotArgs = z.infer<typeof TakeScreenshotArgsSchema>;

export const ExtractTextAtArgsSchema = z
  .object({
    x: z
      .number()
      .nonnegative('x must be a non-negative number (CSS pixels from viewport left)'),
    y: z
      .number()
      .nonnegative('y must be a non-negative number (CSS pixels from viewport top)'),
    max_chars: z
      .number()
      .int('max_chars must be an integer')
      .positive('max_chars must be positive')
      .max(EXTRACT_TEXT_AT_MAX_CHARS, `max_chars must be <= ${EXTRACT_TEXT_AT_MAX_CHARS}`)
      .optional(),
  })
  .strict();

export type ExtractTextAtArgs = z.infer<typeof ExtractTextAtArgsSchema>;

export const ExtractAssistantReplyArgsSchema = z
  .object({
    user_message: z
      .string()
      .optional()
      .describe(
        'Optional user question text to strip from merged container text before picking the last reply group.',
      ),
    max_chars: z
      .number()
      .int('max_chars must be an integer')
      .positive('max_chars must be positive')
      .max(DEFAULT_EXTRACT_MAX_CHARS, `max_chars must be <= ${DEFAULT_EXTRACT_MAX_CHARS}`)
      .optional(),
  })
  .strict();

export type ExtractAssistantReplyArgs = z.infer<typeof ExtractAssistantReplyArgsSchema>;

export const PhysicalKeypressArgsSchema = z
  .object({
    keys: z
      .string()
      .min(1, 'keys must be non-empty')
      .max(64, 'keys must be <= 64 characters')
      .describe('Playwright key chord, e.g. Meta+c, Control+a, Enter.'),
  })
  .strict();

export type PhysicalKeypressArgs = z.infer<typeof PhysicalKeypressArgsSchema>;

// --- Tab control schemas -------------------------------------------------

export const NavigateArgsSchema = z
  .object({
    url: z.string().url('url must be a valid absolute URL (http/https)'),
    new_tab: z.boolean().optional().describe('Open in a new tab instead of the active page.'),
  })
  .strict();

export const SelectTabArgsSchema = z
  .object({
    index: z
      .number()
      .int('index must be an integer')
      .nonnegative('index must be >= 0')
      .describe('Tab index from list_tabs.'),
  })
  .strict();

export const CloseTabArgsSchema = z
  .object({
    index: z
      .number()
      .int('index must be an integer')
      .nonnegative('index must be >= 0')
      .describe('Tab index from list_tabs.'),
  })
  .strict();

// --- Tool context (dependency injection) ---------------------------------

export interface QueryToolContext {
  /**
   * Provide live sniffer stats. May be a no-op when no sniffer is running
   * (e.g. the MCP server process has no browser attached in Phase 2).
   */
  statsProvider: () => SnifferStats;
  store: InterceptStore;
}

/**
 * The shape returned by the query tool. Plain data so we can JSON.stringify it.
 */
export interface ToolPayload {
  count: number;
  items: Array<{
    id: number;
    url: string;
    status: number | null;
    content_type: string | null;
    body: unknown; // parsed object, original string, or truncated string
    truncated: boolean;
    ts: number;
  }>;
  stats: SnifferStats;
}

/**
 * Wire shape returned by every Phase 3 tool when no browser page is
 * attached. Kept structurally distinct from success payloads so an
 * agent can pattern-match on the `error` field.
 */
export interface NotAttachedPayload {
  error: 'browser_not_attached';
  hint: string;
}

export interface A11yPayload {
  count: number;
  items: A11yNode[];
}

export interface PhysicalClickPayload {
  ok: true;
  x: number;
  y: number;
  durationMs: number;
  /** Present when the guard treated this click as a content submit. */
  submit?: true;
}

export interface PhysicalTypePayload {
  ok: true;
  chars: number;
  durationMs: number;
  replaced: boolean;
  /** Present when this text armed the submit gate for the page. */
  writeIntentArmed?: true;
  /** Present when a trailing newline was routed through the submit gate. */
  submit?: true;
}

export interface PhysicalScrollPayload {
  ok: true;
  direction: ScrollDirection;
  distancePx: number;
  durationMs: number;
  /** Present when pacing added a small corrective scroll the other way. */
  reverseScrollPx?: number;
}

/**
 * Action surface injected into physical handlers. Tests pass mocks;
 * production wires this up with a real Page + the cursor/keyboard/scroll
 * helpers from src/physical.
 *
 * The reason for this interface (rather than handlers reaching into
 * src/physical directly) is testability: unit tests can assert that a
 * click handler invokes the cursor with the right coordinates without
 * spawning a real browser.
 */
export interface PhysicalTypeOptions {
  replace?: boolean;
}

export interface PhysicalActions {
  click(x: number, y: number): Promise<void>;
  type(text: string, opts?: PhysicalTypeOptions): Promise<number>;
  pressKeys(keys: string): Promise<void>;
  scroll(direction: ScrollDirection, distancePx: number): Promise<void>;
  getA11y(maxNodes: number): Promise<A11yNode[]>;
}

// --- Pure tool logic (Phase 2) -------------------------------------------

/**
 * Transform a raw DB row into the wire-shape item, parsing JSON bodies and
 * truncating oversized bodies. Pure function — no I/O.
 */
export function transformRow(row: InterceptedRow): ToolPayload['items'][number] {
  const body = parseBody(row.body);
  return {
    id: row.id,
    url: row.url,
    status: row.status,
    content_type: row.content_type,
    body: body.value,
    truncated: body.truncated,
    ts: row.ts,
  };
}

interface ParsedBody {
  value: unknown;
  truncated: boolean;
}

function parseBody(raw: string | null | undefined): ParsedBody {
  if (raw === null || raw === undefined) {
    return { value: null, truncated: false };
  }
  const source = typeof raw === 'string' ? raw : String(raw);

  // Truncation operates on the raw bytes BEFORE parse attempt, so that an
  // oversized body never blows up the LLM context regardless of whether
  // it parses as JSON.
  let effective = source;
  let truncated = false;
  const sourceBytes = Buffer.byteLength(source, 'utf8');
  if (sourceBytes > MAX_BODY_BYTES) {
    // Truncate by characters until we fit under the byte budget, then
    // append the suffix. We slice UTF-8 bytes safely by checking length.
    effective = truncateUtf8(source, MAX_BODY_BYTES - TRUNCATE_SUFFIX.length);
    effective = effective + TRUNCATE_SUFFIX;
    truncated = true;
  }

  // Try to parse as JSON only on non-truncated bodies. A truncated JSON
  // blob would yield a partial object that misrepresents the source.
  if (!truncated) {
    const trimmed = effective.trim();
    if (
      (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
      (trimmed.startsWith('[') && trimmed.endsWith(']'))
    ) {
      try {
        return { value: JSON.parse(effective), truncated: false };
      } catch {
        // fall through; return as string
      }
    }
  }

  return { value: effective, truncated };
}

function truncateUtf8(input: string, maxBytes: number): string {
  if (maxBytes <= 0) return '';
  const totalBytes = Buffer.byteLength(input, 'utf8');
  if (totalBytes <= maxBytes) return input;
  // Encode, slice on byte boundary, then trim any trailing partial UTF-8
  // sequence so the result is valid UTF-8.
  const buf = Buffer.from(input, 'utf8');
  let end = maxBytes;
  while (end > 0 && (buf[end - 1]! & 0xc0) === 0x80) {
    end--; // skip continuation bytes
  }
  if (end > 0 && (buf[end - 1]! & 0xe0) === 0xc0) {
    end -= 1; // drop a 2-byte lead with no continuation
  } else if (end > 1 && (buf[end - 2]! & 0xf0) === 0xe0) {
    end -= 2;
  } else if (end > 2 && (buf[end - 3]! & 0xf8) === 0xf0) {
    end -= 3;
  }
  return buf.subarray(0, end).toString('utf8');
}

/**
 * Pure handler for the query_intercepted_network_data tool.
 *
 * It performs no transport-level work; the caller is responsible for
 * opening the database and providing a statsProvider. This makes it
 * trivially unit-testable without spinning up stdio.
 *
 * Returns a CallToolResult-shaped object so it can be returned verbatim
 * by the MCP server's CallToolRequest handler.
 */
export async function handleQueryIntercepted(
  args: unknown,
  ctx: QueryToolContext,
): Promise<{
  content: Array<{ type: 'text'; text: string }>;
  isError?: boolean;
}> {
  const parsed = QueryInterceptedArgsSchema.safeParse(args);
  if (!parsed.success) {
    return {
      isError: true,
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            error: 'invalid_arguments',
            details: parsed.error.issues,
          }),
        },
      ],
    };
  }

  const limit = parsed.data.limit ?? DEFAULT_LIMIT;
  const rows = await ctx.store.query({
    urlPattern: parsed.data.url_pattern,
    limit,
    sinceTs: parsed.data.since_ts,
  });

  const items = rows.map(transformRow);
  const stats = safeStats(ctx.statsProvider);

  const payload: ToolPayload = {
    count: items.length,
    items,
    stats,
  };

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(payload),
      },
    ],
  };
}

function safeStats(provider: () => SnifferStats): SnifferStats {
  try {
    const s = provider();
    return {
      captured: s.captured,
      skipped: s.skipped,
      errors: s.errors,
    };
  } catch {
    return { ...EMPTY_STATS };
  }
}

// --- Pure tool logic (Phase 3) -------------------------------------------

/**
 * Shared helper that builds a CallToolResult from a JSON-serialisable
 * payload. Keeps the handlers focused on business logic.
 */
function jsonResult(payload: unknown): {
  content: Array<{ type: 'text'; text: string }>;
  isError?: boolean;
} {
  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(payload),
      },
    ],
  };
}

/** Compact, log-safe one-line summary of tool arguments. */
function summarizeArgs(args: unknown): string {
  try {
    const s = JSON.stringify(args);
    return s.length > 200 ? `${s.slice(0, 200)}…(${s.length}b)` : s;
  } catch {
    return '(unserializable)';
  }
}

function invalidArgs(issues: z.ZodIssue[]): {
  content: Array<{ type: 'text'; text: string }>;
  isError: true;
} {
  return {
    isError: true,
    content: [
      {
        type: 'text',
        text: JSON.stringify({ error: 'invalid_arguments', details: issues }),
      },
    ],
  };
}

/**
 * Surface a guard refusal to the agent.
 *
 * Returned as an error so the model cannot mistake it for a completed
 * action, and with the guard's own message intact: the message tells the
 * agent why retrying or switching domains is the wrong response.
 */
function guardRefusedResult(rejection: GuardRejection): {
  content: Array<{ type: 'text'; text: string }>;
  isError: true;
} {
  return {
    isError: true,
    content: [{ type: 'text', text: JSON.stringify(rejectionPayload(rejection)) }],
  };
}

function notAttachedResult(tool: string): {
  content: Array<{ type: 'text'; text: string }>;
  isError: true;
} {
  const payload: NotAttachedPayload = {
    error: 'browser_not_attached',
    hint: `${tool} requires a browser page. Start the server with CDP_ENDPOINT set, e.g. CDP_ENDPOINT=http://localhost:9222`,
  };
  return { isError: true, content: [{ type: 'text', text: JSON.stringify(payload) }] };
}

/**
 * Resolve the actions surface for a call.
 *
 * Priority:
 *   1. Explicitly-injected `deps.actions` (tests / programmatic callers).
 *   2. Live page from `deps.getPage()` (production lazy/self-healing attach).
 *   3. Static `deps.page` (legacy / direct injection).
 *   4. null — handler returns `browser_not_attached`.
 *
 * Injected actions win even without a page so unit tests can exercise
 * the handlers without spawning a browser.
 */
async function resolveActions(deps: PhysicalToolDeps): Promise<PhysicalActions | null> {
  const ctx = await resolveActionContext(deps);
  return ctx?.actions ?? null;
}

/**
 * Resolve both the action surface and the page behind it.
 *
 * The page is what the account-safety guards need (URL, visibility, quota
 * domain). It is intentionally null when a caller injected `deps.actions`
 * without a page — that is the unit-test path, where there is no account to
 * protect and therefore nothing for the guards to do.
 */
async function resolveActionContext(
  deps: PhysicalToolDeps,
): Promise<{ actions: PhysicalActions; page: Page | null } | null> {
  const page = await resolvePage(deps);
  if (deps.actions) return { actions: deps.actions, page };
  if (!page) return null;
  return { actions: defaultActionsForPage(page), page };
}

/** Resolve a live page, preferring the lazy provider over a static handle. */
async function resolvePage(deps: {
  page?: Page;
  getPage?: () => Promise<Page | null>;
}): Promise<Page | null> {
  if (deps.getPage) {
    const p = await deps.getPage();
    if (p) return p;
  }
  return deps.page ?? null;
}

/**
 * Build a PhysicalActions implementation backed by a real Playwright
 * page. Each method delegates to the corresponding src/physical helper
 * but DOES NOT itself wrap withCooldown — the handlers do that so the
 * timing bookkeeping (durationMs) is correct.
 */
function defaultActionsForPage(page: Page): PhysicalActions {
  const cursor: PhysicalCursor = createPhysicalCursor(page);
  return {
    async click(x, y) {
      await cursor.click(x, y);
    },
    async type(text, opts) {
      return typeText(page, text, { replace: opts?.replace });
    },
    async pressKeys(keys) {
      await pressKeys(page, keys);
    },
    async scroll(direction, distancePx) {
      await scroll(page, direction, distancePx);
    },
    async getA11y(maxNodes) {
      return getPageAccessibilityTree(page, { maxNodes });
    },
  };
}

/** One open tab as surfaced to the agent. */
export interface TabInfo {
  index: number;
  url: string;
  title: string;
  active: boolean;
  visible: boolean;
}

export interface NavigateResult {
  ok: true;
  url: string;
  title: string;
}

/** Tab/navigation control surface, injected from the PageProvider. */
export interface TabController {
  navigate(url: string, opts?: { newTab?: boolean }): Promise<NavigateResult | null>;
  listTabs(): Promise<TabInfo[]>;
  selectTab(index: number): Promise<NavigateResult | null>;
  closeTab(index: number): Promise<CloseTabResult | null>;
}

export type CloseTabResult =
  | { ok: true; closedUrl: string }
  | { ok: false; reason: 'last_tab'; url: string };

/** Deps shared by all four Phase 3 handlers. */
export interface PhysicalToolDeps {
  /** The attached page. Null when no browser is connected. */
  page?: Page;
  /**
   * Lazy/self-healing page resolver. Production wires this to a
   * PageProvider so the browser connection is established on first use
   * and transparently re-established after Chrome restarts.
   */
  getPage?: () => Promise<Page | null>;
  /**
   * Optional injected action surface. Tests pass mocks here so handlers
   * can be exercised without a browser. Production leaves this undefined
   * and a real cursor/keyboard/scroll stack is built from `page`.
   */
  actions?: PhysicalActions;
}

/**
 * Handler for `get_page_accessibility_tree`.
 *
 * Returns the A11y tree as a flat list of nodes with role+name+centre
 * coordinates. This is a READ-ONLY perception call (a page-evaluate that
 * dispatches no input), so it is intentionally NOT wrapped in withCooldown:
 * README §7's 1-3s pacing targets *physical actions* (click/type/scroll),
 * not observation. Skipping cooldown here removes ~2-6s/step of dead time
 * that dominated multi-step agent tasks.
 */
export async function handleGetA11yTree(
  args: unknown,
  deps: PhysicalToolDeps,
): Promise<{
  content: Array<{ type: 'text'; text: string }>;
  isError?: boolean;
}> {
  const parsed = GetA11yArgsSchema.safeParse(args ?? {});
  if (!parsed.success) {
    return invalidArgs(parsed.error.issues);
  }
  const actions = await resolveActions(deps);
  if (!actions) {
    return notAttachedResult(TOOL_NAME_A11Y);
  }
  const maxNodes = parsed.data.max_nodes ?? A11Y_MAX_NODES;
  try {
    const items = await actions.getA11y(maxNodes);
    const payload: A11yPayload = { count: items.length, items };
    return jsonResult(payload);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      isError: true,
      content: [
        { type: 'text', text: JSON.stringify({ error: 'a11y_failed', message: msg }) },
      ],
    };
  }
}

/**
 * Handler for `physical_click`. Coordinates-only; no selector.
 * Wrapped in withCooldown so a 1-3s human pause bookends every click.
 *
 * A click is also the gesture that submits. When typing has armed a write
 * intent on this page, the guard reclassifies this click as the submit and
 * routes it through the pre-publish dwell, archive and write quota.
 */
export async function handlePhysicalClick(
  args: unknown,
  deps: PhysicalToolDeps,
): Promise<{
  content: Array<{ type: 'text'; text: string }>;
  isError?: boolean;
}> {
  const parsed = PhysicalClickArgsSchema.safeParse(args ?? {});
  if (!parsed.success) {
    return invalidArgs(parsed.error.issues);
  }
  const ctx = await resolveActionContext(deps);
  if (!ctx) {
    return notAttachedResult(TOOL_NAME_CLICK);
  }
  const { actions, page } = ctx;
  const { x, y } = parsed.data;
  const startedAt = Date.now();

  const guard = await guardAction({
    page,
    actionType: 'click',
    baseClass: 'light',
    canSubmit: true,
    detail: `x=${x},y=${y}`,
  });
  if (!guard.ok) return guardRefusedResult(guard.rejection);

  try {
    await withCooldown(() => actions.click(x, y));
    const payload: PhysicalClickPayload = {
      ok: true,
      x,
      y,
      durationMs: Date.now() - startedAt,
      ...(guard.submit ? { submit: true } : {}),
    };
    return jsonResult(payload);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      isError: true,
      content: [
        { type: 'text', text: JSON.stringify({ error: 'click_failed', message: msg }) },
      ],
    };
  }
}

/**
 * Handler for `physical_type`. Types the given text into the focused
 * element. Wrapped in withCooldown.
 *
 * Typing enough text arms the submit gate for this page, so the click or
 * Enter that follows is recognised as publishing rather than as an ordinary
 * click.
 *
 * A TRAILING newline is split out and routed through the gate explicitly.
 * `typeText` maps '\n' to Enter, so `physical_type("my post\n")` would
 * otherwise compose and publish inside a single ungated call — the one
 * bypass that would make the whole gate decorative. Newlines *inside* the
 * text are left alone: those are line breaks in multi-line content, and the
 * subsequent explicit submit is still gated.
 */
export async function handlePhysicalType(
  args: unknown,
  deps: PhysicalToolDeps,
): Promise<{
  content: Array<{ type: 'text'; text: string }>;
  isError?: boolean;
}> {
  const parsed = PhysicalTypeArgsSchema.safeParse(args ?? {});
  if (!parsed.success) {
    return invalidArgs(parsed.error.issues);
  }
  const ctx = await resolveActionContext(deps);
  if (!ctx) {
    return notAttachedResult(TOOL_NAME_TYPE);
  }
  const { actions, page } = ctx;
  const { text, replace } = parsed.data;
  const startedAt = Date.now();

  const body = text.replace(/\n+$/, '');
  const submitsOnEnter = body.length !== text.length;

  const guard = await guardAction({
    page,
    actionType: 'type',
    baseClass: 'light',
    detail: `chars=${text.length}`,
  });
  if (!guard.ok) return guardRefusedResult(guard.rejection);

  try {
    let chars = 0;
    if (body.length > 0) {
      chars = await withCooldown(() => actions.type(body, { replace }));
    }

    const armed = page !== null && body.length > 0 && noteTyping(page, body.length, page.url());

    // The trailing Enter is a separate, gated action.
    let submitted = false;
    if (submitsOnEnter) {
      const submitGuard = await guardAction({
        page,
        actionType: 'keypress',
        baseClass: 'light',
        canSubmit: true,
        detail: 'Enter (trailing newline)',
      });
      if (!submitGuard.ok) {
        // The text is typed and still sitting in the field; report the
        // refusal rather than pressing Enter anyway.
        return guardRefusedResult(submitGuard.rejection);
      }
      await withCooldown(() => actions.pressKeys('Enter'));
      submitted = submitGuard.submit;
      chars += text.length - body.length;
    }

    const payload: PhysicalTypePayload = {
      ok: true,
      chars,
      durationMs: Date.now() - startedAt,
      replaced: replace === true,
      ...(armed && !submitsOnEnter ? { writeIntentArmed: true as const } : {}),
      ...(submitted ? { submit: true as const } : {}),
    };
    return jsonResult(payload);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      isError: true,
      content: [
        { type: 'text', text: JSON.stringify({ error: 'type_failed', message: msg }) },
      ],
    };
  }
}

/**
 * Handler for `physical_scroll`. Scrolls in the given direction by
 * `distance_px` pixels, dispatched as a sequence of small wheel events.
 * Wrapped in withCooldown.
 */
export async function handlePhysicalScroll(
  args: unknown,
  deps: PhysicalToolDeps,
): Promise<{
  content: Array<{ type: 'text'; text: string }>;
  isError?: boolean;
}> {
  const parsed = PhysicalScrollArgsSchema.safeParse(args ?? {});
  if (!parsed.success) {
    return invalidArgs(parsed.error.issues);
  }
  const ctx = await resolveActionContext(deps);
  if (!ctx) {
    return notAttachedResult(TOOL_NAME_SCROLL);
  }
  const { actions, page } = ctx;
  const { direction, distance_px } = parsed.data;
  const startedAt = Date.now();

  const guard = await guardAction({
    page,
    actionType: 'scroll',
    baseClass: 'read',
    detail: `${direction},${distance_px}px`,
  });
  if (!guard.ok) return guardRefusedResult(guard.rejection);

  try {
    await withCooldown(() => actions.scroll(direction, distance_px));

    // Occasional drift back the other way: the correction a person makes
    // after scrolling past something. Only for real pages — a mock surface
    // has no feed to overshoot.
    let reversePx: number | undefined;
    if (page) {
      const reverse = planReverseScroll(direction, distance_px);
      if (reverse) {
        await withCooldown(() => actions.scroll(reverse.direction, reverse.distancePx));
        reversePx = reverse.distancePx;
      }
    }

    const payload: PhysicalScrollPayload = {
      ok: true,
      direction,
      distancePx: distance_px,
      durationMs: Date.now() - startedAt,
      ...(reversePx !== undefined ? { reverseScrollPx: reversePx } : {}),
    };
    return jsonResult(payload);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      isError: true,
      content: [
        { type: 'text', text: JSON.stringify({ error: 'scroll_failed', message: msg }) },
      ],
    };
  }
}

// --- Tab / navigation tool logic -----------------------------------------

function noBrowserResult(tool: string): {
  content: Array<{ type: 'text'; text: string }>;
  isError: true;
} {
  const payload: NotAttachedPayload = {
    error: 'browser_not_attached',
    hint: `${tool} requires a reachable Chrome (CDP). Start Chrome with --remote-debugging-port=9222 or let the server auto-launch it.`,
  };
  return { isError: true, content: [{ type: 'text', text: JSON.stringify(payload) }] };
}

export async function handleNavigate(
  args: unknown,
  deps: { controller?: TabController; getPage?: () => Promise<Page | null> },
): Promise<{ content: Array<{ type: 'text'; text: string }>; isError?: boolean }> {
  const parsed = NavigateArgsSchema.safeParse(args ?? {});
  if (!parsed.success) return invalidArgs(parsed.error.issues);
  if (!deps.controller) return noBrowserResult(TOOL_NAME_NAVIGATE);

  // Billed to the destination's read quota: the risk of opening 400 pages in
  // an hour belongs to the site being opened, not the one being left.
  const guard = await guardNavigation(parsed.data.url);
  if (!guard.ok) return guardRefusedResult(guard.rejection);

  const res = await withCooldown(() =>
    deps.controller!.navigate(parsed.data.url, { newTab: parsed.data.new_tab ?? false }),
  );
  if (!res) return noBrowserResult(TOOL_NAME_NAVIGATE);

  if (deps.getPage) {
    const page = await deps.getPage();
    if (page) {
      // Whatever was half-composed belongs to the page we just left.
      clearWriteIntent(page);
      // Then pause as if actually reading what was opened, instead of
      // firing the next action the instant the DOM settles.
      await readingDwell(page);
    }
  }
  return jsonResult(res);
}

export async function handleListTabs(
  _args: unknown,
  deps: { controller?: TabController },
): Promise<{ content: Array<{ type: 'text'; text: string }>; isError?: boolean }> {
  if (!deps.controller) return noBrowserResult(TOOL_NAME_LIST_TABS);
  const tabs = await deps.controller.listTabs();
  return jsonResult({ count: tabs.length, tabs });
}

export async function handleSelectTab(
  args: unknown,
  deps: { controller?: TabController },
): Promise<{ content: Array<{ type: 'text'; text: string }>; isError?: boolean }> {
  const parsed = SelectTabArgsSchema.safeParse(args ?? {});
  if (!parsed.success) return invalidArgs(parsed.error.issues);
  if (!deps.controller) return noBrowserResult(TOOL_NAME_SELECT_TAB);
  const res = await deps.controller.selectTab(parsed.data.index);
  if (!res) {
    return {
      isError: true,
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            error: 'tab_not_found',
            hint: `No tab at index ${parsed.data.index}. Call ${TOOL_NAME_LIST_TABS} first.`,
          }),
        },
      ],
    };
  }
  return jsonResult(res);
}

export async function handleCloseTab(
  args: unknown,
  deps: { controller?: TabController },
): Promise<{ content: Array<{ type: 'text'; text: string }>; isError?: boolean }> {
  const parsed = CloseTabArgsSchema.safeParse(args ?? {});
  if (!parsed.success) return invalidArgs(parsed.error.issues);
  if (!deps.controller) return noBrowserResult(TOOL_NAME_CLOSE_TAB);
  const res = await deps.controller.closeTab(parsed.data.index);
  if (!res) {
    return {
      isError: true,
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            error: 'tab_not_found',
            hint: `No tab at index ${parsed.data.index}. Call ${TOOL_NAME_LIST_TABS} first.`,
          }),
        },
      ],
    };
  }
  if (!res.ok) {
    return {
      isError: true,
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            error: 'last_tab',
            url: res.url,
            hint:
              'Refused to close the last remaining tab: closing it would shut down the whole browser. ' +
              'Leave it open (the browser is meant to stay resident); no further action needed.',
          }),
        },
      ],
    };
  }
  return jsonResult({ ok: true, closed_url: res.closedUrl });
}

// --- take_screenshot tool logic ------------------------------------------

/**
 * A single MCP tool content block. Most tools return only text; the
 * screenshot tool also returns an `image` block so the agent's own
 * multimodal model can see the page.
 */
export type ToolContentBlock =
  | { type: 'text'; text: string }
  | { type: 'image'; data: string; mimeType: string };

/** Metadata text block accompanying the screenshot image. */
export interface TakeScreenshotMeta {
  url: string;
  title: string;
  viewport_css: { width: number; height: number };
  image_px: { width: number; height: number };
  device_scale_factor: number;
  truncated: boolean;
  coord_hint: string;
}

/**
 * Handler for `take_screenshot`.
 *
 * READ-ONLY perception, like get_page_accessibility_tree: NOT wrapped in
 * withCooldown, does NOT touch quota, and does NOT require a foreground
 * check or any API key. It captures the page and hands the raw image
 * (plus coordinate-mapping metadata) back to the agent.
 */
export async function handleTakeScreenshot(
  args: unknown,
  deps: PhysicalToolDeps,
): Promise<{ content: ToolContentBlock[]; isError?: boolean }> {
  const parsed = TakeScreenshotArgsSchema.safeParse(args ?? {});
  if (!parsed.success) {
    return invalidArgs(parsed.error.issues);
  }
  const page = await resolvePage(deps);
  if (!page) {
    return notAttachedResult(TOOL_NAME_SCREENSHOT);
  }

  let shot: ScreenshotWithMeta;
  try {
    shot = await captureScreenshotWithMeta(page, {
      ...(parsed.data.full_page !== undefined ? { fullPage: parsed.data.full_page } : {}),
      ...(parsed.data.max_bytes !== undefined ? { maxBytes: parsed.data.max_bytes } : {}),
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      isError: true,
      content: [
        { type: 'text', text: JSON.stringify({ error: 'screenshot_failed', message: msg }) },
      ],
    };
  }

  let url = '';
  try {
    url = page.url();
  } catch {
    url = '';
  }
  let title = '';
  try {
    title = await page.title();
  } catch {
    title = '';
  }

  const meta: TakeScreenshotMeta = {
    url,
    title,
    viewport_css: { width: shot.cssWidth, height: shot.cssHeight },
    image_px: { width: shot.imagePxWidth, height: shot.imagePxHeight },
    device_scale_factor: shot.deviceScaleFactor,
    truncated: shot.truncated,
    coord_hint:
      'Divide image_px coordinates by device_scale_factor to get CSS pixels for physical_click.',
  };

  return {
    content: [
      { type: 'image', data: shot.base64, mimeType: shot.mediaType },
      { type: 'text', text: JSON.stringify(meta) },
    ],
  };
}

// --- extract_text_at / extract_assistant_reply / read_clipboard ---------

export interface ExtractTextAtPayload {
  ok: boolean;
  text: string;
  char_count: number;
  depth?: number;
  truncated?: boolean;
  reason?: string;
}

export interface ExtractAssistantReplyPayload {
  ok: boolean;
  text: string;
  char_count: number;
  method: 'scroll_collect' | 'direct_dom';
  scroll_steps: number;
  truncated: boolean;
  reason?: string;
}

export interface ReadClipboardPayload {
  ok: true;
  text: string;
  char_count: number;
  truncated: boolean;
}

export interface PhysicalKeypressPayload {
  ok: true;
  keys: string;
  durationMs: number;
}

export async function handleExtractTextAt(
  args: unknown,
  deps: PhysicalToolDeps,
): Promise<{ content: ToolContentBlock[]; isError?: boolean }> {
  const parsed = ExtractTextAtArgsSchema.safeParse(args ?? {});
  if (!parsed.success) {
    return invalidArgs(parsed.error.issues);
  }
  const page = await resolvePage(deps);
  if (!page) {
    return notAttachedResult(TOOL_NAME_EXTRACT_TEXT_AT);
  }
  const { x, y, max_chars } = parsed.data;
  try {
    const result = await extractTextAt(page, x, y, max_chars ?? EXTRACT_TEXT_AT_MAX_CHARS);
    const payload: ExtractTextAtPayload = {
      ok: result.ok,
      text: result.text ?? '',
      char_count: result.char_count ?? 0,
      ...(result.depth !== undefined ? { depth: result.depth } : {}),
      ...(result.truncated !== undefined ? { truncated: result.truncated } : {}),
      ...(result.reason !== undefined ? { reason: result.reason } : {}),
    };
    return jsonResult(payload);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      isError: true,
      content: [
        {
          type: 'text',
          text: JSON.stringify({ error: 'extract_text_at_failed', message: msg }),
        },
      ],
    };
  }
}

export async function handleExtractAssistantReply(
  args: unknown,
  deps: PhysicalToolDeps,
): Promise<{ content: ToolContentBlock[]; isError?: boolean }> {
  const parsed = ExtractAssistantReplyArgsSchema.safeParse(args ?? {});
  if (!parsed.success) {
    return invalidArgs(parsed.error.issues);
  }
  const page = await resolvePage(deps);
  if (!page) {
    return notAttachedResult(TOOL_NAME_EXTRACT_ASSISTANT_REPLY);
  }
  try {
    const result = await extractAssistantReply(page, {
      ...(parsed.data.user_message !== undefined
        ? { userMessage: parsed.data.user_message }
        : {}),
      ...(parsed.data.max_chars !== undefined ? { maxChars: parsed.data.max_chars } : {}),
    });
    const payload: ExtractAssistantReplyPayload = {
      ok: result.ok,
      text: result.text,
      char_count: result.char_count,
      method: result.method,
      scroll_steps: result.scroll_steps,
      truncated: result.truncated,
      ...(result.reason !== undefined ? { reason: result.reason } : {}),
    };
    return jsonResult(payload);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      isError: true,
      content: [
        {
          type: 'text',
          text: JSON.stringify({ error: 'extract_assistant_reply_failed', message: msg }),
        },
      ],
    };
  }
}

export async function handleReadClipboard(
  _args: unknown,
  deps: PhysicalToolDeps,
): Promise<{ content: ToolContentBlock[]; isError?: boolean }> {
  const page = await resolvePage(deps);
  if (!page) {
    return notAttachedResult(TOOL_NAME_READ_CLIPBOARD);
  }
  try {
    const text = await readClipboardText();
    const truncated = text.endsWith('...[truncated]');
    const payload: ReadClipboardPayload = {
      ok: true,
      text,
      char_count: text.length,
      truncated,
    };
    return jsonResult(payload);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      isError: true,
      content: [
        { type: 'text', text: JSON.stringify({ error: 'read_clipboard_failed', message: msg }) },
      ],
    };
  }
}

export interface WriteClipboardPayload {
  ok: true;
  char_count: number;
  truncated: boolean;
}

export async function handleWriteClipboard(
  args: unknown,
  _deps: PhysicalToolDeps,
): Promise<{ content: ToolContentBlock[]; isError?: boolean }> {
  const parsed = WriteClipboardArgsSchema.safeParse(args ?? {});
  if (!parsed.success) {
    return invalidArgs(parsed.error.issues);
  }
  try {
    const originalLen = parsed.data.text.replace(/\r\n/g, '\n').length;
    const charCount = await writeClipboardText(parsed.data.text);
    const payload: WriteClipboardPayload = {
      ok: true,
      char_count: charCount,
      truncated: charCount < originalLen,
    };
    return jsonResult(payload);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      isError: true,
      content: [
        {
          type: 'text',
          text: JSON.stringify({ error: 'write_clipboard_failed', message: msg }),
        },
      ],
    };
  }
}

export interface SetInputFilesPayload {
  ok: true;
  path: string;
  selector: string;
  input_count: number;
  durationMs: number;
}

export async function handleSetInputFiles(
  args: unknown,
  deps: PhysicalToolDeps,
): Promise<{ content: ToolContentBlock[]; isError?: boolean }> {
  const parsed = SetInputFilesArgsSchema.safeParse(args ?? {});
  if (!parsed.success) {
    return invalidArgs(parsed.error.issues);
  }
  const page = await resolvePage(deps);
  if (!page) {
    return notAttachedResult(TOOL_NAME_SET_INPUT_FILES);
  }
  const startedAt = Date.now();
  const guard = await guardAction({
    page,
    actionType: 'type',
    baseClass: 'light',
    detail: `set_input_files path=${parsed.data.path}`,
  });
  if (!guard.ok) return guardRefusedResult(guard.rejection);

  try {
    const result = await withCooldown(() =>
      setInputFiles(page, parsed.data.path, parsed.data.selector),
    );
    // Body import (docx/md) counts as composition for the submit gate.
    const lower = parsed.data.path.toLowerCase();
    if (/\.(docx|md|markdown|html|htm)$/.test(lower)) {
      noteTyping(page, 5000, page.url());
    }
    const payload: SetInputFilesPayload = {
      ok: true,
      path: result.path,
      selector: result.selector,
      input_count: result.input_count,
      durationMs: Date.now() - startedAt,
    };
    return jsonResult(payload);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      isError: true,
      content: [
        {
          type: 'text',
          text: JSON.stringify({ error: 'set_input_files_failed', message: msg }),
        },
      ],
    };
  }
}

/**
 * True for the chords that publish: bare Enter and the Cmd/Ctrl+Enter
 * shortcut most editors bind to "send". Copy/paste chords are not submits,
 * so they stay ordinary light actions.
 */
function isSubmitChord(keys: string): boolean {
  return /(^|\+)enter$/i.test(keys.trim());
}

/** Meta+v / Control+v — paste after write_clipboard. */
function isPasteChord(keys: string): boolean {
  const k = keys.trim().toLowerCase();
  return k === 'meta+v' || k === 'control+v' || k === 'ctrl+v';
}

export async function handlePhysicalKeypress(
  args: unknown,
  deps: PhysicalToolDeps,
): Promise<{ content: ToolContentBlock[]; isError?: boolean }> {
  const parsed = PhysicalKeypressArgsSchema.safeParse(args ?? {});
  if (!parsed.success) {
    return invalidArgs(parsed.error.issues);
  }
  const ctx = await resolveActionContext(deps);
  if (!ctx) {
    return notAttachedResult(TOOL_NAME_KEYPRESS);
  }
  const { actions, page } = ctx;
  const { keys } = parsed.data;
  const startedAt = Date.now();

  const guard = await guardAction({
    page,
    actionType: 'keypress',
    baseClass: 'light',
    canSubmit: isSubmitChord(keys),
    detail: keys,
  });
  if (!guard.ok) return guardRefusedResult(guard.rejection);

  try {
    await withCooldown(() => actions.pressKeys(keys));
    // Paste of long clipboard content = composition → arm submit gate.
    if (isPasteChord(keys) && page) {
      const chars = getLastClipboardWriteChars();
      if (chars > 0) {
        noteTyping(page, chars, page.url());
      }
    }
    const payload: PhysicalKeypressPayload = {
      ok: true,
      keys,
      durationMs: Date.now() - startedAt,
    };
    return jsonResult(payload);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      isError: true,
      content: [
        { type: 'text', text: JSON.stringify({ error: 'keypress_failed', message: msg }) },
      ],
    };
  }
}

// --- Server wiring -------------------------------------------------------

export interface ServerDeps {
  store: InterceptStore;
  statsProvider?: () => SnifferStats;
  /**
   * Optional attached page. When present, the Phase 3 physical tools
   * become usable; when absent, they return a `browser_not_attached`
   * error and only the query tool works.
   */
  page?: Page;
  /**
   * Lazy/self-healing page resolver. Production wires this to a
   * PageProvider; when set it takes priority over `page` so the browser
   * connection is established on demand and survives Chrome restarts
   * without reloading the MCP server.
   */
  getPage?: () => Promise<Page | null>;
  /**
   * Tab/navigation controller (from the PageProvider). Enables the
   * browser_navigate / list_tabs / select_tab tools. When omitted those
   * tools report browser_not_attached.
   */
  tabController?: TabController;
}

/**
 * Build a configured low-level MCP Server. Registers the tools
 * (query + physical + screenshot + tab control) against ListTools /
 * CallTool handlers.
 *
 * Kept separate from startServer() so tests can assert on the resulting
 * handler set without binding to stdio.
 */
export function createServer(deps: ServerDeps): Server {
  const statsProvider = deps.statsProvider ?? (() => ({ ...EMPTY_STATS }));
  const ctx: QueryToolContext = { statsProvider, store: deps.store };
  const physicalDeps: PhysicalToolDeps = {
    ...(deps.page !== undefined ? { page: deps.page } : {}),
    ...(deps.getPage !== undefined ? { getPage: deps.getPage } : {}),
  };
  // getPage is included so browser_navigate can clear stale write intent and
  // apply reading dwell on the page it just opened.
  const tabDeps: { controller?: TabController; getPage?: () => Promise<Page | null> } = {
    ...(deps.tabController !== undefined ? { controller: deps.tabController } : {}),
    ...(deps.getPage !== undefined ? { getPage: deps.getPage } : {}),
  };

  const server = new Server(
    { name: SERVER_NAME, version: SERVER_VERSION },
    {
      capabilities: {
        tools: {},
      },
    },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
      tools: [
        {
          name: TOOL_NAME_QUERY,
          description: TOOL_DESCRIPTION_QUERY,
          inputSchema: {
            type: 'object',
            properties: {
              url_pattern: {
                type: 'string',
                description:
                  'SQL LIKE pattern. % matches any sequence (including empty), ' +
                  '_ matches exactly one character. Not a regex. ' +
                  'Example: "%api.example.com/v1/search%"',
              },
              limit: {
                type: 'integer',
                minimum: 1,
                maximum: TOOL_MAX_LIMIT,
                default: DEFAULT_LIMIT,
                description: `Max items to return (1..${TOOL_MAX_LIMIT}, default ${DEFAULT_LIMIT}).`,
              },
              since_ts: {
                type: 'integer',
                minimum: 0,
                description:
                  'Optional millisecond-epoch cutoff. Only rows with ts >= since_ts are returned.',
              },
            },
            required: ['url_pattern'],
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_A11Y,
          description: TOOL_DESCRIPTION_A11Y,
          inputSchema: {
            type: 'object',
            properties: {
              interesting_only: {
                type: 'boolean',
                default: true,
                description: 'Reserved; current impl always filters to role/name-bearing nodes.',
              },
              max_nodes: {
                type: 'integer',
                minimum: 1,
                maximum: A11Y_MAX_NODES,
                default: A11Y_MAX_NODES,
                description: `Cap on the number of nodes returned (1..${A11Y_MAX_NODES}).`,
              },
            },
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_CLICK,
          description: TOOL_DESCRIPTION_CLICK,
          inputSchema: {
            type: 'object',
            properties: {
              x: {
                type: 'number',
                minimum: 0,
                description: 'X coordinate (CSS pixels from viewport left).',
              },
              y: {
                type: 'number',
                minimum: 0,
                description: 'Y coordinate (CSS pixels from viewport top).',
              },
            },
            required: ['x', 'y'],
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_TYPE,
          description: TOOL_DESCRIPTION_TYPE,
          inputSchema: {
            type: 'object',
            properties: {
              text: {
                type: 'string',
                minLength: 1,
                maxLength: MAX_TYPE_CHARS,
                description: 'Text to type. Newlines are mapped to Enter.',
              },
              replace: {
                type: 'boolean',
                description:
                  'Select all in the focused field before typing (Meta+A on macOS, Control+A elsewhere).',
              },
            },
            required: ['text'],
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_SCROLL,
          description: TOOL_DESCRIPTION_SCROLL,
          inputSchema: {
            type: 'object',
            properties: {
              direction: {
                type: 'string',
                enum: ['up', 'down'],
                description: 'Scroll direction.',
              },
              distance_px: {
                type: 'integer',
                minimum: 1,
                maximum: MAX_SCROLL_DISTANCE_PX,
                description: `Total scroll distance in CSS pixels (1..${MAX_SCROLL_DISTANCE_PX}).`,
              },
            },
            required: ['direction', 'distance_px'],
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_SCREENSHOT,
          description: TOOL_DESCRIPTION_SCREENSHOT,
          inputSchema: {
            type: 'object',
            properties: {
              full_page: {
                type: 'boolean',
                default: false,
                description: 'Capture the full scrollable document instead of the viewport.',
              },
              max_bytes: {
                type: 'integer',
                minimum: 1,
                maximum: 8 * 1024 * 1024,
                description:
                  'Soft cap on screenshot base64 length in bytes. Defaults to 1 MiB; PNG exceeding the cap falls back to JPEG, then truncation.',
              },
            },
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_EXTRACT_TEXT_AT,
          description: TOOL_DESCRIPTION_EXTRACT_TEXT_AT,
          inputSchema: {
            type: 'object',
            properties: {
              x: {
                type: 'number',
                minimum: 0,
                description: 'X coordinate (CSS pixels from viewport left).',
              },
              y: {
                type: 'number',
                minimum: 0,
                description: 'Y coordinate (CSS pixels from viewport top).',
              },
              max_chars: {
                type: 'integer',
                minimum: 1,
                maximum: EXTRACT_TEXT_AT_MAX_CHARS,
                description: `Max characters to return (default ${EXTRACT_TEXT_AT_MAX_CHARS}).`,
              },
            },
            required: ['x', 'y'],
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_EXTRACT_ASSISTANT_REPLY,
          description: TOOL_DESCRIPTION_EXTRACT_ASSISTANT_REPLY,
          inputSchema: {
            type: 'object',
            properties: {
              user_message: {
                type: 'string',
                description:
                  'Optional user question to strip before picking the last assistant reply group.',
              },
              max_chars: {
                type: 'integer',
                minimum: 1,
                maximum: DEFAULT_EXTRACT_MAX_CHARS,
                description: `Max characters to return (default ${DEFAULT_EXTRACT_MAX_CHARS}).`,
              },
            },
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_READ_CLIPBOARD,
          description: TOOL_DESCRIPTION_READ_CLIPBOARD,
          inputSchema: {
            type: 'object',
            properties: {},
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_WRITE_CLIPBOARD,
          description: TOOL_DESCRIPTION_WRITE_CLIPBOARD,
          inputSchema: {
            type: 'object',
            properties: {
              text: {
                type: 'string',
                minLength: 1,
                maxLength: MAX_CLIPBOARD_CHARS,
                description: 'Plain text to place on the system clipboard.',
              },
            },
            required: ['text'],
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_SET_INPUT_FILES,
          description: TOOL_DESCRIPTION_SET_INPUT_FILES,
          inputSchema: {
            type: 'object',
            properties: {
              path: {
                type: 'string',
                minLength: 1,
                description: 'Absolute path to a local file that exists on disk.',
              },
              selector: {
                type: 'string',
                minLength: 1,
                description:
                  'CSS selector for <input type="file">. Default: input[type="file"].',
              },
            },
            required: ['path'],
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_KEYPRESS,
          description: TOOL_DESCRIPTION_KEYPRESS,
          inputSchema: {
            type: 'object',
            properties: {
              keys: {
                type: 'string',
                minLength: 1,
                maxLength: 64,
                description: 'Playwright key chord, e.g. Meta+c, Control+a.',
              },
            },
            required: ['keys'],
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_NAVIGATE,
          description: TOOL_DESCRIPTION_NAVIGATE,
          inputSchema: {
            type: 'object',
            properties: {
              url: {
                type: 'string',
                description: 'Absolute URL to open (http/https).',
              },
              new_tab: {
                type: 'boolean',
                default: false,
                description: 'Open in a new tab instead of navigating the active page.',
              },
            },
            required: ['url'],
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_LIST_TABS,
          description: TOOL_DESCRIPTION_LIST_TABS,
          inputSchema: {
            type: 'object',
            properties: {},
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_SELECT_TAB,
          description: TOOL_DESCRIPTION_SELECT_TAB,
          inputSchema: {
            type: 'object',
            properties: {
              index: {
                type: 'integer',
                minimum: 0,
                description: 'Tab index from list_tabs.',
              },
            },
            required: ['index'],
            additionalProperties: false,
          },
        },
        {
          name: TOOL_NAME_CLOSE_TAB,
          description: TOOL_DESCRIPTION_CLOSE_TAB,
          inputSchema: {
            type: 'object',
            properties: {
              index: {
                type: 'integer',
                minimum: 0,
                description: 'Tab index from list_tabs.',
              },
            },
            required: ['index'],
            additionalProperties: false,
          },
        },
      ],
    };
  });

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const params = request.params;
    const name = params?.name;
    const args = params?.arguments ?? {};

    // Central observability: every tool call is bracketed with a start
    // line (name + arg summary) and an end line (ok/error + elapsed ms),
    // so a single log stream tells the whole story of a debug session.
    const startedAt = Date.now();
    logger.info(`tool → ${name ?? '(none)'}`, { args: summarizeArgs(args) });
    const result = await runTool(name, args);
    logger.info(`tool ← ${name ?? '(none)'}`, {
      isError: result.isError === true,
      ms: Date.now() - startedAt,
    });
    return result;
  });

  async function runTool(
    name: string | undefined,
    args: unknown,
  ): Promise<{ content: ToolContentBlock[]; isError?: boolean }> {
    switch (name) {
      case TOOL_NAME_QUERY:
        return await handleQueryIntercepted(args, ctx);
      case TOOL_NAME_A11Y:
        return handleGetA11yTree(args, physicalDeps);
      case TOOL_NAME_SCREENSHOT:
        return handleTakeScreenshot(args, physicalDeps);
      case TOOL_NAME_EXTRACT_TEXT_AT:
        return handleExtractTextAt(args, physicalDeps);
      case TOOL_NAME_EXTRACT_ASSISTANT_REPLY:
        return handleExtractAssistantReply(args, physicalDeps);
      case TOOL_NAME_READ_CLIPBOARD:
        return handleReadClipboard(args, physicalDeps);
      case TOOL_NAME_WRITE_CLIPBOARD:
        return handleWriteClipboard(args, physicalDeps);
      case TOOL_NAME_SET_INPUT_FILES:
        return handleSetInputFiles(args, physicalDeps);
      case TOOL_NAME_KEYPRESS:
        return handlePhysicalKeypress(args, physicalDeps);
      case TOOL_NAME_CLICK:
        return handlePhysicalClick(args, physicalDeps);
      case TOOL_NAME_TYPE:
        return handlePhysicalType(args, physicalDeps);
      case TOOL_NAME_SCROLL:
        return handlePhysicalScroll(args, physicalDeps);
      case TOOL_NAME_NAVIGATE:
        return handleNavigate(args, tabDeps);
      case TOOL_NAME_LIST_TABS:
        return handleListTabs(args, tabDeps);
      case TOOL_NAME_SELECT_TAB:
        return handleSelectTab(args, tabDeps);
      case TOOL_NAME_CLOSE_TAB:
        return handleCloseTab(args, tabDeps);
      default:
        return {
          isError: true,
          content: [
            {
              type: 'text',
              text: JSON.stringify({
                error: 'unknown_tool',
                name: name ?? null,
              }),
            },
          ],
        };
    }
  }

  // Surface server errors via the logger so they don't get swallowed.
  server.onerror = (err: Error) => {
    logger.error('MCP server error', { error: err.message });
  };

  return server;
}

/**
 * Wire a configured server to stdio transport and start it.
 * Returns the transport so the caller can await close().
 */
export async function startServer(deps: ServerDeps): Promise<{
  server: Server;
  transport: StdioServerTransport;
}> {
  const server = createServer(deps);
  const transport = new StdioServerTransport();
  await server.connect(transport);
  logger.info('MCP server listening on stdio', {
    name: SERVER_NAME,
    version: SERVER_VERSION,
    hasPage: deps.page ? true : false,
    lazyAttach: deps.getPage ? true : false,
  });
  return { server, transport };
}

// --- Re-exports for testability -----------------------------------------
// Handlers and helpers from this module that tests import directly.
// Also re-export the underlying physical helpers so consumers have a
// single import surface for the MCP package.
export { withCooldown, randomSleep, getCooldownBounds } from '../physical/cooldown.js';
export { flattenA11y, getPageAccessibilityTree } from '../percept/a11y.js';
export type { A11yNode } from '../percept/a11y.js';
export type { PhysicalCursor } from '../physical/cursor.js';
export type { ScrollDirection } from '../physical/scroll.js';
// Screenshot re-exports for direct testability.
export {
  captureScreenshotWithMeta,
  decodeImageDimensions,
  DEFAULT_MAX_SCREENSHOT_BYTES,
} from '../percept/screenshot.js';
export type { ScreenshotWithMeta } from '../percept/screenshot.js';
export {
  mergeScrollCaptures,
  pickLastMessageGroup,
  dedupeRepeatedContent,
  stripTrailingFollowUps,
  stripUiNoiseLines,
  refineAssistantReplyText,
  stripAfterUserMessage,
  extractTextAt,
  extractAssistantReply,
} from '../percept/extract-text.js';
export {
  readClipboardText,
  writeClipboardText,
  getLastClipboardWriteChars,
  MAX_CLIPBOARD_CHARS,
} from '../percept/clipboard.js';
export { setInputFiles } from '../percept/set-input-files.js';
export { pressKeys } from '../physical/keyboard.js';
