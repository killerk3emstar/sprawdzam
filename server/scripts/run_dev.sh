#!/usr/bin/env bash
# Run the backend for local development on 127.0.0.1:8765 (port 8000 is basal-serve's).
# Settings come from ../.env (copy ../.env.example). Extra arguments go to uvicorn.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8765}" "$@"
