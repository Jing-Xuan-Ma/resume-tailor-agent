/**
 * Screenshot capture for the take_screenshot tool: the raw image (plus
 * coordinate-mapping metadata) is handed back to the agent, whose own
 * multimodal model — or the in-repo screen-locate skill — does the
 * visual locating.
 *
 * Sizing contract:
 *   - PNG is the default (lossless).
 *   - If the PNG base64 exceeds `maxBytes`, we re-capture as JPEG with a
 *     fixed quality of 80 (visually lossless for UI screenshots and
 *     roughly 3-4x smaller than PNG for typical photo-heavy pages).
 *   - If the JPEG STILL exceeds `maxBytes`, we byte-slice the base64 and
 *     flag `truncated: true`. A truncated image is likely un-decodable
 *     downstream; callers MUST treat this as a degraded signal.
 */

import type { Page } from 'playwright-core';

import { logger } from '../util/logger.js';

/** Default cap on base64 length. 1 MiB keeps us well under typical API limits. */
export const DEFAULT_MAX_SCREENSHOT_BYTES = 1 * 1024 * 1024;

/** JPEG quality used when PNG exceeds the byte cap. */
const FALLBACK_JPEG_QUALITY = 80;

/** Bare encode result produced by captureEncoded. */
interface EncodedScreenshot {
  base64: string;
  mediaType: 'image/png' | 'image/jpeg';
  truncated: boolean;
}

/**
 * Capture + downsize a screenshot to a byte budget, returning only the
 * encoded bytes. PNG → JPEG → byte-slice fallback chain.
 */
async function captureEncoded(
  page: Page,
  opts: { fullPage?: boolean; maxBytes?: number } = {},
): Promise<EncodedScreenshot> {
  const fullPage = opts.fullPage ?? false;
  const maxBytes = opts.maxBytes ?? DEFAULT_MAX_SCREENSHOT_BYTES;

  // First attempt: PNG. playwright-core 1.60 returns a Buffer; we
  // base64-encode it ourselves so we control the string form.
  const pngBuf = await page.screenshot({
    type: 'png',
    fullPage,
  });
  const pngB64 = bufferToBase64(pngBuf);
  if (pngB64.length <= maxBytes) {
    return { base64: pngB64, mediaType: 'image/png', truncated: false };
  }

  logger.warn('screenshot: PNG exceeds maxBytes; retrying as JPEG', {
    pngBytes: pngB64.length,
    maxBytes,
  });

  // Second attempt: JPEG. Only meaningful for full-color content; JPEG
  // does not support alpha so Playwright will composite onto white.
  const jpegBuf = await page.screenshot({
    type: 'jpeg',
    quality: FALLBACK_JPEG_QUALITY,
    fullPage,
  });
  const jpegB64 = bufferToBase64(jpegBuf);
  if (jpegB64.length <= maxBytes) {
    return { base64: jpegB64, mediaType: 'image/jpeg', truncated: false };
  }

  // Final fallback: byte-slice the base64. The result will likely be a
  // broken image, but we surface `truncated: true` so the caller can
  // decide whether to attempt the vision call at all.
  logger.warn('screenshot: JPEG still over maxBytes; truncating', {
    jpegBytes: jpegB64.length,
    maxBytes,
  });
  return {
    base64: jpegB64.slice(0, maxBytes),
    mediaType: 'image/jpeg',
    truncated: true,
  };
}

/**
 * Screenshot enriched with coordinate-mapping metadata, for tools that
 * hand the raw image back to a multimodal agent (Cursor's own vision).
 *
 * The agent reads pixel coordinates off the IMAGE. To click via
 * physical_click (which expects CSS pixels relative to the viewport),
 * those image coordinates must be divided by `deviceScaleFactor`.
 */
export interface ScreenshotWithMeta {
  base64: string;
  mediaType: 'image/png' | 'image/jpeg';
  /** True width of the decoded image in raw pixels. */
  imagePxWidth: number;
  /** True height of the decoded image in raw pixels. */
  imagePxHeight: number;
  /** Viewport width in CSS pixels (window.innerWidth). */
  cssWidth: number;
  /** Viewport height in CSS pixels (window.innerHeight). */
  cssHeight: number;
  /** image px / css px. Usually devicePixelRatio (e.g. 2 on retina). */
  deviceScaleFactor: number;
  /** True iff the base64 was byte-truncated to fit under maxBytes. */
  truncated: boolean;
}

const VIEWPORT_PROBE_SCRIPT =
  "({ cssWidth: window.innerWidth, cssHeight: window.innerHeight, dpr: window.devicePixelRatio })";

/**
 * Capture a screenshot and the metadata an agent needs to translate
 * image-pixel coordinates into CSS pixels for physical_click.
 */
