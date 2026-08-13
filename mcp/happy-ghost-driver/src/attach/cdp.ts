import { chromium } from 'playwright-core';
import type { Browser, BrowserContext, Page } from 'playwright-core';

import { logger } from '../util/logger.js';

export interface AttachedBrowser {
  browser: Browser;
  context: BrowserContext;
  page: Page;
}

/**
 * Attach to a Chrome instance already running with --remote-debugging-port.
 * Returns the first browser context and first page found.
 */
export async function attachBrowser(endpoint: string): Promise<AttachedBrowser> {
  logger.info(`Attaching to Chrome via CDP: ${endpoint}`);
  let browser: Browser;
  try {
    browser = await chromium.connectOverCDP(endpoint);
  } catch (err) {
    throw new Error(
      `Failed to connectOverCDP(${endpoint}). Make sure Chrome is running with ` +
        `--remote-debugging-port=9222. Underlying error: ${
          err instanceof Error ? err.message : String(err)
        }`,
    );
  }

  const contexts = browser.contexts();
  if (contexts.length === 0) {
    throw new Error(
      'No browser contexts available after CDP attach. The target Chrome instance may have no open windows.',
    );
  }
  const context = contexts[0];
  if (!context) {
    throw new Error('Unexpected: contexts[0] is undefined');
  }

  const pages = context.pages();
  if (pages.length === 0) {
    throw new Error(
      'No pages available in the first context. Open at least one tab in Chrome before attaching.',
    );
  }
  const page = pages[0];
  if (!page) {
    throw new Error('Unexpected: pages[0] is undefined');
  }

  logger.info('CDP attach succeeded: 1 context, 1 page acquired.');
  return { browser, context, page };
}
