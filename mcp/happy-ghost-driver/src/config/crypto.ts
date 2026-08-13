import { createCipheriv, createDecipheriv, randomBytes, scryptSync } from 'node:crypto';

import type { EncryptedPayload } from './types.js';

const ALGO = 'aes-256-gcm';
const KEY_LEN = 32;
const IV_LEN = 12;
const SCRYPT_SALT = 'ghost-driver-mcp-config-v1';

export function encryptJson(value: unknown, passphrase: string): EncryptedPayload {
  const key = scryptSync(passphrase, SCRYPT_SALT, KEY_LEN);
  const iv = randomBytes(IV_LEN);
  const cipher = createCipheriv(ALGO, key, iv);
  const plaintext = Buffer.from(JSON.stringify(value), 'utf8');
  const encrypted = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const tag = cipher.getAuthTag();
  return {
    v: 1,
    iv: iv.toString('base64'),
    tag: tag.toString('base64'),
    data: encrypted.toString('base64'),
  };
}

export function decryptJson<T>(payload: EncryptedPayload, passphrase: string): T {
  if (payload.v !== 1) {
    throw new Error(`Unsupported encrypted config version: ${payload.v}`);
  }
  const key = scryptSync(passphrase, SCRYPT_SALT, KEY_LEN);
  const decipher = createDecipheriv(ALGO, key, Buffer.from(payload.iv, 'base64'));
  decipher.setAuthTag(Buffer.from(payload.tag, 'base64'));
  const decrypted = Buffer.concat([
    decipher.update(Buffer.from(payload.data, 'base64')),
    decipher.final(),
  ]);
  return JSON.parse(decrypted.toString('utf8')) as T;
}
