#!/usr/bin/env bash
# Stop Resume Agent API + frontend (launchd KeepAlive off until next login / dev-up).
set -euo pipefail
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"

for label in com.majingxuan.resume-agent.api com.majingxuan.resume-agent.frontend; do
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  launchctl bootout "$DOMAIN" "$HOME/Library/LaunchAgents/${label}.plist" 2>/dev/null || true
done

lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true
lsof -tiTCP:3000 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true

echo "Stopped API :8000 and Frontend :3000"
echo "Note: plists remain; next login (or ./scripts/dev-up.sh / install) will start again."
echo "To remove auto-start entirely: ./scripts/uninstall-launchd-dev.sh"
