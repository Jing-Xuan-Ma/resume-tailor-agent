import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { decryptJson, encryptJson } from '../../dist/config/crypto.js';
import {
  configEncPath,
  configKeyPath,
  configPlainPath,
} from '../../dist/config/paths.js';
import {
  ensureAppConfigLoaded,
  loadAppConfig,
  resetAppConfigLoader,
} from '../../dist/config/load.js';

// Path helpers resolve against process.cwd() at CALL time, so chdir-ing
// into a temp sandbox makes every config read/write hermetic. (An older
// version resolved paths at import time and a test overwrote the repo's
// real config/ files — never again.)
function withConfigSandbox(fn) {
  const dir = mkdtempSync(join(tmpdir(), 'ghost-config-'));
  const prevCwd = process.cwd();
  process.chdir(dir);
  mkdirSync('config', { recursive: true });
  try {
    fn();
  } finally {
    process.chdir(prevCwd);
    rmSync(dir, { recursive: true, force: true });
  }
}

test('config crypto: roundtrip', () => {
  const payload = {
    store: {
      backend: 'mysql',
      mysql: {
        host: 'db.example.com',
        port: 3306,
        user: 'u',
        password: 'p@ss',
        database: 'ghost',
      },
    },
  };
  const enc = encryptJson(payload, 'test-passphrase');
  const dec = decryptJson(enc, 'test-passphrase');
  assert.deepEqual(dec, payload);
});

test('config crypto: wrong passphrase fails', () => {
  const enc = encryptJson({ ok: true }, 'right');
  assert.throws(() => decryptJson(enc, 'wrong'));
});

test('loadAppConfig reads plain json', () => {
  withConfigSandbox(() => {
    writeFileSync(
      configPlainPath(),
      JSON.stringify({
        store: {
          backend: 'mysql',
          mysql: { user: 'ghost', password: 's', database: 'db' },
        },
      }),
    );

    assert.deepEqual(loadAppConfig(), {
      store: {
        backend: 'mysql',
        mysql: { user: 'ghost', password: 's', database: 'db' },
      },
    });
  });
});

test('ensureAppConfigLoaded applies unset env vars', () => {
  withConfigSandbox(() => {
    writeFileSync(
      configPlainPath(),
      JSON.stringify({
        store: {
          backend: 'mysql',
          mysql: {
            host: 'cfg-host',
            user: 'cfg-user',
            password: 'cfg-pass',
            database: 'cfg-db',
          },
        },
      }),
    );

    resetAppConfigLoader();
    const saved = {
      STORE_BACKEND: process.env.STORE_BACKEND,
      MYSQL_HOST: process.env.MYSQL_HOST,
      MYSQL_USER: process.env.MYSQL_USER,
      MYSQL_PASSWORD: process.env.MYSQL_PASSWORD,
      MYSQL_DATABASE: process.env.MYSQL_DATABASE,
    };
    delete process.env.STORE_BACKEND;
    delete process.env.MYSQL_HOST;
    delete process.env.MYSQL_USER;
    delete process.env.MYSQL_PASSWORD;
    delete process.env.MYSQL_DATABASE;

    try {
      ensureAppConfigLoaded();
      assert.equal(process.env.STORE_BACKEND, 'mysql');
      assert.equal(process.env.MYSQL_HOST, 'cfg-host');
      assert.equal(process.env.MYSQL_USER, 'cfg-user');
      assert.equal(process.env.MYSQL_PASSWORD, 'cfg-pass');
      assert.equal(process.env.MYSQL_DATABASE, 'cfg-db');
    } finally {
      resetAppConfigLoader();
      for (const [key, val] of Object.entries(saved)) {
        if (val === undefined) delete process.env[key];
        else process.env[key] = val;
      }
    }
  });
});

test('encrypted config loads with key file', () => {
  withConfigSandbox(() => {
    writeFileSync(configKeyPath(), 'local-dev-key\n');
    const enc = encryptJson(
      {
        store: {
          backend: 'mysql',
          mysql: {
            host: 'enc-host',
            user: 'enc-user',
            password: 'enc-pass',
            database: 'enc-db',
          },
        },
      },
      'local-dev-key',
    );
    writeFileSync(configEncPath(), JSON.stringify(enc));

    assert.deepEqual(loadAppConfig(), {
      store: {
        backend: 'mysql',
        mysql: {
          host: 'enc-host',
          user: 'enc-user',
          password: 'enc-pass',
          database: 'enc-db',
        },
      },
    });
  });
});
