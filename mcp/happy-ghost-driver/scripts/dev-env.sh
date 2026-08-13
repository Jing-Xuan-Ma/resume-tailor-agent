#!/usr/bin/env bash
# Orchestrate Chrome (CDP :9222) and optional standalone MCP for local debugging.
# Usage: scripts/dev-env.sh {start|stop|restart|status|logs} [--chrome-only|--mcp-only]

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEBUG_DIR="$ROOT/.debug"
LOG_DIR="$DEBUG_DIR/logs"
STATE_DIR="$DEBUG_DIR/state"
DEV_ENV_LOG="$LOG_DIR/dev-env.log"
MCP_PID_FILE="$STATE_DIR/mcp-standalone.pid"
CHROME_PORT=9222
# Match the exact --user-data-dir flag launch-chrome.sh passes. The profile now
# lives under $HOME, so matching on a bare directory name would both miss our
# Chrome and risk matching unrelated processes. Defaults must stay in sync with
# scripts/launch-chrome.sh and src/config/paths.ts.
GHOST_HOME="${GHOST_HOME:-$HOME/.ghost-driver}"
CHROME_PROFILE_DIR="${GHOST_PROFILE_DIR:-$GHOST_HOME/chrome-profile}"
CHROME_PROFILE_MARKER="--user-data-dir=$CHROME_PROFILE_DIR"
CDP_ENDPOINT="${CDP_ENDPOINT:-http://127.0.0.1:$CHROME_PORT}"
DB_PATH="${DB_PATH:-$ROOT/data/intercepted.db}"

mkdir -p "$LOG_DIR" "$STATE_DIR" "$(dirname "$DB_PATH")"

log() {
  local level="$1"
  shift
  local ts
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  local line="[$ts] [$level] $*"
  echo "$line" | tee -a "$DEV_ENV_LOG"
}

usage() {
  cat <<EOF
Usage: scripts/dev-env.sh {start|stop|restart|status|logs} [--chrome-only|--mcp-only]

Commands:
  start    Start Chrome (9222) and/or standalone MCP
  stop     Stop Chrome debug profile and/or standalone MCP
  restart  stop then start
  status   Print port, CDP, build, and process health
  logs     Tail recent dev logs (dev-env + mcp-latest)

Options:
  --chrome-only   Only manage Chrome
  --mcp-only      Only manage standalone MCP (Cursor uses its own MCP spawn)

Env overrides:
  CDP_ENDPOINT  default: http://127.0.0.1:9222
  DB_PATH       default: \$ROOT/data/intercepted.db

Logs:  $LOG_DIR/
State: $STATE_DIR/
EOF
}

port_listening() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$CHROME_PORT" -sTCP:LISTEN >/dev/null 2>&1
  else
    nc -z 127.0.0.1 "$CHROME_PORT" >/dev/null 2>&1
  fi
}

cdp_reachable() {
  curl -sf --max-time 2 "$CDP_ENDPOINT/json/version" >/dev/null 2>&1
}

ensure_build() {
  if [[ ! -f "$ROOT/dist/mcp/run-server.js" ]]; then
    log INFO "dist/ missing; running npm run build"
    (cd "$ROOT" && npm run build) >>"$DEV_ENV_LOG" 2>&1
  fi
}

start_chrome() {
  if port_listening; then
    log INFO "Chrome CDP port $CHROME_PORT already listening; skip launch"
    return 0
  fi
  log INFO "Starting Chrome via scripts/launch-chrome.sh"
  local chrome_log="$LOG_DIR/chrome-$(date +%Y%m%d-%H%M%S).log"
  ln -sf "$(basename "$chrome_log")" "$LOG_DIR/chrome-latest.log"
  bash "$ROOT/scripts/launch-chrome.sh" >>"$chrome_log" 2>&1 || true
  local i
  for i in {1..20}; do
    if cdp_reachable; then
      log INFO "Chrome CDP ready at $CDP_ENDPOINT"
      return 0
    fi
    sleep 0.5
  done
  log ERROR "Chrome did not become reachable on $CDP_ENDPOINT within 10s"
  log ERROR "See $LOG_DIR/chrome-latest.log"
  return 1
}

stop_chrome() {
  if ! port_listening; then
    log INFO "Chrome CDP port $CHROME_PORT not listening; nothing to stop"
    return 0
  fi
  log INFO "Stopping Chrome instances with profile marker: $CHROME_PROFILE_MARKER"
  if command -v pkill >/dev/null 2>&1; then
    pkill -f "$CHROME_PROFILE_MARKER" 2>/dev/null || true
    sleep 1
  fi
  if port_listening && command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -tiTCP:"$CHROME_PORT" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      log WARN "Force killing PID(s) on port $CHROME_PORT: $pids"
      kill $pids 2>/dev/null || true
    fi
  fi
  if port_listening; then
    log ERROR "Port $CHROME_PORT still in use after stop"
    return 1
  fi
  log INFO "Chrome debug instance stopped"
}

