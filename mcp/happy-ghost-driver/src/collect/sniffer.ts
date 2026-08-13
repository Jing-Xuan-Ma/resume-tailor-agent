import type { BrowserContext, Page, Response } from 'playwright-core';

import { getInterceptStore } from '../db/store.js';
import type { InterceptStore } from '../db/types.js';
import { logger } from '../util/logger.js';

const DEFAULT_MAX_BODY_BYTES = 5 * 1024 * 1024;
const DEFAULT_CONTENT_TYPES = ['application/json'];

/**
 * Anything we can subscribe to `'response'` on. Both Playwright `Page`
 * and `BrowserContext` satisfy this; binding at the context level lets a
 * single sniffer capture traffic across ALL tabs (and new ones), which is
 * what the MCP server wants for a persistent multi-tab browser.
 */
export type ResponseSource = Page | BrowserContext;

export interface SnifferOptions {
  urlInclude?: string[];
  urlExclude?: string[];
  maxBodyBytes?: number;
  contentTypes?: string[];
  /**
   * Hostname suffixes allowed to be captured. When set, a response is stored
   * only if its host matches one of them.
   *
   * This exists because the sniffer runs at browser-context level: without a
   * scope it silently persists the JSON of every logged-in API the browser
   * touches — mail, banking, work tools — in plaintext, none of which the
   * operator asked to collect. Capture should be as narrow as the task.
   */
  domainAllowlist?: string[];
  /** When omitted, uses the process-wide intercept store from store.ts. */
  store?: InterceptStore;
}

/** True when `host` is exactly `suffix` or a subdomain of it. */
function hostMatches(host: string, suffix: string): boolean {
  const h = host.toLowerCase();
  const s = suffix.toLowerCase().replace(/^\./, '');
  return h === s || h.endsWith(`.${s}`);
}

export interface SnifferStats {
  captured: number;
  skipped: number;
  errors: number;
}

export interface SnifferHandle {
  stop(): void;
  getStats(): SnifferStats;
}

function normalizeContentType(raw: string | undefined): string {
  // e.g. "application/json; charset=utf-8" -> "application/json"
  if (!raw) return '';
  const semi = raw.indexOf(';');
  const base = semi >= 0 ? raw.slice(0, semi) : raw;
  return base.trim().toLowerCase();
}

export function startSniffer(
  source: ResponseSource,
  opts: SnifferOptions = {},
): SnifferHandle {
  const urlInclude = opts.urlInclude ?? null;
  const urlExclude = opts.urlExclude ?? null;
  const maxBodyBytes = opts.maxBodyBytes ?? DEFAULT_MAX_BODY_BYTES;
  const contentTypes = (opts.contentTypes ?? DEFAULT_CONTENT_TYPES)
    .map((c) => normalizeContentType(c))
    .filter((c) => c.length > 0);
  const contentTypeSet = new Set(contentTypes);
  const domainAllowlist =
    opts.domainAllowlist && opts.domainAllowlist.length > 0 ? opts.domainAllowlist : null;
  const store = opts.store ?? getInterceptStore();

  if (!domainAllowlist) {
    logger.warn(
      'sniffer: no domain allowlist — every JSON response from every tab will be stored. ' +
        'Set SNIFF_DOMAINS to scope capture to the sites you are actually working on.',
    );
  }

  const stats: SnifferStats = { captured: 0, skipped: 0, errors: 0 };

  const handler = (response: Response): void => {
    // Isolate every response: a single failure must not break the listener.
    try {
      const url = response.url();
      const status = response.status();
      const ctRaw = response.headers()['content-type'] ?? '';
      const ct = normalizeContentType(ctRaw);

      if (domainAllowlist) {
        let host = '';
        try {
          host = new URL(url).hostname;
        } catch {
          host = '';
        }
        if (!host || !domainAllowlist.some((suffix) => hostMatches(host, suffix))) {
          stats.skipped++;
          return;
        }
      }
      if (urlInclude && !urlInclude.some((kw) => url.includes(kw))) {
        stats.skipped++;
        return;
      }
      if (urlExclude && urlExclude.some((kw) => url.includes(kw))) {
        stats.skipped++;
        return;
      }
      if (contentTypeSet.size > 0 && !contentTypeSet.has(ct)) {
        stats.skipped++;
        return;
      }

      void consumeBody(response, maxBodyBytes)
        .then((result) => {
          if (result.kind === 'captured') {
            void store
              .insert({
                url,
                status,
                content_type: ctRaw || null,
                body: result.body,
              })
              .then(() => {
                stats.captured++;
              })
              .catch((err: unknown) => {
                stats.errors++;
                logger.warn(`sniffer insert failed`, {
                  url,
                  error: err instanceof Error ? err.message : String(err),
                });
              });
          } else if (result.kind === 'oversize') {
            stats.skipped++;
          } else if (result.kind === 'error') {
            stats.errors++;
            logger.warn(`sniffer body read failed`, {
              url,
              reason: result.reason,
            });
          }
        })
        .catch((err: unknown) => {
          stats.errors++;
          logger.warn(`sniffer body pipeline failed`, {
            url,
            error: err instanceof Error ? err.message : String(err),
          });
        });
    } catch (err) {
      stats.errors++;
      logger.warn(`sniffer handler threw`, {
        error: err instanceof Error ? err.message : String(err),
      });
    }
  };

  source.on('response', handler);

  return {
    stop(): void {
      source.off('response', handler);
    },
    getStats(): SnifferStats {
      return { ...stats };
    },
  };
}

type BodyResult =
  | { kind: 'captured'; body: string }
  | { kind: 'oversize'; bytes: number }
  | { kind: 'error'; reason: string };

async function consumeBody(
  response: Response,
  maxBodyBytes: number,
): Promise<BodyResult> {
  // Try JSON first: if content-type is JSON, prefer the parsed+stringified form
  // so we capture canonical JSON regardless of how the server formatted it.
  let body: string;
  try {
    const json = await response.json();
    body = JSON.stringify(json);
  } catch {
    try {
      body = await response.text();
    } catch (err) {
      return {
        kind: 'error',
        reason: err instanceof Error ? err.message : String(err),
      };
    }
  }

  const bytes = Buffer.byteLength(body, 'utf8');
  if (bytes > maxBodyBytes) {
    return { kind: 'oversize', bytes };
  }
  return { kind: 'captured', body };
}
