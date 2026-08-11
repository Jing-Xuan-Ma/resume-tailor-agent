#!/usr/bin/env bash
# Remove login auto-start for Resume Agent API + frontend.
set -euo pipefail
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"
PLIST_DIR="$HOME/Library/LaunchAgents"

for label in com.majingxuan.resume-agent.api com.majingxuan.resume-agent.frontend; do
  plist="$PLIST_DIR/${label}.plist"
  launchctl bootout "$DOMAIN" "$plist" 2>/dev/null || true
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  rm -f "$plist"
  echo "Removed ${label}"
done

lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true
lsof -tiTCP:3000 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true

echo "Auto-start disabled. Ports 8000/3000 freed."
