export interface InterceptedRecord {
  url: string;
  status: number | null;
  content_type: string | null;
  body: string;
}

export interface InterceptedRow {
  id: number;
  url: string;
  status: number | null;
  content_type: string | null;
  body: string;
  ts: number;
}

export interface QueryFilter {
  urlPattern: string;
  limit?: number;
  sinceTs?: number;
}

export const DEFAULT_QUERY_LIMIT = 50;
export const MAX_QUERY_LIMIT = 500;

export function clampQueryLimit(requested: number | undefined): number {
  const n = requested ?? DEFAULT_QUERY_LIMIT;
  return Math.min(Math.max(1, n), MAX_QUERY_LIMIT);
}

/**
 * Pluggable persistence for intercepted network responses.
 * SQLite is sync under the hood; MySQL is async — callers always await.
 */
export interface InterceptStore {
  insert(record: InterceptedRecord): Promise<void>;
  query(filter: QueryFilter): Promise<InterceptedRow[]>;
  /**
   * Delete rows older than `cutoffTs`, returning how many were removed.
   *
   * Captured bodies are responses from logged-in sessions, so keeping them
   * forever turns a debugging convenience into an indefinite archive of
   * personal data. Retention is bounded on purpose.
   */
  purgeOlderThan(cutoffTs: number): Promise<number>;
  close(): Promise<void>;
}
