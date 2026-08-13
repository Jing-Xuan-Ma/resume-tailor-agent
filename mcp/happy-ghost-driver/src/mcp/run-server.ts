import { ensureAppConfigLoaded } from '../config/load.js';
import { createPageProvider } from '../attach/provider.js';
import { startSniffer } from '../collect/sniffer.js';
import { startServer } from './server.js';
import { logger } from '../util/logger.js';
import {
  closeDb,
  createInterceptStoreFromEnv,
  resolveStoreBackend,
  setInterceptStore,
} from '../db/store.js';
import { closeLedger } from '../guard/ledger.js';
import type { BrowserContext } from 'playwright-core';
import type { PageProvider } from '../attach/provider.js';
import type { SnifferHandle, SnifferStats } from '../collect/sniffer.js';
import type { InterceptStore } from '../db/types.js';

const DEFAULT_CDP_ENDPOINT = 'http://127.0.0.1:9222';
const DEFAULT_URL_EXCLUDE = ['unread_count'];
/** Days of captured response bodies to keep. Override with SNIFF_RETENTION_DAYS. */
const DEFAULT_RETENTION_DAYS = 7;
const EMPTY_STATS: SnifferStats = { captured: 0, skipped: 0, errors: 0 };

interface Runtime {
  shutdown: () => Promise<void>;
}

async function main(): Promise<void> {
  ensureAppConfigLoaded();

  let store;
  try {
    store = await createInterceptStoreFromEnv();
    setInterceptStore(store);
    await purgeExpiredCaptures(store);
  } catch (err) {
    logger.error('Failed to open intercept store', {
      backend: resolveStoreBackend(),
      error: err instanceof Error ? err.message : String(err),
    });
    process.exit(3);
  }

  const cdpEndpoint =
    process.env.CDP_ENDPOINT && process.env.CDP_ENDPOINT.trim() !== ''
      ? process.env.CDP_ENDPOINT.trim()
      : DEFAULT_CDP_ENDPOINT;

  const { provider, getSniffer } = setupBrowser(cdpEndpoint);

  const { server, transport } = await startServer({
    store,
    getPage: () => provider.getPage(),
    statsProvider: () => getSniffer()?.getStats() ?? EMPTY_STATS,
    tabController: {
      navigate: (url, navOpts) => provider.navigate(url, navOpts),
      listTabs: () => provider.listTabs(),
      selectTab: (index) => provider.selectTab(index),
      closeTab: (index) => provider.closeTab(index),
    },
  });

  const runtime: Runtime = {
    shutdown: makeShutdown({ server, transport, provider, getSniffer }),
  };

  const sigHandler = (): void => {
    void runtime.shutdown().finally(() => {
      process.exit(0);
    });
  };
  process.on('SIGINT', sigHandler);
  process.on('SIGTERM', sigHandler);

  process.stdin.on('end', () => {
    logger.info('stdin EOF detected; shutting down.');
    void runtime.shutdown().finally(() => {
      process.exit(0);
    });
  });

  logger.info('ghost-driver-mcp server ready', {
    storeBackend: resolveStoreBackend(),
    cdpEndpoint,
  });
}

function setupBrowser(cdpEndpoint: string): {
  provider: PageProvider;
  getSniffer: () => SnifferHandle | null;
} {
  const sniffEnabled = shouldEnableSniffer();
  const sniffOpts = readSnifferOptions();
  let snifferHandle: SnifferHandle | null = null;

  const onContext = (ctx: BrowserContext): void => {
    try {
      snifferHandle?.stop();
    } catch {
      // previous context already gone; ignore
    }
    snifferHandle = startSniffer(ctx, sniffOpts);
    logger.info('Sniffer attached to browser context', sniffOpts);
  };

  const provider = createPageProvider({
    endpoint: cdpEndpoint,
    ...(shouldAutoLaunchChrome()
      ? { launch: { command: 'bash', args: ['scripts/launch-chrome.sh'], cwd: process.cwd() } }
      : {}),
    ...(sniffEnabled ? { onContext } : {}),
  });
  logger.info('Browser page provider ready (lazy attach)', {
    endpoint: cdpEndpoint,
    autoLaunch: shouldAutoLaunchChrome(),
    sniffer: sniffEnabled,
  });

  return { provider, getSniffer: () => snifferHandle };
}

