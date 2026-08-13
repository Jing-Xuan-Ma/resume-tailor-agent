/**
 * Phase 3 — Accessibility tree perception.
 *
 * README §4 "physical / cognition split":
 *   The cognition layer (the AI agent) reads the page via the A11y
 *   tree and decides WHAT to interact with. The physical layer accepts
 *   only coordinates. This module is the cognition-side adapter that
 *   produces a flat list of {role, name, x, y, width, height} nodes
 *   the agent can reason about.
 *
 * CRITICAL INVARIANT: this module MUST NEVER return a CSS/XPath
 * selector. Returning role+name+coords lets the agent hand the
 * coordinates straight to physical_click without ever touching the
 * DOM API directly.
 *
 * Implementation choice: we use `page.evaluate` to walk the DOM and
 * compute each element's accessible role/name and viewport-relative
 * bounding box. This is more accurate than `page.accessibility.snapshot()`
 * for our needs because snapshot does not expose coordinates — and
 * coordinates are a hard requirement of the Phase 3 acceptance
 * ("AI 指令能正确点中卡片").
 */

import type { Page } from 'playwright-core';

import { logger } from '../util/logger.js';

/** Wire shape of one A11y node. */
export interface A11yNode {
  role: string;
  name: string;
  /** Centre X of the element, in CSS pixels relative to viewport. */
  x: number;
  /** Centre Y of the element, in CSS pixels relative to viewport. */
  y: number;
  width: number;
  height: number;
  /** Present only for real `<a href>` anchors — the resolved absolute URL. */
  url?: string;
}

/** Caps to keep the response from blowing up the LLM context. */
export const A11Y_MAX_NODES = 200;

/**
 * The browser-side script. Has to be a plain string because it runs in
 * the page context, not Node. We keep it self-contained: no closures
 * over Node variables.
 *
 * Algorithm:
 *   1. Walk every element under document.body.
 *   2. Skip elements with zero-size bounding boxes (display:none etc).
 *   3. Skip elements that are not "visible" per getComputedStyle.
 *   4. Compute an accessible-name via the same heuristics browsers use
 *      for the ARIA accessible name: aria-label, aria-labelledby, then
 *      the element's text or value, then title.
 *   5. Compute role: explicit role attribute first, then implicit role
 *      from tag name.
 *   6. De-duplicate adjacent identical (role,name,x,y,w,h) tuples.
 *
 * Returns the raw list; Node-side code does the final slicing/capping.
 */
