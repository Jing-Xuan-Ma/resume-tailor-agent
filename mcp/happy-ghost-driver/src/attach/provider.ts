import { spawn } from 'node:child_process';

import { chromium } from 'playwright-core';
import type { Browser, BrowserContext, Page } from 'playwright-core';

import { logger } from '../util/logger.js';
import { applyStealth, stealthEnabled, verifyStealth } from '../physical/stealth.js';
import { resolveProfileDir } from '../config/paths.js';

/**
 * Lazy, self-healing CDP page provider.
 *
 * Unlike attachBrowser() (one-shot, fail-fast), this resolves a live Page
 * on demand and transparently recovers from the four states that make
 * the MCP feel "broken" to a user:
 *   1. Chrome not running yet  -> optionally auto-launch, then connect.
 *   2. Chrome up but no tab     -> create a blank page instead of erroring.
 *   3. Chrome was closed/reopened after attach -> drop stale handles and
 *      re-attach on the next call (driven by the 'disconnected' event).
 *   4. Chrome alive but wedged (CDP connects, yet every navigation times
 *      out because renderers stopped making progress) -> force-kill the
 *      automation Chrome and relaunch it (wedge watchdog; only armed when
 *      we own the launch spec, so a user-managed Chrome is never killed).
 *
 * The goal: once configured, the user never has to manually reload the
 * MCP server to recover the browser connection.
 */
export interface LaunchSpec {
  command: string;
  args: string[];
  cwd?: string;
}

export interface PageProviderOptions {
  endpoint: string;
  /** When set, auto-launch Chrome via this command if the first connect fails. */
  launch?: LaunchSpec;
  /** Max ms to wait for CDP to accept a connection after launching. */
  launchWaitMs?: number;
  /**
   * Called once each time a fresh BrowserContext is established (initial
   * connect and every reconnect after a Chrome restart). Lets the caller
   * attach a context-level sniffer that survives tab churn.
   */
  onContext?: (ctx: BrowserContext) => void;
}

/** Lightweight description of an open tab for the agent to choose from. */
export interface TabInfo {
  index: number;
  url: string;
  title: string;
  /** True for the tab the provider currently operates on. */
  active: boolean;
  /** True if the tab is the foreground/visible one in its window. */
  visible: boolean;
}

export interface NavigateResult {
  ok: true;
  url: string;
  title: string;
}

export interface PageProvider {
  /** Resolve a usable page, attaching/launching/re-attaching as needed. Null on failure. */
  getPage(): Promise<Page | null>;
  /** List open content tabs (http/https), newest last. */
  listTabs(): Promise<TabInfo[]>;
  /** Make the tab at `index` (from listTabs) the active page; brings it to front. */
  selectTab(index: number): Promise<NavigateResult | null>;
  /**
   * Close the tab at `index` (from listTabs). If it was the active page,
   * a new active page is picked the same way getPage() would (foreground
   * tab, else newest content tab, else a fresh blank page).
   * Refuses to close the last remaining page (`ok: false, reason: 'last_tab'`):
   * closing it would take the whole Chrome window/process down and break
   * the "browser stays resident" contract.
   */
  closeTab(index: number): Promise<CloseTabResult | null>;
  /** Navigate the active page (or a new tab) to `url`; the target becomes active. */
  navigate(url: string, opts?: { newTab?: boolean }): Promise<NavigateResult | null>;
  /** Drop our CDP session without killing the user's Chrome. */
  dispose(): Promise<void>;
}

export type CloseTabResult =
  | { ok: true; closedUrl: string }
  | { ok: false; reason: 'last_tab'; url: string };

/** Must cover launch-chrome.sh CDP_WAIT_SECS (default 15s) + a little slack. */
const DEFAULT_LAUNCH_WAIT_MS = 18_000;
const CONNECT_RETRY_DELAY_MS = 400;
const VISIBILITY_PROBE_TIMEOUT_MS = 1500;
const NAVIGATE_TIMEOUT_MS = 30_000;
/** Consecutive navigate timeouts before the browser is declared wedged. */
const WEDGE_GOTO_TIMEOUT_THRESHOLD = 2;
/** Max ms to wait for the CDP port to free after asking Chrome to die. */
const WEDGE_KILL_WAIT_MS = 8_000;

/**
 * pkill target for the wedge fallback: the exact --user-data-dir flag that
 * scripts/launch-chrome.sh passes. Matching the full flag (not just the
 * directory name) keeps the kill scoped to our own Chrome even though the
 * profile now lives under $HOME alongside other tooling.
 */