start_mcp_standalone() {
  if [[ -f "$MCP_PID_FILE" ]]; then
    local old_pid
    old_pid="$(cat "$MCP_PID_FILE")"
    if kill -0 "$old_pid" 2>/dev/null; then
      log INFO "Standalone MCP already running (PID $old_pid)"
      return 0
    fi
    rm -f "$MCP_PID_FILE"
  fi
  ensure_build
  local mcp_log="$LOG_DIR/mcp-standalone-$(date +%Y%m%d-%H%M%S).log"
  ln -sf "$(basename "$mcp_log")" "$LOG_DIR/mcp-standalone-latest.log"
  log INFO "Starting standalone MCP (stdio test / manual debug)"
  log INFO "  DB_PATH=$DB_PATH"
  log INFO "  CDP_ENDPOINT=$CDP_ENDPOINT"
  log INFO "  log=$mcp_log"
  (
    export DB_PATH CDP_ENDPOINT
    cd "$ROOT"
    exec node dist/mcp/run-server.js
  ) >>"$mcp_log" 2>&1 &
  echo $! >"$MCP_PID_FILE"
  sleep 0.5
  if kill -0 "$(cat "$MCP_PID_FILE")" 2>/dev/null; then
    log INFO "Standalone MCP started (PID $(cat "$MCP_PID_FILE"))"
  else
    log ERROR "Standalone MCP failed to start; see $LOG_DIR/mcp-standalone-latest.log"
    rm -f "$MCP_PID_FILE"
    return 1
  fi
}

stop_mcp_standalone() {
  if [[ ! -f "$MCP_PID_FILE" ]]; then
    log INFO "No standalone MCP PID file; skip"
    return 0
  fi
  local pid
  pid="$(cat "$MCP_PID_FILE")"
  if kill -0 "$pid" 2>/dev/null; then
    log INFO "Stopping standalone MCP (PID $pid)"
    kill -TERM "$pid" 2>/dev/null || true
    sleep 1
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$MCP_PID_FILE"
  log INFO "Standalone MCP stopped"
}

cmd_status() {
  echo "=== ghost-driver dev environment ==="
  echo "project:      $ROOT"
  echo "CDP_ENDPOINT: $CDP_ENDPOINT"
  echo "DB_PATH:      $DB_PATH"
  echo ""
  if port_listening; then
    echo "chrome:       LISTENING :$CHROME_PORT"
  else
    echo "chrome:       STOPPED"
  fi
  if cdp_reachable; then
    local ver
    ver="$(curl -sf --max-time 2 "$CDP_ENDPOINT/json/version" | head -c 200 || true)"
    echo "cdp:          OK  $ver"
  else
    echo "cdp:          UNREACHABLE"
  fi
  if [[ -f "$ROOT/dist/mcp/run-server.js" ]]; then
    echo "build:        OK  dist/mcp/run-server.js"
  else
    echo "build:        MISSING (run npm run build)"
  fi
  if [[ -f "$MCP_PID_FILE" ]] && kill -0 "$(cat "$MCP_PID_FILE")" 2>/dev/null; then
    echo "mcp(standalone): RUNNING PID $(cat "$MCP_PID_FILE")"
  else
    echo "mcp(standalone): STOPPED"
  fi
  echo "mcp(cursor):  managed by Cursor via .cursor/mcp.json (not this script)"
  echo ""
  echo "logs:"
  echo "  dev-env:           $DEV_ENV_LOG"
  echo "  mcp-cursor-latest: $LOG_DIR/mcp-cursor-latest.log"
  echo "  chrome-latest:     $LOG_DIR/chrome-latest.log"
  log INFO "status checked"
}

cmd_logs() {
  echo "--- dev-env.log (last 40 lines) ---"
  tail -n 40 "$DEV_ENV_LOG" 2>/dev/null || echo "(empty)"
  echo ""
  if [[ -f "$LOG_DIR/mcp-cursor-latest.log" ]]; then
    echo "--- mcp-cursor-latest.log (last 40 lines) ---"
    tail -n 40 "$LOG_DIR/mcp-cursor-latest.log"
  fi
  if [[ -f "$LOG_DIR/chrome-latest.log" ]]; then
    echo ""
    echo "--- chrome-latest.log (last 20 lines) ---"
    tail -n 20 "$LOG_DIR/chrome-latest.log"
  fi
}

CMD="${1:-}"
SCOPE="all"
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --chrome-only) SCOPE="chrome" ;;
    --mcp-only) SCOPE="mcp" ;;
    *) usage; exit 1 ;;
  esac
  shift
done

case "$CMD" in
  start)
    log INFO "=== dev-env start (scope=$SCOPE) ==="
    [[ "$SCOPE" == "all" || "$SCOPE" == "chrome" ]] && start_chrome
    [[ "$SCOPE" == "all" || "$SCOPE" == "mcp" ]] && start_mcp_standalone
    cmd_status
    ;;
  stop)
    log INFO "=== dev-env stop (scope=$SCOPE) ==="
    [[ "$SCOPE" == "all" || "$SCOPE" == "mcp" ]] && stop_mcp_standalone
    [[ "$SCOPE" == "all" || "$SCOPE" == "chrome" ]] && stop_chrome
    cmd_status
    ;;
  restart)
    log INFO "=== dev-env restart (scope=$SCOPE) ==="
    extra=()
    case "$SCOPE" in
      chrome) extra=(--chrome-only) ;;
      mcp) extra=(--mcp-only) ;;
    esac
    bash "$0" stop "${extra[@]}"
    bash "$0" start "${extra[@]}"
    ;;
  status) cmd_status ;;
  logs) cmd_logs ;;
  *)
    usage
    exit 1
    ;;
esac