const COLLECT_A11Y_SCRIPT = `
() => {
  const IMPLICIT_ROLE = {
    A: 'link',
    BUTTON: 'button',
    INPUT: 'textbox',
    TEXTAREA: 'textbox',
    SELECT: 'combobox',
    IMG: 'image',
    H1: 'heading', H2: 'heading', H3: 'heading',
    H4: 'heading', H5: 'heading', H6: 'heading',
    LABEL: 'label',
    NAV: 'navigation',
    MAIN: 'main',
    ARTICLE: 'article',
    SECTION: 'region',
    UL: 'list', OL: 'list',
    LI: 'listitem',
    TABLE: 'table',
    FORM: 'form',
    FIELDSET: 'group',
    DIALOG: 'dialog',
    SUMMARY: 'button',
    DETAILS: 'group',
    CANVAS: 'canvas',
    SVG: 'image',
    VIDEO: 'video',
    AUDIO: 'audio',
  };

  // Many SPA UIs (DeepSeek included) build "buttons" out of a bare
  // <div>/<span> with a React onClick instead of a semantic <button> or
  // role="button". Those have no implicit/explicit role at all, so they
  // were previously invisible to this tree — e.g. the "9 个网页" citation
  // toggle is a plain <span>. cursor:pointer plus the element owning its
  // *own* (non-descendant) text is a standard, selector-free signal that
  // it is the clickable label itself rather than a large clickable card
  // wrapping unrelated child content — checking direct text (not
  // descendant text) is what keeps this from also flagging every
  // ancestor wrapper up the tree.
  function hasDirectText(el) {
    for (const node of el.childNodes) {
      if (node.nodeType === 3 && node.textContent && node.textContent.trim()) return true;
    }
    return false;
  }

  function computeRole(el, style) {
    const explicit = el.getAttribute('role');
    if (explicit && explicit.trim() !== '' && explicit.toLowerCase() !== 'none' && explicit.toLowerCase() !== 'presentation') {
      return explicit.toLowerCase();
    }
    const tag = el.tagName;
    const implicit = IMPLICIT_ROLE[tag];
    if (implicit) return implicit;
    if (style.cursor === 'pointer' && hasDirectText(el)) return 'button';
    return '';
  }

  function computeName(el, role) {
    // aria-labelledby wins over everything else.
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const parts = labelledby.split(/\\s+/).map(id => {
        const ref = document.getElementById(id);
        return ref ? (ref.innerText || ref.textContent || '').trim() : '';
      }).filter(Boolean);
      if (parts.length) return parts.join(' ');
    }
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();
    const alt = el.getAttribute && el.getAttribute('alt');
    if (alt && alt.trim()) return alt.trim();
    // For form controls, prefer associated <label>.
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
      const id = el.id;
      if (id) {
        const label = document.querySelector('label[for="' + CSS.escape(id) + '"]');
        if (label) {
          const t = (label.innerText || label.textContent || '').trim();
          if (t) return t;
        }
      }
      // Also <label><input>text</label>
      const parent = el.closest('label');
      if (parent) {
        const t = (parent.innerText || parent.textContent || '').trim();
        if (t) return t;
      }
      const placeholder = el.getAttribute('placeholder');
      if (placeholder && placeholder.trim()) return placeholder.trim();
      const title = el.getAttribute('title');
      if (title && title.trim()) return title.trim();
    }
    // For elements with text content.
    const text = (el.innerText || el.textContent || '').trim();
    if (text) {
      // Cap each name so we do not return 10KB of paragraph text.
      return text.length > 200 ? text.slice(0, 200) + '...' : text;
    }
    if (role === 'image') {
      const src = el.getAttribute('src');
      if (src) return src.split('/').pop() || src;
    }
    return '';
  }

  function isVisible(el, style) {
    if (style.visibility === 'hidden') return false;
    if (style.display === 'none') return false;
    if (Number(style.opacity) === 0) return false;
    if (el.getAttribute('aria-hidden') === 'true') return false;
    // Off-screen check via bounding rect (recomputed below for x/y).
    return true;
  }

  // Many chat/feed UIs (e.g. DeepSeek, Doubao) put long content inside an
  // inner element with its own overflow:auto/scroll, independent of the
  // page/window scroll. getBoundingClientRect() is NOT clipped by an
  // ancestor's overflow — it reports the element's full laid-out position
  // even when a scrolled ancestor is hiding it. Checking only against
  // window bounds therefore both (a) keeps content that scrolled out of
  // an inner container but still happens to land inside the window rect,
  // and (b) can drop large elements (e.g. <table>) whose own unclipped
  // extent exceeds the window even though the visible slice is on-screen.
  // Walk up the ancestor chain and reject the point if any clipping
  // ancestor's own box does not contain it.
  function isClippedByAncestor(el, cx, cy) {
    let node = el.parentElement;
    while (node && node !== document.documentElement) {
      const s = window.getComputedStyle(node);
      const clipsX = s.overflowX === 'hidden' || s.overflowX === 'auto' || s.overflowX === 'scroll' || s.overflowX === 'clip';
      const clipsY = s.overflowY === 'hidden' || s.overflowY === 'auto' || s.overflowY === 'scroll' || s.overflowY === 'clip';
      if (clipsX || clipsY) {
        const r = node.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) {
          if (clipsX && (cx < r.left || cx > r.right)) return true;
          if (clipsY && (cy < r.top || cy > r.bottom)) return true;
        }
      }
      node = node.parentElement;
    }
    return false;
  }

  const out = [];
  const all = document.body ? document.body.querySelectorAll('*') : document.querySelectorAll('*');
  for (const el of all) {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    const style = window.getComputedStyle(el);
    if (!isVisible(el, style)) continue;
    const role = computeRole(el, style);
    // Skip GenericContainer/none roles with no name — pure noise.
    if (!role && !el.getAttribute('aria-label') && !el.getAttribute('role')) continue;
    if (role === 'none' || role === 'presentation') continue;
    const name = computeName(el, role);
    // We require either a non-empty role or a non-empty name. Empty
    // roles+names are the "structural <div>" noise we want to drop.
    if (!role && !name) continue;
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    // Drop elements whose centre is outside the viewport entirely.
    const vw = window.innerWidth || document.documentElement.clientWidth;
    const vh = window.innerHeight || document.documentElement.clientHeight;
    if (cx < 0 || cy < 0 || cx > vw || cy > vh) continue;
    // Drop elements whose centre is outside a scrolled ancestor's own box
    // (see isClippedByAncestor for why window-bounds alone is not enough).
    if (isClippedByAncestor(el, cx, cy)) continue;
    const node = {
      role: role || 'generic',
      name: name,
      x: Math.round(cx * 100) / 100,
      y: Math.round(cy * 100) / 100,
      width: Math.round(rect.width * 100) / 100,
      height: Math.round(rect.height * 100) / 100,
    };
    // Real anchors carry a resolved absolute URL (el.href, not the raw
    // attribute) — expose it so callers can get the actual link target
    // without falling back to DOM scraping outside the physical/cognition
    // split.
    if (el.tagName === 'A' && el.href) {
      node.url = el.href;
    }
    out.push(node);
  }
  return out;
}
`;

