#!/usr/bin/env bash
# Start the project: Web (API :8000 + frontend :3000) and Chrome CDP :9222.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

"$ROOT/scripts/dev-up.sh"
bash "$ROOT/mcp/happy-ghost-driver/scripts/dev-env.sh" start --chrome-only

echo
echo "Web     http://127.0.0.1:3000"
echo "API     http://127.0.0.1:8000/health"
echo "Chrome  CDP http://127.0.0.1:9222  (MCP 由 Cursor/CC 按 mcp.json 拉起)"
