#!/usr/bin/env bash
# Generate the PL/EN voice prompts (macOS `say` + ffmpeg) into $DATA_DIR/prompts (default
# server/data/prompts). The generated audio is not committed. See scripts/make_prompts.py.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run python scripts/make_prompts.py "$@"
