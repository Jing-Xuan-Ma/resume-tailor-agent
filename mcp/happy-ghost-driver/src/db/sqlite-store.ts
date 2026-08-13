import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

import Database from 'better-sqlite3';

import { logger } from '../util/logger.js';
import type { InterceptedRecord, InterceptedRow, InterceptStore, QueryFilter } from './types.js';
import { clampQueryLimit } from './types.js';

const SCHEMA = `
CREATE TABLE IF NOT EXISTS intercepted (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL,
  status INTEGER,
  content_type TEXT,
  body TEXT,
  ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_url ON intercepted(url);
CREATE INDEX IF NOT EXISTS idx_ts ON intercepted(ts);
`;

export class SqliteInterceptStore implements InterceptStore {
  private db: Database.Database | null = null;

  constructor(private readonly path: string) {}

  open(): void {
    if (this.db) {
      this.db.close();
      this.db = null;
    }
    mkdirSync(dirname(this.path), { recursive: true });
    this.db = new Database(this.path);
    this.db.pragma('journal_mode = WAL');
    this.db.exec(SCHEMA);
    logger.info('SQLite store opened', { path: this.path });
  }

  async insert(record: InterceptedRecord): Promise<void> {
    const db = this.requireDb();
    const stmt = db.prepare(
      `INSERT INTO intercepted (url, status, content_type, body, ts) VALUES (?, ?, ?, ?, ?)`,
    );
    stmt.run(record.url, record.status, record.content_type, record.body, Date.now());
  }

  async query(filter: QueryFilter): Promise<InterceptedRow[]> {
    const db = this.requireDb();
    const limit = clampQueryLimit(filter.limit);

    const stmt = db.prepare(
      filter.sinceTs !== undefined
        ? `SELECT id, url, status, content_type, body, ts
           FROM intercepted
           WHERE url LIKE ? AND ts >= ?
           ORDER BY ts DESC
           LIMIT ?`
        : `SELECT id, url, status, content_type, body, ts
           FROM intercepted
           WHERE url LIKE ?
           ORDER BY ts DESC
           LIMIT ?`,
    );

    return (
      filter.sinceTs !== undefined
        ? stmt.all(filter.urlPattern, filter.sinceTs, limit)
        : stmt.all(filter.urlPattern, limit)
    ) as InterceptedRow[];
  }

  async purgeOlderThan(cutoffTs: number): Promise<number> {
    const db = this.requireDb();
    const info = db.prepare(`DELETE FROM intercepted WHERE ts < ?`).run(cutoffTs);
    return info.changes;
  }

  async close(): Promise<void> {
    if (this.db) {
      this.db.close();
      this.db = null;
      logger.info('SQLite store closed', { path: this.path });
    }
  }

  private requireDb(): Database.Database {
    if (!this.db) {
      throw new Error('SQLite store is not open.');
    }
    return this.db;
  }
}
