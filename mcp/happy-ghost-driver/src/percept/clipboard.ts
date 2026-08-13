/**
 * System clipboard read/write — used after physical copy (Meta+C / platform
 * copy button) and before paste (Meta+V) for long-form article injection.
 */

import { execFile, spawn } from 'node:child_process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

/** Write stdin to a clipboard helper command. */
function pipeToClipboardCmd(
  command: string,
  args: string[],
  text: string,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ['pipe', 'ignore', 'pipe'] });
    let stderr = '';
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} exited ${code}: ${stderr.trim()}`));
    });
    child.stdin.write(text, 'utf8');
    child.stdin.end();
  });
}

export const MAX_CLIPBOARD_CHARS = 200_000;

/** Last successful write length (for paste → write-intent arming). */
let lastWriteCharCount = 0;

export function getLastClipboardWriteChars(): number {
  return lastWriteCharCount;
}

/**
 * Read plain text from the OS clipboard. Platform-specific commands keep
 * this dependency-free (no npm clipboard packages).
 */
export async function readClipboardText(): Promise<string> {
  let raw: string;
  if (process.platform === 'darwin') {
    ({ stdout: raw } = await execFileAsync('pbpaste', []));
  } else if (process.platform === 'win32') {
    ({ stdout: raw } = await execFileAsync('powershell', [
      '-NoProfile',
      '-Command',
      'Get-Clipboard -Raw',
    ]));
  } else {
    try {
      ({ stdout: raw } = await execFileAsync('xclip', [
        '-selection',
        'clipboard',
        '-o',
      ]));
    } catch {
      ({ stdout: raw } = await execFileAsync('xsel', [
        '--clipboard',
        '--output',
      ]));
    }
  }
  const text = raw.replace(/\r\n/g, '\n');
  if (text.length > MAX_CLIPBOARD_CHARS) {
    return text.slice(0, MAX_CLIPBOARD_CHARS) + '...[truncated]';
  }
  return text;
}

/**
 * Write plain text to the OS clipboard. Truncates to MAX_CLIPBOARD_CHARS.
 * Returns the number of characters actually written.
 */
export async function writeClipboardText(text: string): Promise<number> {
  const normalized = text.replace(/\r\n/g, '\n');
  const payload =
    normalized.length > MAX_CLIPBOARD_CHARS
      ? normalized.slice(0, MAX_CLIPBOARD_CHARS)
      : normalized;

  if (process.platform === 'darwin') {
    await pipeToClipboardCmd('pbcopy', [], payload);
  } else if (process.platform === 'win32') {
    await pipeToClipboardCmd(
      'powershell',
      ['-NoProfile', '-Command', 'Set-Clipboard -Value $input'],
      payload,
    );
  } else {
    try {
      await pipeToClipboardCmd('xclip', ['-selection', 'clipboard', '-i'], payload);
    } catch {
      await pipeToClipboardCmd('xsel', ['--clipboard', '--input'], payload);
    }
  }
  lastWriteCharCount = payload.length;
  return payload.length;
}
