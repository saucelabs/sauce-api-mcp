#!/usr/bin/env bash
set -euo pipefail

# cd to repo root (assumes this script lives in repo root)
cd "$(dirname "$0")"

# Load .env if present (API keys, etc.)
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# Ensure deps are ready (fast if already synced)
# Try locked first for reproducibility; fallback if lock missing/outdated.
uv sync --locked || uv sync

# Exec MCP server with any args passed by the client
exec uv run sauce-mcp-rdc-openapi "$@"
