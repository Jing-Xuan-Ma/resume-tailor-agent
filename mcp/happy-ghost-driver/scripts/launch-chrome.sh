#!/usr/bin/env bash
# Launch Chrome with --remote-debugging-port=9222 (macOS / Linux).
# If 9222 is already in use, prints a hint and exits without launching.
#
# macOS: use `open -na` so Chrome is owned by LaunchServices and survives
# when the launching shell / MCP spawn exits (raw binary + `&` does not).
# Linux: setsid + nohup for similar detachment.
# Waits until CDP answers before exiting 0 so callers can connect immediately.
#
# PROFILE PERSISTENCE (account-safety critical)
#   The user-data-dir holds the logged-in session. It lives under $HOME, not
#   $TMPDIR: macOS purges /var/folders periodically, and losing the profile
#   forces a re-login, which sites see as a brand-new device — a high-weight
#   risk signal for a personal account. Keep this directory, and back it up
#   with scripts/backup-profile.sh.
#
#   Chrome 136+ ignores --remote-debugging-port when it points at the default
#   Chrome data directory, so a dedicated profile is the only supported shape.
#   Defaults here must match src/config/paths.ts.

set -euo pipefail

PORT=9222
GHOST_HOME="${GHOST_HOME:-$HOME/.ghost-driver}"
USER_DATA_DIR="${GHOST_PROFILE_DIR:-$GHOST_HOME/chrome-profile}"
BIRTH_MARKER="$USER_DATA_DIR/.ghost-created-at"
CDP_WAIT_SECS="${CDP_WAIT_SECS:-15}"

chrome_args=(
  --remote-debugging-port="$PORT"
  # Allow raw CDP WebSocket clients (python websocket-client, curl, etc.).
  # Without this, non-DevTools origins get Handshake 403 Forbidden.
  --remote-allow-origins=*
  --user-data-dir="$USER_DATA_DIR"
  --disable-blink-features=AutomationControlled
  --disable-features=AutomationControlled
  --disable-infobars
  --no-first-run
  --disable-background-timer-throttling
)

port_listening() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1
  else
    nc -z 127.0.0.1 "$PORT" >/dev/null 2>&1
  fi
}

wait_for_cdp() {
  local deadline=$((SECONDS + CDP_WAIT_SECS))
  while (( SECONDS < deadline )); do
    if port_listening; then
      echo "[launch-chrome] CDP ready at http://127.0.0.1:$PORT"
      return 0
    fi
    sleep 0.4
  done
  echo "[launch-chrome] Timed out waiting for CDP on :$PORT (${CDP_WAIT_SECS}s)." >&2
  return 1
}

# Already up — nothing to do.
if port_listening; then
  echo "[launch-chrome] Port $PORT is already in use. Assuming Chrome is running."
  exit 0
fi

# Stale Singleton* from a dead Chrome blocks a clean relaunch.
rm -f \
  "$USER_DATA_DIR/SingletonLock" \
  "$USER_DATA_DIR/SingletonCookie" \
  "$USER_DATA_DIR/SingletonSocket" \
  2>/dev/null || true

# First run: no profile yet. Record the birth date (the budget guard ramps
# quotas up over a new profile's warm-up window) and tell the user plainly
# that this Chrome starts logged out.
FIRST_RUN=0
if [[ ! -f "$BIRTH_MARKER" ]]; then
  FIRST_RUN=1
fi

mkdir -p "$USER_DATA_DIR"
if [[ "$FIRST_RUN" == "1" ]]; then
  date -u +%Y-%m-%dT%H:%M:%SZ > "$BIRTH_MARKER"
  cat >&2 <<EOF
[launch-chrome] ============================================================
[launch-chrome]  NEW PROFILE CREATED — this Chrome is logged out.
[launch-chrome]    $USER_DATA_DIR
[launch-chrome]
[launch-chrome]  To a site, this is a brand-new device. Before automating:
[launch-chrome]    1. Log in manually, by hand, in this window.
[launch-chrome]    2. Browse normally for a few days (read-only).
[launch-chrome]    3. Only then let the agent perform write actions.
[launch-chrome]
[launch-chrome]  The budget guard enforces reduced quotas during warm-up.
[launch-chrome]  NEVER delete this directory: losing it forces a re-login,
[launch-chrome]  which looks like a new device again. Back it up with:
[launch-chrome]    bash scripts/backup-profile.sh
[launch-chrome] ============================================================
EOF
fi

OS="$(uname -s)"
case "$OS" in
  Darwin)
    if [[ ! -d "/Applications/Google Chrome.app" ]]; then
      echo "[launch-chrome] Google Chrome.app not found." >&2
      exit 1
    fi
    echo "[launch-chrome] Launching via open -na (LaunchServices, stays alive)"
    echo "[launch-chrome]   --remote-debugging-port=$PORT"
    echo "[launch-chrome]   --user-data-dir=$USER_DATA_DIR"
    # -n = new instance; -a = application. Chrome is re-parented to launchd.
    open -na "Google Chrome" --args "${chrome_args[@]}"
    ;;
  Linux)
    CHROME_BIN=""
    for candidate in \
      "google-chrome" \
      "google-chrome-stable" \
      "/usr/bin/google-chrome" \
      "/usr/bin/chromium" \
      "/usr/bin/chromium-browser"; do
      if command -v "$candidate" >/dev/null 2>&1; then
        CHROME_BIN="$candidate"
        break
      fi
    done
    if [[ -z "$CHROME_BIN" ]]; then
      echo "[launch-chrome] Chrome binary not found on Linux." >&2
      exit 1
    fi
    echo "[launch-chrome] Launching: $CHROME_BIN (setsid+nohup)"
    echo "[launch-chrome]   --remote-debugging-port=$PORT"
    echo "[launch-chrome]   --user-data-dir=$USER_DATA_DIR"
    # New session so MCP/agent shell teardown cannot reap Chrome.
    if command -v setsid >/dev/null 2>&1; then
      setsid -f "$CHROME_BIN" "${chrome_args[@]}" >/dev/null 2>&1 || \
        setsid "$CHROME_BIN" "${chrome_args[@]}" >/dev/null 2>&1 &
    else
      nohup "$CHROME_BIN" "${chrome_args[@]}" >/dev/null 2>&1 &
      disown $! 2>/dev/null || true
    fi
    ;;
  *)
    echo "[launch-chrome] Unsupported OS: $OS" >&2
    exit 1
    ;;
esac

wait_for_cdp
