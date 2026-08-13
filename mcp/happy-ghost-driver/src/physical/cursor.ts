/**
 * Phase 3 — Physical cursor backed by ghost-cursor.
 *
 * Design contract (README §4 "physical / cognition split"):
 *   The physical layer NEVER accepts a CSS/XPath selector. It only
 *   accepts raw screen coordinates. The AI agent (cognition layer)
 *   resolves "what to click" via the accessibility tree and passes
 *   pixel coordinates here.
 *
 * ghost-cursor 1.4.x emits a GhostCursor whose coordinate-mode API is
 *   `moveTo({x,y}, opts?)` (NOT `move(selector)`), followed by
 *   `mouseDown()` / `mouseUp()`. We use those.
 *
 * ghost-cursor's typings target puppeteer's Page. Playwright's Page is
 *   duck-compatible for the methods ghost-cursor touches (CDP session,
 *   mouse, viewport). We bridge via `unknown` so the cast is explicit
 *   and type-checker-verified — no `as any`, no `@ts-ignore`.
 */

import type { Page } from 'playwright-core';
// ghost-cursor ships its own .d.ts. The library's main export is a CJS
// module; NodeNext + esModuleInterop lets us import it as a namespace.
import { createCursor } from 'ghost-cursor';

import { logger } from '../util/logger.js';
import { gaussianInt } from './rand.js';

/** Public surface every handler depends on. */
export interface PhysicalCursor {
  /** Move the cursor to (x, y) via bezier path and dispatch a click. */
  click(x: number, y: number): Promise<void>;
  /** Move the cursor to (x, y) without clicking. */
  move(x: number, y: number): Promise<void>;
}

/** ghost-cursor's GhostCursor is what backs us at runtime. */
type GhostCursorLike = ReturnType<typeof createCursor>;

/**
 * Cast a Playwright page to whatever ghost-cursor wants without `as any`.
 * Two-step (page -> unknown -> GhostCursorLike-ish) makes the assertion
 * auditable.
 */
function asGhostPage(page: Page): unknown {
  return page as unknown;
}

function assertFiniteCoord(name: string, v: number): void {
  if (!Number.isFinite(v)) {
    throw new Error(`physical_cursor: ${name} must be a finite number, got ${v}`);
  }
  if (v < 0) {
    throw new Error(`physical_cursor: ${name} must be >= 0, got ${v}`);
  }
}

/**
 * Build a PhysicalCursor that drives ghost-cursor's bezier-curve mouse.
 *
 * Coordinates are CSS pixels relative to the viewport's top-left corner
 * (same coordinate system Playwright's `page.mouse` uses).
 *
 * The click sequence is: bezier move → hover dwell (200-800ms) → mousedown
 * → press delay (50-150ms) → mouseup. The hover dwell mimics the natural
 * pause a human makes between moving to a target and pressing the button.
 * The press delay is the realistic "button travel time" that bot detectors
 * look for.
 */
export function createPhysicalCursor(page: Page): PhysicalCursor {
  // ghost-cursor expects a puppeteer-shaped page; we hand it our
  // playwright page cast through `unknown`. The runtime surface it uses
  // (CDP, mouse, viewport) is the same on both.
  const cursor: GhostCursorLike = createCursor(asGhostPage(page) as never, { x: 0, y: 0 });

  // ghost-cursor dispatches input via getCDPClient(page) = page._client(),
  // a Puppeteer-only handle. Playwright pages don't expose it, so we
  // attach a real Playwright CDP session (whose .send() speaks raw CDP —
  // the same protocol) plus a browser() shim used by ghost-cursor's
  // error-recovery branch. Created lazily so construction stays sync.
  let cdpReady: Promise<void> | null = null;
  function ensureCdp(): Promise<void> {
    if (!cdpReady) {
      cdpReady = (async () => {
        const session = await page.context().newCDPSession(page);
        const shim = page as unknown as {
          _client?: () => unknown;
          browser?: () => unknown;
        };
        shim._client = () => session;
        shim.browser = () => page.context().browser();
      })();
    }
    return cdpReady;
  }

  return {
    async click(x: number, y: number): Promise<void> {
      assertFiniteCoord('x', x);
      assertFiniteCoord('y', y);
      try {
        await ensureCdp();
        await cursor.moveTo({ x, y });
        // ghost-cursor dispatches via raw CDP, bypassing Playwright's own
        // Mouse state tracking. Sync it here (same coords -> no visible
        // jump) so a later page.mouse.wheel() (physical_scroll) fires at
        // this position instead of Playwright's stale default (0, 0).
        await page.mouse.move(x, y);
        // Hover dwell: human pause between arriving at target and pressing.
        const dwellMs = gaussianInt(200, 800);
        await new Promise((r) => setTimeout(r, dwellMs));
        await cursor.mouseDown();
        // Press delay: realistic "button travel time".
        const pressDelay = gaussianInt(50, 150);
        await new Promise((r) => setTimeout(r, pressDelay));
        await cursor.mouseUp();
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        throw new Error(
          `physical_cursor.click(${x}, ${y}) failed: ${msg}`,
        );
      }
    },

    async move(x: number, y: number): Promise<void> {
      assertFiniteCoord('x', x);
      assertFiniteCoord('y', y);
      try {
        await ensureCdp();
        await cursor.moveTo({ x, y });
        // See click() above: keep Playwright's Mouse state in sync so
        // page.mouse.wheel() (physical_scroll) targets the right spot.
        await page.mouse.move(x, y);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        throw new Error(
          `physical_cursor.move(${x}, ${y}) failed: ${msg}`,
        );
      }
    },
  };
}

/**
 * Module-level helper for ad-hoc / debug usage. Most callers should
 * hold a PhysicalCursor instance instead; this is just for tooling that
 * wants a one-shot cursor without managing lifecycle.
 */
export function physicalClick(page: Page, x: number, y: number): Promise<void> {
  logger.warn('physicalClick(page,...) is a one-shot helper; prefer createPhysicalCursor.');
  return createPhysicalCursor(page).click(x, y);
}
