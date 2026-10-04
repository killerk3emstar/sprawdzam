#!/usr/bin/env bash
# Render the /dev/caller sample clips (macOS `say` + ffmpeg) into $DATA_DIR/samples (default
# server/data/samples). The generated audio is not committed. See scripts/make_samples.py.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run python scripts/make_samples.py "$@"
