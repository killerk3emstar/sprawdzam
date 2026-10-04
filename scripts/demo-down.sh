#!/usr/bin/env bash
# Stop what scripts/demo-up.sh started: tunnel, USB watcher, backend.
# Model servers keep running (they take minutes to load); add --all to stop them too.
set -euo pipefail

STATE="${SPRAWDZAM_DEMO_DIR:-${TMPDIR:-/tmp}/sprawdzam-demo}"
names=(tunnel adb-watch backend)
[[ "${1:-}" == "--all" ]] && names+=(basal whisper)

for name in "${names[@]}"; do
  pidfile="$STATE/$name.pid"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    pid="$(cat "$pidfile")"
    pkill -P "$pid" 2>/dev/null || true # children (uvicorn under uv, exec'd servers)
    kill "$pid" 2>/dev/null || true
    echo "stopped $name"
  fi
  rm -f "$pidfile"
done
