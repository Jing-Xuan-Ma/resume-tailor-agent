#!/usr/bin/env bash
# Cursor MCP entrypoint: stdio JSON-RPC on stdout, server logs on stderr (+ file).
# Do not redirect stdout — MCP protocol uses it.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/.debug/logs"
mkdir -p "$LOG_DIR" "$(dirname "${DB_PATH:-$ROOT/data/intercepted.db}")"

export DB_PATH="${DB_PATH:-$ROOT/data/intercepted.db}"
export CDP_ENDPOINT="${CDP_ENDPOINT:-http://127.0.0.1:9222}"

MCP_LOG="$LOG_DIR/mcp-cursor-$(date +%Y%m%d-%H%M%S).log"
ln -sf "$(basename "$MCP_LOG")" "$LOG_DIR/mcp-cursor-latest.log"

if [[ ! -f "$ROOT/dist/mcp/run-server.js" ]]; then
  echo "[run-mcp-stdio] dist missing; building..." >&2
  (cd "$ROOT" && npm run build) >>"$MCP_LOG" 2>&1
fi

# Cursor's MCP spawn PATH often exposes Node 22 (ABI 127). Native addons in
# this repo are compiled by `npm install` against the developer Node (here
# 24 / ABI 137). Prefer that binary so better-sqlite3 can load.
if [[ -z "${NODE_BIN:-}" || ! -x "${NODE_BIN}" ]]; then
  if [[ -x "${HOME}/.local/node/bin/node" ]]; then
    NODE_BIN="${HOME}/.local/node/bin/node"
  else
    NODE_BIN="$(command -v node)"
  fi
fi
export PATH="$(dirname "$NODE_BIN"):${PATH}"

echo "[run-mcp-stdio] starting ghost-driver-mcp" >&2
echo "[run-mcp-stdio]   node=$NODE_BIN ($("$NODE_BIN" -v))" >&2
echo "[run-mcp-stdio]   DB_PATH=$DB_PATH" >&2
echo "[run-mcp-stdio]   CDP_ENDPOINT=$CDP_ENDPOINT" >&2
echo "[run-mcp-stdio]   log=$MCP_LOG" >&2

# Mirror stderr to log file while preserving terminal/stderr for Cursor.
exec 2> >(tee -a "$MCP_LOG" >&2)
cd "$ROOT"
exec "$NODE_BIN" dist/mcp/run-server.js