function chromeProfilePattern(): string {
  return `--user-data-dir=${resolveProfileDir()}`;
}

export function createPageProvider(opts: PageProviderOptions): PageProvider {
  let browser: Browser | null = null;
  let context: BrowserContext | null = null;
  let page: Page | null = null;
  // True while the active page was chosen explicitly (selectTab / navigate);
  // honored over foreground-following so the agent's choice is stable.
  let explicit = false;
  let inFlight: Promise<Page | null> | null = null;
  let launchAttempted = false;
  let consecutiveGotoTimeouts = 0;
  let restarting: Promise<boolean> | null = null;
  // One fingerprint self-check per process; it is diagnostic, not a gate.
  let fingerprintVerified = false;

  function clearCache(reason: string): void {
    if (browser || page) {
      logger.warn('PageProvider: dropping stale browser handles', { reason });
    }
    browser = null;
    context = null;
    page = null;
    explicit = false;
    // Chrome died / we dropped the session — allow auto-launch on the next call.
    // Without this, a single failed launch (or mid-session crash) permanently
    // blocks relaunch until the MCP process is restarted (launchAttempted trap).
    if (
      reason.includes('disconnect') ||
      reason.includes('wedge') ||
      reason.includes('dispose')
    ) {
      launchAttempted = false;
    }
  }

  function pageIsLive(p: Page | null): p is Page {
    return !!p && !p.isClosed() && !!browser && browser.isConnected();
  }

  async function connectOnce(): Promise<Browser> {
    const b = await chromium.connectOverCDP(opts.endpoint);
    b.on('disconnected', () => clearCache('cdp disconnected'));
    return b;
  }

  async function connectWithLaunch(): Promise<Browser | null> {
    try {
      return await connectOnce();
    } catch (err) {
      logger.info('PageProvider: initial CDP connect failed', {
        endpoint: opts.endpoint,
        error: err instanceof Error ? err.message : String(err),
      });
    }

    if (!opts.launch) return null;
    if (launchAttempted) {
      // Previous launch in this process may have left a live Chrome that we
      // simply failed to attach to once; try connect again before giving up.
      try {
        return await connectOnce();
      } catch {
        logger.warn('PageProvider: CDP still down after prior launchAttempted; will not re-spawn this call', {
          endpoint: opts.endpoint,
          hint: 'If Chrome was killed, next disconnect/clearCache re-arms auto-launch; or restart MCP.',
        });
        return null;
      }
    }

    launchAttempted = true;
    logger.info('PageProvider: auto-launching Chrome', {
      command: `${opts.launch.command} ${opts.launch.args.join(' ')}`,
    });
    try {
      // Detached so the launcher outlives brief spawn teardown; launch-chrome.sh
      // itself waits for CDP before exiting (macOS uses open -na).
      const child = spawn(opts.launch.command, opts.launch.args, {
        cwd: opts.launch.cwd ?? process.cwd(),
        detached: true,
        stdio: 'ignore',
      });
      child.unref();
    } catch (err) {
      launchAttempted = false; // spawn itself failed — allow immediate retry
      logger.error('PageProvider: failed to spawn Chrome launcher', {
        error: err instanceof Error ? err.message : String(err),
      });
      return null;
    }

    const deadline = Date.now() + (opts.launchWaitMs ?? DEFAULT_LAUNCH_WAIT_MS);
    while (Date.now() < deadline) {
      await sleep(CONNECT_RETRY_DELAY_MS);
      try {
        return await connectOnce();
      } catch {
        // keep polling until the deadline
      }
    }
    // Launch did not yield a reachable CDP — re-arm so the next tool call
    // can try again (e.g. after fixing a profile lock) without restarting MCP.
    launchAttempted = false;
    logger.error('PageProvider: Chrome did not become reachable after launch', {
      endpoint: opts.endpoint,
    });
    return null;
  }

  /** True when the CDP endpoint still accepts TCP/HTTP connections. */
  async function cdpReachable(): Promise<boolean> {
    try {
      const res = await fetch(`${opts.endpoint}/json/version`, {
        signal: AbortSignal.timeout(2000),
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  /** Poll until the CDP port frees; escalate to pkill by profile marker once. */
  async function waitForBrowserDeath(): Promise<void> {
    const deadline = Date.now() + WEDGE_KILL_WAIT_MS;
    let killedViaSignal = false;
    while (Date.now() < deadline && (await cdpReachable())) {
      if (!killedViaSignal) {
        killedViaSignal = true;
        try {
          const killer = spawn('pkill', ['-f', chromeProfilePattern()], { stdio: 'ignore' });
          killer.unref();
        } catch (err) {
          logger.warn('PageProvider: pkill fallback failed to spawn', {
            error: err instanceof Error ? err.message : String(err),
          });
        }
      }
      await sleep(CONNECT_RETRY_DELAY_MS);
    }
  }

  /**
   * Wedge watchdog: kill and relaunch the automation Chrome after
   * WEDGE_GOTO_TIMEOUT_THRESHOLD consecutive navigation timeouts.
   *
   * Only armed when we own the launch spec — killing a Chrome the user
   * started themselves would be destructive, so without `opts.launch`
   * this never fires and navigate() keeps its old warn-and-continue
   * behavior.
   *
   * Kill strategy, gentlest first:
   *   1. CDP `Browser.close` — clean shutdown even when renderers hang,
   *      as long as the browser process itself still answers.
   *   2. `pkill -f --user-data-dir=<profile>` — the launch script pins a
   *      dedicated user-data-dir, so the pattern only ever matches ours.
   */
  async function forceRestartBrowser(): Promise<boolean> {
    if (restarting) return restarting;
    restarting = (async () => {
      logger.error('PageProvider: browser wedged; forcing Chrome restart', {
        consecutiveGotoTimeouts,
      });
      const b = browser;
      clearCache('wedge watchdog restart');
      if (b) {
        try {
          const session = await b.newBrowserCDPSession();
          await session.send('Browser.close');
        } catch {
          // Browser process unresponsive over CDP; fall through to pkill.
        }
        await b.close().catch(() => {});
      }

      await waitForBrowserDeath();
      if (await cdpReachable()) {
        logger.error('PageProvider: wedged Chrome refused to die; giving up this cycle');
        return false;
      }

      consecutiveGotoTimeouts = 0;
      launchAttempted = false; // re-arm auto-launch for the next connect
      logger.info('PageProvider: wedged Chrome stopped; relaunching');
      return (await ensureContext()) !== null;
    })().finally(() => {
      restarting = null;
    });
    return restarting;
  }

  /** Content tabs only: real http/https documents, in creation order. */
  function contentPages(ctx: BrowserContext): Page[] {
    return ctx.pages().filter((p) => !p.isClosed() && /^https?:\/\//i.test(p.url()));
  }

  /**
   * Playwright enables focus emulation on every page it attaches to, so that
   * background tabs keep behaving as if active. That is convenient for test
   * automation and wrong for us: it makes `document.hasFocus()` return true
   * for every tab, so nothing can tell which one the operator is actually
   * looking at — and acting on a tab nobody is looking at is precisely the
   * pattern the foreground guard exists to prevent.
   *
   * Turning it off restores a truthful `hasFocus()` (verified: it tracks
   * bringToFront exactly). Note that `visibilityState` stays 'visible' either
   * way under CDP, which is why src/guard/foreground.ts treats hasFocus as the
   * authoritative signal rather than visibilityState.
   */
  async function disableFocusEmulation(ctx: BrowserContext, p: Page): Promise<void> {
    try {
      const session = await ctx.newCDPSession(p);
      await session.send('Emulation.setFocusEmulationEnabled', { enabled: false });
    } catch (err) {
      logger.warn('PageProvider: could not disable focus emulation', {
        url: p.url(),
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  /** Probe document.visibilityState with a hard timeout so a heavy/hung page can't block us. */
  async function isVisible(p: Page): Promise<boolean> {
    try {
      // String form avoids needing the DOM lib in tsconfig (same pattern as a11y.ts).
      const probe = p.evaluate("document.visibilityState === 'visible'") as Promise<boolean>;
      const timeout = new Promise<boolean>((res) => setTimeout(() => res(false), VISIBILITY_PROBE_TIMEOUT_MS));
      return await Promise.race([probe, timeout]);
    } catch {
      return false;
    }
  }

  /**
   * Pick the best tab to operate on, preferring the foreground/visible
   * one, then the newest content page, then any open page, finally a new
   * blank tab. This is what makes "agent opened a new tab" Just Work:
   * the visible tab wins over a stale background one.
   */
  async function pickBest(ctx: BrowserContext): Promise<Page> {
    const pages = contentPages(ctx);
    logger.info('PageProvider: choosing among open tabs', {
      count: pages.length,
      urls: pages.map((p) => p.url()),
    });
    for (const p of pages) {
      if (await isVisible(p)) return p;
    }
    const lastContent = pages.at(-1);
    if (lastContent) return lastContent;
    const anyOpen = ctx.pages().filter((p) => !p.isClosed());
    const lastOpen = anyOpen.at(-1);
    if (lastOpen) return lastOpen;
    logger.info('PageProvider: no open tab; creating a blank page');
    return ctx.newPage();
  }

  /** Ensure we have a connected browser + context, launching Chrome if allowed. */
  async function ensureContext(): Promise<BrowserContext | null> {
    if (context && browser?.isConnected()) return context;
    const b = await connectWithLaunch();
    if (!b) return null;
    const ctx = b.contexts()[0];
    if (!ctx) {
      logger.error('PageProvider: no browser context after connect');
      await b.close().catch(() => {});
      return null;
    }
    browser = b;
    context = ctx;
    // Applied to current and future tabs, so the foreground guard has a real
    // signal to work with no matter how a tab came into existence.
    ctx.on('page', (p) => {
      void disableFocusEmulation(ctx, p);
    });
    for (const p of ctx.pages()) {
      void disableFocusEmulation(ctx, p);
    }
    // Stealth is opt-in and off by default: a CDP-attached Chrome that was
    // not launched with --enable-automation already reports
    // navigator.webdriver === false, so the patches are redundant, and the
    // non-native getters they leave behind are themselves detectable.
    if (stealthEnabled()) {
      try {
        applyStealth(ctx);
      } catch (err) {
        logger.warn('PageProvider: stealth injection failed', {
          error: err instanceof Error ? err.message : String(err),
        });
      }
    }
    try {
      opts.onContext?.(ctx);
    } catch (err) {
      logger.warn('PageProvider: onContext hook threw', {
        error: err instanceof Error ? err.message : String(err),
      });
    }
    return ctx;
  }

  async function getPage(): Promise<Page | null> {
    // Honor an explicit agent selection while it stays live.
    if (explicit && pageIsLive(page)) return page;

    // A live auto-picked page is reused unless it has fallen to the
    // background while another tab is visible (follow the foreground).
    if (pageIsLive(page)) {
      if (!context) return page;
      if (await isVisible(page)) return page;
      for (const candidate of contentPages(context)) {
        if (candidate !== page && (await isVisible(candidate))) {
          logger.info('PageProvider: following foreground tab', { url: candidate.url() });
          page = candidate;
          return page;
        }
      }
      return page;
    }

    if (inFlight) return inFlight;
    inFlight = (async () => {
      try {
        const ctx = await ensureContext();
        if (!ctx) return null;
        const p = await pickBest(ctx);
        page = p;
        explicit = false;
        logger.info('PageProvider: page attached', { url: p.url() });
        // Report what the page actually exposes, once per attach. Injection
        // can fail silently (addInitScript never throws on a bad script), so
        // "we called applyStealth" is not evidence that anything changed.
        if (!fingerprintVerified) {
          fingerprintVerified = true;
          void verifyStealth(p);
        }
        return p;
      } catch (err) {
        logger.error('PageProvider: attach failed', {
          error: err instanceof Error ? err.message : String(err),
        });
        clearCache('attach threw');
        return null;
      } finally {
        inFlight = null;
      }
    })();
    return inFlight;
  }

  async function describe(p: Page): Promise<NavigateResult> {
    let title = '';
    try {
      title = await Promise.race([
        p.title(),
        new Promise<string>((res) => setTimeout(() => res(''), VISIBILITY_PROBE_TIMEOUT_MS)),
      ]);
    } catch {
      title = '';
    }
    return { ok: true, url: p.url(), title };
  }

  async function listTabs(): Promise<TabInfo[]> {
    const ctx = await ensureContext();
    if (!ctx) return [];
    const pages = contentPages(ctx);
    const out: TabInfo[] = [];
    for (let i = 0; i < pages.length; i++) {
      const p = pages[i]!;
      let title = '';
      try {
        title = await Promise.race([
          p.title(),
          new Promise<string>((res) => setTimeout(() => res(''), VISIBILITY_PROBE_TIMEOUT_MS)),
        ]);
      } catch {
        title = '';
      }
      out.push({
        index: i,
        url: p.url(),
        title,
        active: p === page,
        visible: await isVisible(p),
      });
    }
    return out;
  }

  async function selectTab(index: number): Promise<NavigateResult | null> {
    const ctx = await ensureContext();
    if (!ctx) return null;
    const pages = contentPages(ctx);
    const target = pages[index];
    if (!target) {
      logger.warn('PageProvider: selectTab index out of range', { index, count: pages.length });
      return null;
    }
    await target.bringToFront().catch(() => {});
    page = target;
    explicit = true;
    logger.info('PageProvider: tab selected', { index, url: target.url() });
    return describe(target);
  }

  async function closeTab(index: number): Promise<CloseTabResult | null> {
    const ctx = await ensureContext();
    if (!ctx) return null;
    const pages = contentPages(ctx);
    const target = pages[index];
    if (!target) {
      logger.warn('PageProvider: closeTab index out of range', { index, count: pages.length });
      return null;
    }
    // Last-page guard: count every live page in the context (not just
    // http/https content tabs — a chrome://newtab etc. also keeps the
    // window alive). If nothing else remains, closing this tab would close
    // the Chrome window/process, so keep it and tell the caller why.
    const otherLivePages = ctx.pages().filter((p) => p !== target && !p.isClosed());
    if (otherLivePages.length === 0) {
      logger.info('PageProvider: refusing to close the last remaining tab', {
        index,
        url: target.url(),
      });
      return { ok: false, reason: 'last_tab', url: target.url() };
    }
    const closedUrl = target.url();
    const wasActive = target === page;
    await target.close().catch(() => {});
    if (wasActive) {
      // Mirror getPage()'s own selection policy instead of duplicating it:
      // drop the stale handle and let the next getPage() pick a fresh one.
      page = null;
      explicit = false;
    }
    logger.info('PageProvider: tab closed', { index, url: closedUrl, wasActive });
    return { ok: true, closedUrl };
  }

  /** Adopt `target` as the active page and report the result. */
  function finishNavigate(target: Page, label: string): Promise<NavigateResult> {
    page = target;
    explicit = true;
    logger.info(label, { url: target.url() });
    return describe(target);
  }

  /**
   * A goto timed out. When it crosses the wedge threshold (and we own the
   * launch), restart Chrome and retry once on a fresh tab.
   * Returns undefined when the watchdog did not engage (caller continues
   * with the original page); otherwise the final navigate outcome.
   */
  async function handleGotoTimeout(url: string): Promise<NavigateResult | null | undefined> {
    if (!opts.launch) return undefined;
    consecutiveGotoTimeouts += 1;
    if (consecutiveGotoTimeouts < WEDGE_GOTO_TIMEOUT_THRESHOLD) return undefined;

    if (!(await forceRestartBrowser())) return null;
    const ctx = await ensureContext();
    if (!ctx) return null;
    // Old page handle died with the browser; retry once on a fresh tab.
    const retryPage = await ctx.newPage();
    try {
      await retryPage.goto(url, { waitUntil: 'domcontentloaded', timeout: NAVIGATE_TIMEOUT_MS });
      consecutiveGotoTimeouts = 0;
    } catch (retryErr) {
      logger.warn('PageProvider: post-restart retry also failed', {
        url,
        error: retryErr instanceof Error ? retryErr.message : String(retryErr),
      });
    }
    await retryPage.bringToFront().catch(() => {});
    return finishNavigate(retryPage, 'PageProvider: navigated (after wedge restart)');
  }

  async function navigate(url: string, navOpts?: { newTab?: boolean }): Promise<NavigateResult | null> {
    const ctx = await ensureContext();
    if (!ctx) return null;
    let target: Page | null;
    if (navOpts?.newTab) {
      target = await ctx.newPage();
    } else {
      target = await getPage();
    }
    if (!target) return null;
    try {
      await target.goto(url, { waitUntil: 'domcontentloaded', timeout: NAVIGATE_TIMEOUT_MS });
      consecutiveGotoTimeouts = 0;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      logger.warn('PageProvider: navigate goto failed (continuing)', { url, error: msg });
      if (/Timeout \d+ms exceeded/i.test(msg)) {
        const outcome = await handleGotoTimeout(url);
        if (outcome !== undefined) return outcome;
      }
    }
    await target.bringToFront().catch(() => {});
    return finishNavigate(target, 'PageProvider: navigated');
  }

  async function dispose(): Promise<void> {
    const b = browser;
    clearCache('dispose');
    if (b) {
      await b.close().catch(() => {});
    }
  }

  return { getPage, listTabs, selectTab, closeTab, navigate, dispose };
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
