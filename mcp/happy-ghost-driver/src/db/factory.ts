import { resolve } from 'node:path';

import { ensureAppConfigLoaded } from '../config/load.js';
import type { InterceptStore } from './types.js';
import { SqliteInterceptStore } from './sqlite-store.js';
import { MysqlInterceptStore, type MysqlStoreConfig } from './mysql-store.js';

const DEFAULT_DB_PATH = './data/intercepted.db';

export function resolveStoreBackend(): 'sqlite' | 'mysql' {
  ensureAppConfigLoaded();
  const raw = (process.env.STORE_BACKEND ?? 'sqlite').trim().toLowerCase();
  if (raw === 'mysql') return 'mysql';
  if (raw === 'sqlite') return 'sqlite';
  throw new Error(`Unknown STORE_BACKEND: ${process.env.STORE_BACKEND}`);
}

export function resolveMysqlConfig(): MysqlStoreConfig {
  ensureAppConfigLoaded();
  const url = process.env.DATABASE_URL?.trim();
  if (url) {
    return parseMysqlUrl(url);
  }

  const user = process.env.MYSQL_USER?.trim();
  const database = process.env.MYSQL_DATABASE?.trim();
  if (!user || !database) {
    throw new Error(
      'MySQL store requires DATABASE_URL or MYSQL_USER + MYSQL_DATABASE (and optionally MYSQL_HOST, MYSQL_PORT, MYSQL_PASSWORD)',
    );
  }

  return {
    host: process.env.MYSQL_HOST?.trim() || '127.0.0.1',
    port: parsePort(process.env.MYSQL_PORT, 3306),
    user,
    password: process.env.MYSQL_PASSWORD ?? '',
    database,
  };
}

function parseMysqlUrl(raw: string): MysqlStoreConfig {
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error('DATABASE_URL is not a valid URL');
  }
  if (parsed.protocol !== 'mysql:' && parsed.protocol !== 'mysql2:') {
    throw new Error('DATABASE_URL must use mysql:// or mysql2:// scheme');
  }
  const database = parsed.pathname.replace(/^\//, '');
  if (!database) {
    throw new Error('DATABASE_URL must include a database name');
  }
  return {
    host: parsed.hostname || '127.0.0.1',
    port: parsePort(parsed.port, 3306),
    user: decodeURIComponent(parsed.username),
    password: decodeURIComponent(parsed.password),
    database,
  };
}

function parsePort(raw: string | undefined, fallback: number): number {
  if (!raw || raw.trim() === '') return fallback;
  const n = Number(raw);
  if (!Number.isFinite(n) || !Number.isInteger(n) || n <= 0) {
    throw new Error(`Invalid MySQL port: ${raw}`);
  }
  return n;
}

export async function createInterceptStoreFromEnv(): Promise<InterceptStore> {
  const backend = resolveStoreBackend();
  if (backend === 'mysql') {
    const store = new MysqlInterceptStore(resolveMysqlConfig());
    await store.open();
    return store;
  }

  const path = resolve(process.env.DB_PATH?.trim() || DEFAULT_DB_PATH);
  const store = new SqliteInterceptStore(path);
  store.open();
  return store;
}
