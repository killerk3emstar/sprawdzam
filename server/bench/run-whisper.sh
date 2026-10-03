#!/usr/bin/env bash
# Start whisper.cpp's HTTP server (Metal) with large-v3-turbo on this Mac.
# The backend talks to it via WHISPER_URL (default http://host.docker.internal:8080 from inside Docker).
#
#   server/bench/run-whisper.sh            # foreground, port 8080, language pl
#   WHISPER_LANG=en server/bench/run-whisper.sh
#   WHISPER_MODEL=~/models/sprawdzam/whisper/ggml-large-v3-turbo-q5_0.bin server/bench/run-whisper.sh
#
# The default language only applies when a request does not send `language`; the backend should always send it
# (forced from the senior's settings, PL or EN).
set -euo pipefail

WHISPER_BIN_DIR="${WHISPER_BIN_DIR:-/opt/homebrew/opt/whisper.cpp/bin}"
WHISPER_MODEL="${WHISPER_MODEL:-$HOME/models/sprawdzam/whisper/ggml-large-v3-turbo.bin}"
WHISPER_HOST="${WHISPER_HOST:-0.0.0.0}"   # 0.0.0.0 so Docker containers can reach it via host.docker.internal
WHISPER_PORT="${WHISPER_PORT:-8080}"
WHISPER_LANG="${WHISPER_LANG:-pl}"
WHISPER_THREADS="${WHISPER_THREADS:-4}"

if [[ ! -f "$WHISPER_MODEL" ]]; then
  echo "model not found: $WHISPER_MODEL (run server/bench/download-models.sh whisper)" >&2
  exit 1
fi

# --no-timestamps: we only need text; --suppress-nst: drop [music]/(noise) style tokens.
# Temperature fallback stays on (default) because it rescues hallucination loops on noisy phone audio.
exec "$WHISPER_BIN_DIR/whisper-server" \
  --model "$WHISPER_MODEL" \
  --host "$WHISPER_HOST" --port "$WHISPER_PORT" \
  --language "$WHISPER_LANG" \
  --threads "$WHISPER_THREADS" \
  --no-timestamps --suppress-nst \
  "$@"
