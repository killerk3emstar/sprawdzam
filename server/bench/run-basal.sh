#!/usr/bin/env bash
# Start basal-serve (POST /v1/systemone) with basal-1.0-4.5B on this Mac.
# The backend talks to it via BASAL_URL (default http://host.docker.internal:8000 from inside Docker).
#
#   server/bench/run-basal.sh                    # mode mps (Apple GPU via PyTorch MPS, bf16) + --share-state, port 8000
#   BASAL_MODE=mlx server/bench/run-basal.sh     # MLX: same latency here, but the server's footprint grew to 20-33 GB
#   BASAL_MODE=eager server/bench/run-basal.sh   # plain PyTorch reference (slowest, ignores --share-state)
#   BASAL_SHARE_STATE=0 server/bench/run-basal.sh   # upstream behaviour (state recomputed for every question)
#   BASAL_MODEL=~/models/sprawdzam/basal-1.0-1.5B server/bench/run-basal.sh   # lite model
#
# Install first: server/bench/download-models.sh basal
set -euo pipefail

MODELS_DIR="${MODELS_DIR:-$HOME/models/sprawdzam}"
BASAL_SRC="${BASAL_SRC:-$MODELS_DIR/basal-src}"
BASAL_MODEL="${BASAL_MODEL:-$MODELS_DIR/basal-1.0-4.5B}"
BASAL_MODE="${BASAL_MODE:-mps}"
BASAL_SHARE_STATE="${BASAL_SHARE_STATE:-1}"   # needs basal/basal-share-state.patch (applied by download-models.sh)
BASAL_HOST="${BASAL_HOST:-127.0.0.1}"   # localhost only (public hackathon Wi-Fi); set 0.0.0.0 only if Docker cannot reach it via host.docker.internal, and keep the macOS firewall on
BASAL_PORT="${BASAL_PORT:-8000}"

if [[ ! -x "$BASAL_SRC/.venv/bin/basal-serve" ]]; then
  echo "basal-serve not installed in $BASAL_SRC/.venv (run server/bench/download-models.sh basal)" >&2
  exit 1
fi
if [[ ! -f "$BASAL_MODEL/model.safetensors" ]]; then
  echo "weights not found in $BASAL_MODEL (run server/bench/download-models.sh basal)" >&2
  exit 1
fi

extra=()
if [[ "$BASAL_SHARE_STATE" == 1 ]]; then
  extra+=(--share-state)
fi

# --name keeps the reported model name stable when --model is a local path
exec "$BASAL_SRC/.venv/bin/basal-serve" \
  --model "$BASAL_MODEL" --name "$(basename "$BASAL_MODEL")" \
  --mode "$BASAL_MODE" \
  --host "$BASAL_HOST" --port "$BASAL_PORT" \
  ${extra[@]+"${extra[@]}"} "$@"
