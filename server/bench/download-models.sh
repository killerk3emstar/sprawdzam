#!/usr/bin/env bash
# Download the self-hosted models into ~/models/sprawdzam (outside the repo; never commit weights).
#
#   server/bench/download-models.sh            # whisper + basal
#   server/bench/download-models.sh whisper    # only ggml-large-v3-turbo.bin (1.6 GB)
#   server/bench/download-models.sh basal      # only Remek/basal-1.0-4.5B (9.5 GB) + engine source
#
# Needs the Hugging Face CLI (`brew install huggingface-cli` or `uv tool install huggingface_hub`), git and ~12 GB free.
set -euo pipefail

MODELS_DIR="${MODELS_DIR:-$HOME/models/sprawdzam}"
BASAL_REF="${BASAL_REF:-3fa2eeab2132665f6acd29c1bfa83f10448fd5d0}"   # rkinas/basal main with the MLX/MPS backends
what="${1:-all}"
mkdir -p "$MODELS_DIR"

if [[ "$what" == all || "$what" == whisper ]]; then
  hf download ggerganov/whisper.cpp ggml-large-v3-turbo.bin --local-dir "$MODELS_DIR/whisper"
fi

if [[ "$what" == all || "$what" == basal ]]; then
  hf download Remek/basal-1.0-4.5B --local-dir "$MODELS_DIR/basal-1.0-4.5B"
  if [[ ! -d "$MODELS_DIR/basal-src" ]]; then
    git clone https://github.com/rkinas/basal "$MODELS_DIR/basal-src"
  fi
  git -C "$MODELS_DIR/basal-src" checkout -q "$BASAL_REF"
  # local patch: --share-state (compute the state once per request instead of once per question, ~2.2x faster)
  PATCH="$(cd "$(dirname "$0")" && pwd)/basal/basal-share-state.patch"
  if git -C "$MODELS_DIR/basal-src" apply --reverse --check "$PATCH" 2>/dev/null; then
    echo "basal-share-state.patch already applied"
  else
    git -C "$MODELS_DIR/basal-src" apply "$PATCH"
  fi
  # Python 3.12 venv with PyTorch (MPS) + MLX; no CUDA index on a Mac
  (cd "$MODELS_DIR/basal-src" && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[mlx]")
fi

du -sh "$MODELS_DIR"/* 2>/dev/null || true