export async function captureScreenshotWithMeta(
  page: Page,
  opts: { fullPage?: boolean; maxBytes?: number } = {},
): Promise<ScreenshotWithMeta> {
  const viewport = await safeViewportProbe(page);
  const encoded = await captureEncoded(page, opts);

  // Decode true image dimensions from the (non-truncated) bytes. A
  // truncated payload may not contain a parseable header; fall back to
  // css × dpr in that case.
  const dims = encoded.truncated
    ? null
    : decodeImageDimensions(encoded.base64, encoded.mediaType);

  const cssWidth = viewport.cssWidth;
  const cssHeight = viewport.cssHeight;
  const dpr = viewport.dpr;
  const imagePxWidth = dims?.width ?? Math.round(cssWidth * dpr);
  const imagePxHeight = dims?.height ?? Math.round(cssHeight * dpr);

  // Prefer measured ratio; fall back to reported dpr when css width is 0.
  const deviceScaleFactor =
    cssWidth > 0 && imagePxWidth > 0
      ? Math.round((imagePxWidth / cssWidth) * 1000) / 1000
      : dpr;

  return {
    base64: encoded.base64,
    mediaType: encoded.mediaType,
    imagePxWidth,
    imagePxHeight,
    cssWidth,
    cssHeight,
    deviceScaleFactor,
    truncated: encoded.truncated,
  };
}

/**
 * Read the viewport CSS size and devicePixelRatio from the page. Uses
 * page.evaluate (string form, mirroring a11y.ts) instead of
 * viewportSize() because the latter returns null for CDP-attached pages
 * with no fixed viewport.
 */
async function safeViewportProbe(
  page: Page,
): Promise<{ cssWidth: number; cssHeight: number; dpr: number }> {
  try {
    const res: { cssWidth?: unknown; cssHeight?: unknown; dpr?: unknown } =
      await page.evaluate(VIEWPORT_PROBE_SCRIPT);
    const cssWidth = typeof res?.cssWidth === 'number' ? res.cssWidth : 0;
    const cssHeight = typeof res?.cssHeight === 'number' ? res.cssHeight : 0;
    const dpr = typeof res?.dpr === 'number' && res.dpr > 0 ? res.dpr : 1;
    return { cssWidth, cssHeight, dpr };
  } catch (err) {
    logger.warn('screenshot: viewport probe failed', {
      error: err instanceof Error ? err.message : String(err),
    });
    return { cssWidth: 0, cssHeight: 0, dpr: 1 };
  }
}

/**
 * Decode the pixel dimensions of a PNG or JPEG from its base64 bytes.
 * Returns null when the header cannot be parsed.
 *
 * - PNG: the IHDR chunk starts at byte 16; width/height are big-endian
 *   uint32 at offsets 16 and 20.
 * - JPEG: scan segments for a SOF marker (0xFFC0..0xFFCF excluding the
 *   non-SOF C4/C8/CC), then read height/width as big-endian uint16.
 */
export function decodeImageDimensions(
  base64: string,
  mediaType: 'image/png' | 'image/jpeg',
): { width: number; height: number } | null {
  let buf: Buffer;
  try {
    buf = Buffer.from(base64, 'base64');
  } catch {
    return null;
  }
  return mediaType === 'image/png' ? decodePng(buf) : decodeJpeg(buf);
}

function decodePng(buf: Buffer): { width: number; height: number } | null {
  // 8-byte signature + 4-byte length + "IHDR" + width(4) + height(4).
  if (buf.length < 24) return null;
  if (buf.readUInt32BE(12) !== 0x49484452) return null; // "IHDR"
  const width = buf.readUInt32BE(16);
  const height = buf.readUInt32BE(20);
  if (width <= 0 || height <= 0) return null;
  return { width, height };
}

function decodeJpeg(buf: Buffer): { width: number; height: number } | null {
  if (buf.length < 4 || buf[0] !== 0xff || buf[1] !== 0xd8) return null;
  let offset = 2;
  while (offset + 9 < buf.length) {
    if (buf[offset] !== 0xff) {
      offset++;
      continue;
    }
    const marker = buf[offset + 1]!;
    // Standalone markers (no length): RSTn, SOI, EOI, TEM.
    if (marker === 0xd8 || marker === 0xd9 || (marker >= 0xd0 && marker <= 0xd7)) {
      offset += 2;
      continue;
    }
    const segLen = buf.readUInt16BE(offset + 2);
    // SOF markers carry frame dimensions. Exclude DHT(C4), JPG(C8), DAC(CC).
    const isSof =
      marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc;
    if (isSof) {
      const height = buf.readUInt16BE(offset + 5);
      const width = buf.readUInt16BE(offset + 7);
      if (width <= 0 || height <= 0) return null;
      return { width, height };
    }
    offset += 2 + segLen;
  }
  return null;
}

/**
 * Convert a screenshot Buffer (or string when an injected mock returns
 * one) to a base64 string. Defends against mocks that hand us a string
 * directly — keep the runtime robust for tests.
 */
function bufferToBase64(buf: Buffer | unknown): string {
  if (typeof buf === 'string') return buf;
  if (Buffer.isBuffer(buf)) return buf.toString('base64');
  // Last resort: JSON-coerce. This branch should never hit in
  // production but lets a test mock return an arbitrary payload.
  return Buffer.from(String(buf)).toString('base64');
}