function shouldAutoLaunchChrome(): boolean {
  const raw = process.env.AUTO_LAUNCH_CHROME;
  if (raw === undefined) return true;
  return raw !== '0' && raw.toLowerCase() !== 'false';
}

function shouldEnableSniffer(): boolean {
  const raw = process.env.ENABLE_SNIFFER;
  if (raw === undefined) return true;
  return raw !== '0' && raw.toLowerCase() !== 'false';
}

function readSnifferOptions(): {
  urlInclude?: string[];
  urlExclude?: string[];
  contentTypes?: string[];
  domainAllowlist?: string[];
} {
  const urlInclude = parseList(process.env.URL_INCLUDE);
  const urlExclude = mergeSnifferExclude(parseList(process.env.URL_EXCLUDE));
  const contentTypes = parseList(process.env.CONTENT_TYPES);
  const domainAllowlist = parseList(process.env.SNIFF_DOMAINS);
  return {
    ...(urlInclude ? { urlInclude } : {}),
    ...(urlExclude.length > 0 ? { urlExclude } : {}),
    ...(contentTypes ? { contentTypes } : {}),
    ...(domainAllowlist ? { domainAllowlist } : {}),
  };
}

function parseList(raw: string | undefined): string[] | undefined {
  if (!raw || raw.trim() === '') return undefined;
  const list = raw.split(',').map((s) => s.trim()).filter((s) => s.length > 0);
  return list.length > 0 ? list : undefined;
}

/**
 * Drop captured bodies past the retention window.
 *
 * Runs once at startup rather than on a timer: the server is started per
 * session, so startup is the natural boundary, and a background timer that
 * deletes data while the agent is querying it is a worse trade.
 * `SNIFF_RETENTION_DAYS=0` keeps everything.
 */
async function purgeExpiredCaptures(store: InterceptStore): Promise<void> {
  const raw = process.env.SNIFF_RETENTION_DAYS;
  const days = raw === undefined || raw.trim() === '' ? DEFAULT_RETENTION_DAYS : Number(raw);
  if (!Number.isFinite(days) || days <= 0) {
    logger.info('capture retention disabled; intercepted rows are kept indefinitely');
    return;
  }
  const cutoff = Date.now() - days * 86_400_000;
  try {
    const removed = await store.purgeOlderThan(cutoff);
    logger.info('capture retention applied', { days, removed });
  } catch (err) {
    logger.warn('capture retention purge failed', {
      error: err instanceof Error ? err.message : String(err),
    });
  }
}

function mergeSnifferExclude(envExclude: string[] | undefined): string[] {
  const merged = [...DEFAULT_URL_EXCLUDE, ...(envExclude ?? [])];
  return [...new Set(merged)];
}

interface ShutdownDeps {
  server: Awaited<ReturnType<typeof startServer>>['server'];
  transport: Awaited<ReturnType<typeof startServer>>['transport'];
  provider: PageProvider;
  getSniffer: () => SnifferHandle | null;
}

async function safely(label: string, fn: () => unknown): Promise<void> {
  try {
    await fn();
  } catch (err) {
    logger.warn(`${label} failed`, {
      error: err instanceof Error ? err.message : String(err),
    });
  }
}

function makeShutdown(deps: ShutdownDeps): () => Promise<void> {
  let called = false;
  return async () => {
    if (called) return;
    called = true;
    logger.info('Shutting down MCP server...');
    await safely('sniffer stop', () => {
      const sniffer = deps.getSniffer();
      if (sniffer) {
        logger.info('final sniffer stats', sniffer.getStats());
        sniffer.stop();
      }
    });
    await safely('server.close', () => deps.server.close());
    await safely('transport.close', () => deps.transport.close());
    await safely('provider.dispose', () => deps.provider.dispose());
    await safely('closeLedger', () => closeLedger());
    await safely('closeDb', () => closeDb());
  };
}

main().catch((err: unknown) => {
  logger.error('ghost-driver-mcp fatal', {
    error: err instanceof Error ? err.message : String(err),
  });
  void closeDb().finally(() => {
    process.exit(1);
  });
});
