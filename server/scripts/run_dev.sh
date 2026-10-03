#!/usr/bin/env bash
# Run the backend for local development on 127.0.0.1:8765 (port 8000 is basal-serve's).
#
#   scripts/run_dev.sh [--env FILE] [uvicorn args...]
#
# Settings come from ../.env and ./.env (pydantic-settings); `--env FILE` additionally exports
# the variables in FILE (e.g. the untracked server/.env.dev), which take precedence.
# PORT changes the port.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${1:-}" == "--env" ]]; then
  env_file="${2:?--env needs a file}"
  shift 2
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
fi
exec uv run uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8765}" "$@"
