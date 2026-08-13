#!/usr/bin/env bash
# Daily / multi-run scrape driven by config/intern-list.toml
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/backend/.venv/bin/python"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/scrape_${STAMP}.log"

{
  echo "=== intern-list scrape ${STAMP} ==="
  echo "python=$PYTHON"
  cd "$ROOT/backend"
  "$PYTHON" -m app.modules.intern_list_scraper --config "$ROOT/config/intern-list.toml" --targets
} 2>&1 | tee -a "$LOG_FILE"
