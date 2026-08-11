#!/usr/bin/env bash
# Restart the launchd-managed Resume Agent API + frontend.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"

if launchctl print "$DOMAIN/com.majingxuan.resume-agent.api" &>/dev/null; then
  launchctl kickstart -k "$DOMAIN/com.majingxuan.resume-agent.api"
  launchctl kickstart -k "$DOMAIN/com.majingxuan.resume-agent.frontend"
else
  exec "$ROOT/scripts/install-launchd-dev.sh"
fi

echo "Restarted. Waiting for health…"
for i in $(seq 1 40); do
  api=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:8000/health 2>/dev/null || echo 0)
  fe=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:3000/jobs 2>/dev/null || echo 0)
  if [ "$api" = "200" ] && [ "$fe" = "200" ]; then
    echo "OK  http://127.0.0.1:3000/jobs"
    exit 0
  fi
  sleep 1
done
echo "Still starting — logs: $ROOT/logs/"
exit 1