/**
 * Browser-returned raw node (before dedup/cap). Identical shape to
 * A11yNode at runtime, kept separate only for type-clarity in helpers.
 */
type RawA11yNode = A11yNode;

/**
 * Pure post-processing: dedup adjacent identical nodes, cap to
 * A11Y_MAX_NODES. Exported so unit tests can exercise dedup/cap
 * without spawning a browser.
 */
export function flattenA11y(raw: RawA11yNode[], maxNodes: number = A11Y_MAX_NODES): A11yNode[] {
  const out: A11yNode[] = [];
  let prev: A11yNode | undefined;
  for (const node of raw) {
    // Adjacent-only dedup (cheap O(n)); deep-equal check on all fields.
    if (
      prev &&
      prev.role === node.role &&
      prev.name === node.name &&
      prev.x === node.x &&
      prev.y === node.y &&
      prev.width === node.width &&
      prev.height === node.height
    ) {
      continue;
    }
    out.push({
      role: node.role,
      name: node.name,
      x: node.x,
      y: node.y,
      width: node.width,
      height: node.height,
      ...(node.url ? { url: node.url } : {}),
    });
    prev = node;
    if (out.length >= maxNodes) break;
  }
  return out;
}

/**
 * Compute the page's A11y tree as a flat list of {role, name, x, y,
 * width, height} nodes.
 *
 * Coordinates are CSS pixels relative to the viewport's top-left, which
 * matches Playwright's `page.mouse` / ghost-cursor coordinate system —
 * the agent can pass x/y straight into physical_click.
 *
 * The returned list is bounded by A11Y_MAX_NODES to keep the LLM
 * context manageable; nodes are visited in DOM order.
 */
export async function getPageAccessibilityTree(
  page: Page,
  opts: { maxNodes?: number } = {},
): Promise<A11yNode[]> {
  const maxNodes = opts.maxNodes ?? A11Y_MAX_NODES;
  // We intentionally ignore the interesting_only flag from the spec
  // because we do our own filtering here. The flag is accepted in the
  // MCP tool input only for forward compatibility.
  // COLLECT_A11Y_SCRIPT is an arrow-function source string. Passed as-is,
  // Playwright evaluates it as an expression and returns the (non-
  // serializable) function itself -> undefined. Wrap as an IIFE so the
  // function is invoked in-page and its array result is returned.
  const raw = await page.evaluate(`(${COLLECT_A11Y_SCRIPT})()`);
  if (!Array.isArray(raw)) {
    logger.warn('A11y evaluate returned non-array', { got: typeof raw });
    return [];
  }
  return flattenA11y(raw as RawA11yNode[], maxNodes);
}
