#!/usr/bin/env bash
# Bring up the whole live demo on the Mac, reusing whatever already runs:
#   1. model servers (whisper.cpp on :8080, basal-1 on :8000)
#   2. backend on :8765 (server/.env.dev)
#   3. USB link to the senior's Android phone (adb reverse tcp:8765, kept alive by a watcher)
#   4. Cloudflare quick tunnel for the scammer's iPhone (https, random address)
#   5. opens the start page (QR code for the iPhone) and the jury console
#
#   scripts/demo-up.sh                 # everything
#   scripts/demo-up.sh --new-tunnel    # force a fresh tunnel address
#   ANDROID_SERIAL=XXXX scripts/demo-up.sh
# Stop with scripts/demo-down.sh. Logs and pid files: $TMPDIR/sprawdzam-demo/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="${SPRAWDZAM_DEMO_DIR:-${TMPDIR:-/tmp}/sprawdzam-demo}"
mkdir -p "$STATE"
NEW_TUNNEL=0
[[ "${1:-}" == "--new-tunnel" ]] && NEW_TUNNEL=1

say() { printf '\033[1m▸ %s\033[0m\n' "$*"; }
ok() { printf '  \033[32mok\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!!\033[0m %s\n' "$*"; }
listening() { lsof -tiTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
alive() { [[ -f "$STATE/$1.pid" ]] && kill -0 "$(cat "$STATE/$1.pid")" 2>/dev/null; }
start_bg() { # name, command...
  local name="$1"; shift
  nohup "$@" >"$STATE/$name.log" 2>&1 &
  echo $! >"$STATE/$name.pid"
}
wait_port() { # port, seconds, name
  for _ in $(seq 1 "$2"); do listening "$1" && return 0; sleep 1; done
  warn "$3 is not listening on :$1 after $2 s (log: $STATE/$3.log)"; return 1
}

say "1/5 Model servers"
if listening 8080; then ok "whisper already on :8080"; else
  start_bg whisper "$ROOT/server/bench/run-whisper.sh"; wait_port 8080 60 whisper && ok "whisper started"; fi
if listening 8000; then ok "basal-1 already on :8000"; else
  start_bg basal "$ROOT/server/bench/run-basal.sh"; wait_port 8000 240 basal && ok "basal-1 started"; fi

say "2/5 Backend"
cd "$ROOT/server"
if [[ ! -f .env.dev ]]; then
  warn "server/.env.dev is missing: copy .env.example to server/.env.dev and fill it in (see README)"; exit 1
fi
[[ -n "$(ls data/prompts/*.ulaw 2>/dev/null)" ]] || { warn "generating voice prompts"; scripts/make_prompts.sh >/dev/null; }
[[ -n "$(ls data/samples/*.ulaw 2>/dev/null)" ]] || { warn "generating demo scripts (TTS)"; scripts/make_samples.sh >/dev/null; }
if listening 8765; then ok "backend already on :8765"; else
  start_bg backend scripts/run_dev.sh --env .env.dev; wait_port 8765 60 backend && ok "backend started"; fi
health=""
for _ in $(seq 1 30); do # until both model warm-ups have finished
  health="$(curl -s -m 2 http://127.0.0.1:8765/health || true)"
  [[ -n "$health" && "$health" != *'"warmup":"pending"'* ]] && break; sleep 1
done
python3 - "$health" <<'EOF'
import json, sys
try:
    h = json.loads(sys.argv[1])
except Exception:
    print("  !! backend /health did not answer"); sys.exit(0)
m = h["models"]
print(f"  stt warmup: {m['stt']['warmup']}  decision warmup: {m['decision']['warmup']}  "
      f"prompts: {all(h['voice_prompts'].values())}  dry_run: {h['limits']['dry_run']}")
EOF
if alive keep-warm; then ok "keep-warm already running"; else
  # Pings both models every 30 s between calls so macOS does not page the weights out.
  start_bg keep-warm bash -c 'set -a; source .env.dev; set +a; exec uv run python scripts/keep_warm.py --every 30'
  ok "keep-warm started (models stay in memory between calls)"
fi
cd "$ROOT"

say "3/5 Android phone (USB)"
SERIAL="${ANDROID_SERIAL:-$(adb devices | awk 'NR>1 && $2=="device" && $1!~/^emulator/ {print $1; exit}')}"
if [[ -z "$SERIAL" ]]; then
  warn "no physical Android phone over USB (plug it in, allow USB debugging), skipping"
else
  adb -s "$SERIAL" reverse tcp:8765 tcp:8765 >/dev/null
  ok "adb reverse tcp:8765 on $SERIAL ($(adb -s "$SERIAL" shell getprop ro.product.model | tr -d '\r'))"
  if alive adb-watch; then ok "USB watcher already running"; else
    start_bg adb-watch bash -c "while true; do adb -s '$SERIAL' reverse --list 2>/dev/null | grep -q tcp:8765 || { adb -s '$SERIAL' reverse tcp:8765 tcp:8765 >/dev/null 2>&1 && echo \"\$(date +%T) reverse restored\"; }; sleep 5; done"
    ok "USB watcher started (re-adds the port link every 5 s if the cable blips)"
  fi
  # The emulator shares the device token and can steal calls meant for the phone.
  adb devices | awk 'NR>1 && $1~/^emulator/ {print $1}' | while read -r emu; do
    adb -s "$emu" shell am force-stop pl.sprawdzam.app >/dev/null 2>&1 && warn "stopped the app on $emu (it would compete for calls)"
  done
fi

say "4/5 Tunnel for the iPhone"
URL=""
if [[ $NEW_TUNNEL == 0 ]] && alive tunnel; then
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$STATE/tunnel.log" | head -1 || true)"
fi
if [[ -z "$URL" ]]; then
  alive tunnel && kill "$(cat "$STATE/tunnel.pid")" 2>/dev/null || true
  start_bg tunnel cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8765
  for _ in $(seq 1 30); do
    URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$STATE/tunnel.log" | head -1 || true)"
    [[ -n "$URL" ]] && break; sleep 1
  done
fi
if [[ -z "$URL" ]]; then
  warn "no tunnel address (log: $STATE/tunnel.log). Fallback: run the caller page on this Mac."
else
  # Check through a public resolver: asking the local (hotspot) DNS before the name exists
  # makes it cache "no such host" for a while. Phones use their own resolver.
  host="${URL#https://}"; code=000
  for _ in $(seq 1 20); do
    ip="$(dig +short "$host" @1.1.1.1 2>/dev/null | head -1)"
    [[ -n "$ip" ]] && code="$(curl -s -m 5 -o /dev/null -w '%{http_code}' --resolve "$host:443:$ip" "$URL/health" || true)"
    [[ "$code" == 200 ]] && break; sleep 1
  done
  [[ "$code" == 200 ]] && ok "$URL" || warn "$URL does not answer yet (HTTP $code); give it a minute"
fi

say "5/5 Pages"
START="http://127.0.0.1:8765/dev/${URL:+?base=$URL}"
JURY="http://127.0.0.1:8765/dev/jury"
open "$JURY" || true
open "$START" || true
cat <<EOF

  Jury console (projector):   $JURY
  Start page with QR:         $START
  Scammer iPhone (Safari):    ${URL:-<no tunnel>}/dev/caller
  Logs:                       $STATE/
  Stop:                       scripts/demo-down.sh
EOF
