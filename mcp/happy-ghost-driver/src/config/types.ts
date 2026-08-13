export interface AppStoreConfig {
  backend: 'sqlite' | 'mysql';
  sqlite?: {
    path?: string;
  };
  mysql?: {
    host?: string;
    port?: number;
    user?: string;
    password?: string;
    database?: string;
  };
}

export interface AppConfig {
  store: AppStoreConfig;
}

export interface EncryptedPayload {
  v: 1;
  iv: string;
  tag: string;
  data: string;
}
