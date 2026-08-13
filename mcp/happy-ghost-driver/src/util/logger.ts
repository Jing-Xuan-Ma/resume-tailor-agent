type LogLevel = 'info' | 'warn' | 'error';

function ts(): string {
  return new Date().toISOString();
}

function emit(level: LogLevel, msg: string, meta?: unknown): void {
  const prefix = `[${ts()}] [${level.toUpperCase()}]`;
  // All logs go to stderr. stdout is reserved for the MCP JSON-RPC
  // stream when the server runs over stdio; writing logs there would
  // corrupt the protocol.
  if (meta === undefined) {
    // eslint-disable-next-line no-console
    console.error(`${prefix} ${msg}`);
  } else {
    // eslint-disable-next-line no-console
    console.error(`${prefix} ${msg}`, meta);
  }
}

export const logger = {
  info(msg: string, meta?: unknown): void {
    emit('info', msg, meta);
  },
  warn(msg: string, meta?: unknown): void {
    emit('warn', msg, meta);
  },
  error(msg: string, meta?: unknown): void {
    emit('error', msg, meta);
  },
};
