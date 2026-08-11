#!/usr/bin/env bash
# Install LaunchAgents so API (:8000) + frontend (:3000) start at login and stay up.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$ROOT/logs"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"
mkdir -p "$PLIST_DIR" "$LOG_DIR"
chmod +x "$ROOT/scripts/dev-api.sh" "$ROOT/scripts/dev-frontend.sh" "$ROOT/scripts/dev-up.sh" "$ROOT/scripts/dev-down.sh"

# Free ports so launchd can bind cleanly
lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true
lsof -tiTCP:3000 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true
sleep 1

install_one() {
  local label="$1"
  local script="$2"
  local out_log="$3"
  local err_log="$4"
  local plist="$PLIST_DIR/${label}.plist"

  launchctl bootout "$DOMAIN" "$plist" 2>/dev/null || true
  launchctl bootout "$DOMAIN" "$label" 2>/dev/null || true

  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${script}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>StandardOutPath</key>
  <string>${out_log}</string>
  <key>StandardErrorPath</key>
  <string>${err_log}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>${HOME}/.local/node/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>
</dict>
</plist>
EOF

  launchctl bootstrap "$DOMAIN" "$plist"
  launchctl enable "$DOMAIN/${label}" 2>/dev/null || true
  launchctl kickstart -k "$DOMAIN/${label}" 2>/dev/null || true
  echo "Installed ${label}"
}

install_one \
  "com.majingxuan.resume-agent.api" \
  "$ROOT/scripts/dev-api.sh" \
  "$LOG_DIR/api.out.log" \
  "$LOG_DIR/api.err.log"

install_one \
  "com.majingxuan.resume-agent.frontend" \
  "$ROOT/scripts/dev-frontend.sh" \
  "$LOG_DIR/frontend.out.log" \
  "$LOG_DIR/frontend.err.log"

echo
echo "Waiting for health…"
ok=0
for i in $(seq 1 40); do
  api=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:8000/health 2>/dev/null || echo 0)
  fe=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:3000/jobs 2>/dev/null || echo 0)
  if [ "$api" = "200" ] && [ "$fe" = "200" ]; then
    ok=1
    break
  fi
  sleep 1
done

if [ "$ok" = "1" ]; then
  echo "OK  API       http://127.0.0.1:8000"
  echo "OK  Frontend  http://127.0.0.1:3000/jobs"
else
  echo "WARN  still warming up — check logs:"
  echo "  $LOG_DIR/api.err.log"
  echo "  $LOG_DIR/frontend.err.log"
fi

echo
echo "Login auto-start: ON (RunAtLoad + KeepAlive)"
echo "Manual:"
echo "  $ROOT/scripts/dev-up.sh     # start / restart"
echo "  $ROOT/scripts/dev-down.sh   # stop (until next login or dev-up)"
echo "  $ROOT/scripts/uninstall-launchd-dev.sh  # remove auto-start"
