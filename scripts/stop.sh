#!/usr/bin/env bash
# Stop Web and the ghost-driver Chrome (does not touch your daily Chrome).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

"$ROOT/scripts/dev-down.sh"
bash "$ROOT/mcp/happy-ghost-driver/scripts/dev-env.sh" stop --chrome-only || true
