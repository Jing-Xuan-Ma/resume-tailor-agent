import { logger } from '../util/logger.js';
import type { InterceptedRecord, InterceptedRow, InterceptStore, QueryFilter } from './types.js';
import { SqliteInterceptStore } from './sqlite-store.js';

export type { InterceptedRecord, InterceptedRow, QueryFilter, InterceptStore } from './types.js';
export {
  createInterceptStoreFromEnv,
  resolveStoreBackend,
  resolveMysqlConfig,
} from './factory.js';

let activeStore: InterceptStore | null = null;

export function setInterceptStore(store: InterceptStore): void {
  activeStore = store;
}

export function getInterceptStore(): InterceptStore {
  if (!activeStore) {
    throw new Error('Intercept store is not open. Call openDb() or createInterceptStoreFromEnv() first.');
  }
  return activeStore;
}

/** @deprecated Prefer setInterceptStore + SqliteInterceptStore. Kept for unit tests. */
export function openDb(path: string): void {
  if (activeStore) {
    logger.warn('openDb called but a store is already open; closing existing one.');
    void activeStore.close().catch((err: unknown) => {
      logger.warn('failed to close previous store', {
        error: err instanceof Error ? err.message : String(err),
      });
    });
    activeStore = null;
  }
  const store = new SqliteInterceptStore(path);
  store.open();
  activeStore = store;
}

export async function closeDb(): Promise<void> {
  if (activeStore) {
    await activeStore.close();
    activeStore = null;
  }
}

export async function insertIntercepted(record: InterceptedRecord): Promise<void> {
  await getInterceptStore().insert(record);
}

export async function queryIntercepted(filter: QueryFilter): Promise<InterceptedRow[]> {
  return getInterceptStore().query(filter);
}
