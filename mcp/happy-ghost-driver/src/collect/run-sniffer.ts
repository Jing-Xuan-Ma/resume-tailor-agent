import type { Browser } from 'playwright-core';

import { attachBrowser } from '../attach/cdp.js';
import { startSniffer } from './sniffer.js';
import type { SnifferHandle } from './sniffer.js';
import {
  closeDb,
  createInterceptStoreFromEnv,
  resolveStoreBackend,
  setInterceptStore,
} from '../db/store.js';
import { logger } from '../util/logger.js';

const CDP_ENDPOINT = process.env.CDP_ENDPOINT ?? 'http://localhost:9222';
const DEFAULT_URL_EXCLUDE = ['unread_count'];

const URL_INCLUDE = parseList(process.env.URL_INCLUDE);
const URL_EXCLUDE = mergeExclude(parseList(process.env.URL_EXCLUDE));
const CONTENT_TYPES = parseList(process.env.CONTENT_TYPES) ?? ['application/json'];
const STATS_INTERVAL_MS = 10_000;

function parseList(env: string | undefined): string[] | null {
  if (!env || env.trim() === '') return null;
  return env
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function mergeExclude(envExclude: string[] | null): string[] {
  const merged = [...DEFAULT_URL_EXCLUDE, ...(envExclude ?? [])];
  return [...new Set(merged)];
}

interface Runtime {
  sniffer: SnifferHandle;
  browser: Browser;
  statsTimer: NodeJS.Timeout;
}

async function main(): Promise<void> {
  logger.info('Ghost-Driver sniffer starting', {
    endpoint: CDP_ENDPOINT,
    storeBackend: resolveStoreBackend(),
    urlInclude: URL_INCLUDE ?? '(all)',
    urlExclude: URL_EXCLUDE.length > 0 ? URL_EXCLUDE : '(none)',
    contentTypes: CONTENT_TYPES,
  });

  const store = await createInterceptStoreFromEnv();
  setInterceptStore(store);

  const { browser, page } = await attachBrowser(CDP_ENDPOINT);

  const sniffer = startSniffer(page, {
    urlInclude: URL_INCLUDE ?? undefined,
    urlExclude: URL_EXCLUDE.length > 0 ? URL_EXCLUDE : undefined,
    contentTypes: CONTENT_TYPES,
    store,
  });

  const statsTimer = setInterval(() => {
    logger.info('sniffer stats', sniffer.getStats());
  }, STATS_INTERVAL_MS);

  const runtime: Runtime = { sniffer, browser, statsTimer };
  const shutdown = makeShutdown(runtime);
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);

  logger.info('Sniffer attached. Operate Chrome manually; Ctrl+C to stop.');
}

function makeShutdown(runtime: Runtime): () => void {
  let called = false;
  return () => {
    if (called) return;
    called = true;
    logger.info('Shutting down...');
    clearInterval(runtime.statsTimer);
    logger.info('final stats', runtime.sniffer.getStats());
    runtime.sniffer.stop();
    try {
      runtime.browser.close().catch((err: unknown) => {
        logger.warn('browser.close failed', {
          error: err instanceof Error ? err.message : String(err),
        });
      });
    } catch (err) {
      logger.warn('browser.close threw', {
        error: err instanceof Error ? err.message : String(err),
      });
    }
    void closeDb()
      .catch((err: unknown) => {
        logger.error('closeDb failed', {
          error: err instanceof Error ? err.message : String(err),
        });
      })
      .finally(() => {
        setImmediate(() => process.exit(0));
      });
  };
}

main().catch((err: unknown) => {
  logger.error('sniffer fatal', {
    error: err instanceof Error ? err.message : String(err),
  });
  void closeDb().finally(() => {
    process.exit(1);
  });
});
