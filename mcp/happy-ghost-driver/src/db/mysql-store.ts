import mysql, { type Pool, type PoolOptions, type RowDataPacket } from 'mysql2/promise';

import { logger } from '../util/logger.js';
import type { InterceptedRecord, InterceptedRow, InterceptStore, QueryFilter } from './types.js';
import { clampQueryLimit } from './types.js';

const SCHEMA = `
CREATE TABLE IF NOT EXISTS intercepted (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  url TEXT NOT NULL,
  status INT,
  content_type VARCHAR(255),
  body LONGTEXT,
  ts BIGINT NOT NULL,
  INDEX idx_url (url(255)),
  INDEX idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
`;

export interface MysqlStoreConfig {
  host: string;
  port: number;
  user: string;
  password: string;
  database: string;
}

export class MysqlInterceptStore implements InterceptStore {
  private pool: Pool | null = null;

  constructor(private readonly config: MysqlStoreConfig) {}

  async open(): Promise<void> {
    if (this.pool) {
      await this.pool.end();
      this.pool = null;
    }

    const poolOpts: PoolOptions = {
      host: this.config.host,
      port: this.config.port,
      user: this.config.user,
      password: this.config.password,
      database: this.config.database,
      waitForConnections: true,
      connectionLimit: 10,
      enableKeepAlive: true,
    };

    this.pool = mysql.createPool(poolOpts);
    await this.pool.query(SCHEMA);
    logger.info('MySQL store opened', {
      host: this.config.host,
      port: this.config.port,
      database: this.config.database,
    });
  }

  async insert(record: InterceptedRecord): Promise<void> {
    const pool = this.requirePool();
    await pool.execute(
      `INSERT INTO intercepted (url, status, content_type, body, ts) VALUES (?, ?, ?, ?, ?)`,
      [record.url, record.status, record.content_type, record.body, Date.now()],
    );
  }

  async query(filter: QueryFilter): Promise<InterceptedRow[]> {
    const pool = this.requirePool();
    // clampQueryLimit guarantees an integer in [1, MAX_QUERY_LIMIT]; inline it
    // because MySQL/RDS prepared statements reject LIMIT placeholders.
    const limit = clampQueryLimit(filter.limit);

    const [rows] =
      filter.sinceTs !== undefined
        ? await pool.execute(
            `SELECT id, url, status, content_type, body, ts
             FROM intercepted
             WHERE url LIKE ? AND ts >= ?
             ORDER BY ts DESC
             LIMIT ${limit}`,
            [filter.urlPattern, filter.sinceTs],
          )
        : await pool.execute(
            `SELECT id, url, status, content_type, body, ts
             FROM intercepted
             WHERE url LIKE ?
             ORDER BY ts DESC
             LIMIT ${limit}`,
            [filter.urlPattern],
          );

    return (rows as RowDataPacket[]).map((row) => ({
      id: Number(row.id),
      url: String(row.url),
      status: row.status === null || row.status === undefined ? null : Number(row.status),
      content_type:
        row.content_type === null || row.content_type === undefined
          ? null
          : String(row.content_type),
      body: String(row.body),
      ts: Number(row.ts),
    }));
  }

  async purgeOlderThan(cutoffTs: number): Promise<number> {
    const pool = this.requirePool();
    const [result] = await pool.execute(`DELETE FROM intercepted WHERE ts < ?`, [cutoffTs]);
    return (result as { affectedRows?: number }).affectedRows ?? 0;
  }

  async close(): Promise<void> {
    if (this.pool) {
      await this.pool.end();
      this.pool = null;
      logger.info('MySQL store closed', { database: this.config.database });
    }
  }

  private requirePool(): Pool {
    if (!this.pool) {
      throw new Error('MySQL store is not open.');
    }
    return this.pool;
  }
}
