import { existsSync, readFileSync } from 'node:fs';

import { decryptJson } from './crypto.js';
import { configEncPath, configKeyPath, configPlainPath } from './paths.js';
import type { AppConfig, EncryptedPayload } from './types.js';

let loaded = false;

function readPassphrase(): string | null {
  const fromEnv = process.env.GHOST_CONFIG_KEY?.trim();
  if (fromEnv) return fromEnv;

  if (!existsSync(configKeyPath())) return null;
  const raw = readFileSync(configKeyPath(), 'utf8').trim();
  return raw || null;
}

function readConfigFile(): AppConfig | null {
  if (existsSync(configEncPath())) {
    const passphrase = readPassphrase();
    if (!passphrase) {
      throw new Error(
        `Encrypted config found at ${configEncPath()} but no key. Set GHOST_CONFIG_KEY or create ${configKeyPath()}.`,
      );
    }
    const payload = JSON.parse(readFileSync(configEncPath(), 'utf8')) as EncryptedPayload;
    return decryptJson<AppConfig>(payload, passphrase);
  }

  if (existsSync(configPlainPath())) {
    return JSON.parse(readFileSync(configPlainPath(), 'utf8')) as AppConfig;
  }

  return null;
}

function setEnvIfUnset(name: string, value: string | undefined): void {
  if (value === undefined || value === '') return;
  if (process.env[name]?.trim()) return;
  process.env[name] = value;
}

function applyConfig(config: AppConfig): void {
  const { store } = config;
  setEnvIfUnset('STORE_BACKEND', store.backend);

  if (store.sqlite?.path) {
    setEnvIfUnset('DB_PATH', store.sqlite.path);
  }

  const mysql = store.mysql;
  if (mysql) {
    setEnvIfUnset('MYSQL_HOST', mysql.host);
    if (mysql.port !== undefined) {
      setEnvIfUnset('MYSQL_PORT', String(mysql.port));
    }
    setEnvIfUnset('MYSQL_USER', mysql.user);
    setEnvIfUnset('MYSQL_PASSWORD', mysql.password);
    setEnvIfUnset('MYSQL_DATABASE', mysql.database);
  }
}

/** Load project config once and apply unset env vars (env still wins). */
export function ensureAppConfigLoaded(): void {
  if (loaded) return;
  loaded = true;

  const config = readConfigFile();
  if (!config) return;
  applyConfig(config);
}

/** @internal test helper */
export function resetAppConfigLoader(): void {
  loaded = false;
}

/** Read config file without touching process.env. */
export function loadAppConfig(): AppConfig | null {
  return readConfigFile();
}
