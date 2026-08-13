import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { logger } from './util/logger.js';

type DepMap = Record<string, string>;

function readDepVersion(pkgName: string): string {
  // Walk up from this file's compiled location to find the root package.json
  // In dist/, __dirname points to dist/, so the root is one level up.
  const here = dirname(fileURLToPath(import.meta.url));
  const rootPkgPath = resolve(here, '..', 'package.json');
  const rootPkg = JSON.parse(readFileSync(rootPkgPath, 'utf-8')) as {
    dependencies?: DepMap;
    devDependencies?: DepMap;
  };
  const version =
    rootPkg.dependencies?.[pkgName] ?? rootPkg.devDependencies?.[pkgName];
  if (!version) {
    throw new Error(`Package ${pkgName} not declared in package.json`);
  }

  // Read the actual installed version from node_modules
  let installedVersion = 'unknown';
  try {
    const installedPkgPath = resolve(here, '..', 'node_modules', pkgName, 'package.json');
    const installedPkg = JSON.parse(readFileSync(installedPkgPath, 'utf-8')) as {
      version?: string;
    };
    installedVersion = installedPkg.version ?? 'unknown';
  } catch {
    installedVersion = 'not-installed';
  }
  return installedVersion;
}

function main(): void {
  const deps = [
    'playwright-core',
    'better-sqlite3',
    '@modelcontextprotocol/sdk',
    'ghost-cursor',
    'zod',
  ];

  logger.info(`Node version: ${process.version}`);
  logger.info('Dependency versions (installed):');
  for (const dep of deps) {
    const v = readDepVersion(dep);
    logger.info(`  ${dep}@${v}`);
  }
  logger.info('P0 OK');
}

main();
