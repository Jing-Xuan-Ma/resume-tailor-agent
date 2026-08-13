/**
 * Local action ledger — the audit trail for everything the agent physically
 * did, and the data source the budget guard counts against.
 *
 * Deliberately its own local SQLite file rather than the intercept store:
 *   - The intercept store can be pointed at MySQL (STORE_BACKEND=mysql). A
 *     safety guard that stops working when a remote DB is unreachable is not
 *     a safety guard.
 *   - It lives next to the Chrome profile under $GHOST_HOME because both are
 *     identity-continuity state: quota history is only meaningful for as
 *     long as the profile it describes still exists.
 *
 * Never stores typed content — only shapes and counts. The point is "did
 * today look like me?", which needs volume and timing, not payloads.
 */

import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

import Database from 'better-sqlite3';

import { resolveLedgerPath } from '../config/paths.js';
import { logger } from '../util/logger.js';
import type { LedgerCountQuery, LedgerEntry } from './types.js';

const SCHEMA = `
CREATE TABLE IF NOT EXISTS action_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  domain TEXT NOT NULL,
  action_type TEXT NOT NULL,
  write_class TEXT NOT NULL,
  url TEXT NOT NULL,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_ledger_ts ON action_ledger(ts);
CREATE INDEX IF NOT EXISTS idx_ledger_domain_ts ON action_ledger(domain, ts);
CREATE INDEX IF NOT EXISTS idx_ledger_class_ts ON action_ledger(write_class, ts);
`;

let db: Database.Database | null = null;
let openFailed = false;

/**
 * Open lazily on first use. A ledger that cannot open is logged loudly and
 * then degrades to "no ledger" rather than breaking every tool call: losing
 * the audit trail is bad, but wedging the whole MCP server is worse.
 */
function handle(): Database.Database | null {
  if (db) return db;
  if (openFailed) return null;
  const path = resolveLedgerPath();
  try {
    mkdirSync(dirname(path), { recursive: true });
    const opened = new Database(path);
    opened.pragma('journal_mode = WAL');
    opened.exec(SCHEMA);
    db = opened;
    logger.info('action ledger opened', { path });
    return db;
  } catch (err) {
    openFailed = true;
    logger.error('action ledger failed to open; budget guard will fail OPEN', {
      path,
      error: err instanceof Error ? err.message : String(err),
    });
    return null;
  }
}

export function recordAction(entry: LedgerEntry): void {
  const h = handle();
  if (!h) return;
  try {
    h.prepare(
      `INSERT INTO action_ledger (ts, domain, action_type, write_class, url, detail)
       VALUES (?, ?, ?, ?, ?, ?)`,
    ).run(
      entry.ts,
      entry.domain,
      entry.actionType,
      entry.writeClass,
      entry.url,
      entry.detail,
    );
  } catch (err) {
    logger.warn('action ledger insert failed', {
      error: err instanceof Error ? err.message : String(err),
    });
  }
}

/** Count matching actions. Returns 0 when the ledger is unavailable. */
export function countActions(query: LedgerCountQuery): number {
  const h = handle();
  if (!h) return 0;
  const clauses = ['ts >= ?'];
  const params: unknown[] = [query.sinceTs];
  if (query.domain !== undefined) {
    clauses.push('domain = ?');
    params.push(query.domain);
  }
  if (query.writeClass !== undefined) {
    clauses.push('write_class = ?');
    params.push(query.writeClass);
  }
  try {
    const row = h
      .prepare(`SELECT COUNT(*) AS n FROM action_ledger WHERE ${clauses.join(' AND ')}`)
      .get(...params) as { n: number } | undefined;
    return row?.n ?? 0;
  } catch (err) {
    logger.warn('action ledger count failed', {
      error: err instanceof Error ? err.message : String(err),
    });
    return 0;
  }
}

/** Most recent entries, newest first. For the operator's own review. */
export function recentActions(limit = 100): LedgerEntry[] {
  const h = handle();
  if (!h) return [];
  const capped = Math.min(Math.max(1, limit), 1000);
  try {
    const rows = h
      .prepare(
        `SELECT ts, domain, action_type, write_class, url, detail
         FROM action_ledger ORDER BY ts DESC LIMIT ?`,
      )
      .all(capped) as Array<{
      ts: number;
      domain: string;
      action_type: string;
      write_class: string;
      url: string;
      detail: string | null;
    }>;
    return rows.map((r) => ({
      ts: r.ts,
      domain: r.domain,
      actionType: r.action_type as LedgerEntry['actionType'],
      writeClass: r.write_class as LedgerEntry['writeClass'],
      url: r.url,
      detail: r.detail,
    }));
  } catch (err) {
    logger.warn('action ledger read failed', {
      error: err instanceof Error ? err.message : String(err),
    });
    return [];
  }
}

export function closeLedger(): void {
  if (db) {
    try {
      db.close();
    } catch {
      // Closing a already-broken handle is not worth reporting.
    }
    db = null;
  }
}
