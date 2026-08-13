import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
  resolveStoreBackend,
  resolveMysqlConfig,
  createInterceptStoreFromEnv,
} from '../../dist/db/factory.js';
import { resetAppConfigLoader } from '../../dist/config/load.js';

// resolveStoreBackend/resolveMysqlConfig call ensureAppConfigLoaded(),
// which reads config/ relative to cwd. Chdir into an empty sandbox so a
// developer machine's real config/app.config(.enc).json can't leak into
// the assertions.
function withEmptyConfigDir(fn) {
  const dir = mkdtempSync(join(tmpdir(), 'ghost-store-factory-'));
  const prevCwd = process.cwd();
  process.chdir(dir);
  resetAppConfigLoader();
  try {
    return fn();
  } finally {
    process.chdir(prevCwd);
    resetAppConfigLoader();
    rmSync(dir, { recursive: true, force: true });
  }
}

function withEnv(overrides, fn) {
  const saved = {};
  for (const key of Object.keys(overrides)) {
    saved[key] = process.env[key];
    const value = overrides[key];
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  try {
    return fn();
  } finally {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

test('resolveStoreBackend: defaults to sqlite', () => {
  withEmptyConfigDir(() => {
    withEnv({ STORE_BACKEND: undefined }, () => {
      assert.equal(resolveStoreBackend(), 'sqlite');
    });
  });
});

test('resolveStoreBackend: accepts mysql', () => {
  withEmptyConfigDir(() => {
    withEnv({ STORE_BACKEND: 'mysql' }, () => {
      assert.equal(resolveStoreBackend(), 'mysql');
    });
  });
});

test('resolveMysqlConfig: parses DATABASE_URL', () => {
  withEnv(
    {
      DATABASE_URL: 'mysql://user:pa%40ss@db.example.com:3307/ghost_driver',
      MYSQL_USER: undefined,
      MYSQL_DATABASE: undefined,
    },
    () => {
      assert.deepEqual(resolveMysqlConfig(), {
        host: 'db.example.com',
        port: 3307,
        user: 'user',
        password: 'pa@ss',
        database: 'ghost_driver',
      });
    },
  );
});

test('resolveMysqlConfig: builds from MYSQL_* vars', () => {
  withEnv(
    {
      DATABASE_URL: undefined,
      MYSQL_USER: 'ghost',
      MYSQL_PASSWORD: 'secret',
      MYSQL_DATABASE: 'intercepted',
      MYSQL_HOST: '127.0.0.1',
      MYSQL_PORT: '3306',
    },
    () => {
      assert.deepEqual(resolveMysqlConfig(), {
        host: '127.0.0.1',
        port: 3306,
        user: 'ghost',
        password: 'secret',
        database: 'intercepted',
      });
    },
  );
});

test('createInterceptStoreFromEnv: sqlite creates missing parent directory', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'ghost-sqlite-mkdir-'));
  const dbPath = join(dir, 'nested/data/intercepted.db');
  const prevCwd = process.cwd();
  process.chdir(dir);
  resetAppConfigLoader();
  try {
    await withEnv({ STORE_BACKEND: 'sqlite', DB_PATH: dbPath }, async () => {
      const store = await createInterceptStoreFromEnv();
      assert.ok(existsSync(dbPath));
      await store.close();
    });
  } finally {
    process.chdir(prevCwd);
    resetAppConfigLoader();
    rmSync(dir, { recursive: true, force: true });
  }
});
