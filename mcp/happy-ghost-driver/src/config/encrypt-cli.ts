import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { randomBytes } from 'node:crypto';

import { encryptJson } from './crypto.js';
import {
  configEncPath,
  configExamplePath,
  configKeyPath,
  configPlainPath,
} from './paths.js';
import type { AppConfig } from './types.js';

function usage(): never {
  console.error(`Usage:
  node dist/config/encrypt-cli.js init          Create config/.key and copy example if missing
  node dist/config/encrypt-cli.js encrypt     Encrypt config/app.config.json -> app.config.enc.json
  node dist/config/encrypt-cli.js keygen      Regenerate config/.key only`);
  process.exit(1);
}

function writeKey(): string {
  const key = randomBytes(32).toString('hex');
  writeFileSync(configKeyPath(), `${key}\n`, { mode: 0o600 });
  console.log(`Wrote ${configKeyPath()}`);
  return key;
}

function readKey(): string {
  const fromEnv = process.env.GHOST_CONFIG_KEY?.trim();
  if (fromEnv) return fromEnv;
  if (!existsSync(configKeyPath())) {
    throw new Error(`Missing ${configKeyPath()}. Run: npm run config:init`);
  }
  return readFileSync(configKeyPath(), 'utf8').trim();
}

function cmdInit(): void {
  if (!existsSync(configKeyPath())) {
    writeKey();
  } else {
    console.log(`Key already exists: ${configKeyPath()}`);
  }

  if (!existsSync(configPlainPath()) && existsSync(configExamplePath())) {
    writeFileSync(configPlainPath(), readFileSync(configExamplePath()));
    console.log(`Copied example -> ${configPlainPath()}`);
    console.log('Edit app.config.json, then run: npm run config:encrypt');
  } else if (existsSync(configPlainPath())) {
    console.log(`Plain config already exists: ${configPlainPath()}`);
  }
}

function cmdEncrypt(): void {
  if (!existsSync(configPlainPath())) {
    throw new Error(`Missing ${configPlainPath()}. Run: npm run config:init`);
  }
  const config = JSON.parse(readFileSync(configPlainPath(), 'utf8')) as AppConfig;
  const key = readKey();
  const payload = encryptJson(config, key);
  writeFileSync(configEncPath(), `${JSON.stringify(payload, null, 2)}\n`, { mode: 0o600 });
  console.log(`Wrote ${configEncPath()}`);
  console.log('You can delete config/app.config.json after verifying the server starts.');
}

function main(): void {
  const cmd = process.argv[2];
  if (cmd === 'init') {
    cmdInit();
    return;
  }
  if (cmd === 'encrypt') {
    cmdEncrypt();
    return;
  }
  if (cmd === 'keygen') {
    writeKey();
    return;
  }
  usage();
}

main();
