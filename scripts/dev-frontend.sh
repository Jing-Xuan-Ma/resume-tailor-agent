#!/usr/bin/env bash
# Foreground Next.js for launchd (KeepAlive). Do not background yourself.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.local/node/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
cd "$ROOT/frontend"
exec npm run dev -- -H 127.0.0.1 -p 3000
