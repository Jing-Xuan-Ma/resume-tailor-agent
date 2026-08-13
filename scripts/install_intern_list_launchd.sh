#!/usr/bin/env bash
# Install / refresh macOS launchd timers from config/intern-list.toml schedule_hours.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL_PREFIX="com.majingxuan.intern-list-scrape"
PLIST_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$PLIST_DIR" "$ROOT/logs"

shopt -s nullglob
for f in "$PLIST_DIR"/${LABEL_PREFIX}*.plist; do
  launchctl bootout "gui/$(id -u)" "$f" 2>/dev/null || true
  rm -f "$f"
done
shopt -u nullglob

HOURS_FILE="$ROOT/logs/.schedule_hours.txt"
"$ROOT/backend/.venv/bin/python" -c "
import tomllib
from pathlib import Path
cfg = tomllib.loads(Path('$ROOT/config/intern-list.toml').read_text())
scrape = cfg.get('scrape', cfg)
hours = scrape.get('schedule_hours') or [9]
times = int(scrape.get('times_per_day') or len(hours) or 1)
hours = list(hours)[:times]
Path('$HOURS_FILE').write_text(' '.join(str(int(h)) for h in hours))
print('schedule_hours=', ' '.join(str(int(h)) for h in hours))
"

HOURS=$(cat "$HOURS_FILE")
IDX=0
for HOUR in $HOURS; do
  LABEL="${LABEL_PREFIX}.${IDX}"
  PLIST="$PLIST_DIR/${LABEL}.plist"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${ROOT}/scripts/run_scheduled_intern_list_scrape.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>${HOUR}</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>StandardOutPath</key>
  <string>${ROOT}/logs/launchd_${IDX}.out.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/logs/launchd_${IDX}.err.log</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
EOF
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "Installed ${LABEL} at hour ${HOUR}:00"
  IDX=$((IDX + 1))
done

echo "Done. Edit config/intern-list.toml schedule_hours then re-run this script."
