/**
 * Inject a local file into an <input type="file"> via Playwright.
 * File inputs are usually hidden from A11y — this is the intentional
 * exception to the "no selectors" rule for geo-publish cover/docx flows.
 */

import { access } from 'node:fs/promises';
import { resolve } from 'node:path';

import type { Page } from 'playwright-core';

import { logger } from '../util/logger.js';

export interface SetInputFilesResult {
  ok: true;
  path: string;
  selector: string;
  input_count: number;
}

/**
 * Set files on a file input. Absolute path required; must exist on disk.
 * Default selector matches the first attached file input on the page.
 */
export async function setInputFiles(
  page: Page,
  filePath: string,
  selector = 'input[type="file"]',
): Promise<SetInputFilesResult> {
  const abs = resolve(filePath);
  await access(abs);

  const locator = page.locator(selector);
  const count = await locator.count();
  if (count === 0) {
    throw new Error(`no_file_input: selector=${selector}`);
  }

  // Prefer the first attached input (hidden is fine — Playwright setInputFiles works).
  await locator.first().setInputFiles(abs);
  logger.info('set_input_files ok', { path: abs, selector, input_count: count });
  return { ok: true, path: abs, selector, input_count: count };
}
