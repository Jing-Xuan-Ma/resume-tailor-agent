#!/usr/bin/env bash
# Foreground API for launchd (KeepAlive). Do not background yourself.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
exec "$ROOT/backend/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
