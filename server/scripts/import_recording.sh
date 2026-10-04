#!/usr/bin/env bash
# Import our own voice recording of a caller script as a /dev/caller sample clip.
#
#   scripts/import_recording.sh <input audio (m4a/mp3/wav/caf/...)> <name>
#   scripts/import_recording.sh ~/Downloads/policja.m4a pl_scam_police
#
# Output: $DATA_DIR/samples/<name>.ulaw (default server/data/samples), the exact format
# `/dev/caller`, `scripts/smoke_call.py` and `make_samples.sh` use: raw G.711 mu-law, 8 kHz,
# mono, no header. Processing (ffmpeg): trim leading/trailing silence (pauses inside the
# recording are kept, the segmenter needs them), high-pass 120 Hz (handling noise, hum),
# low-pass 3.4 kHz (phone band), loudness-normalise to about -18 LUFS, resample to 8 kHz.
# An existing clip of the same name (e.g. the macOS TTS one) is moved to samples/tts/ once.
# The audio is not committed (data/ is ignored). Guide for the team: scripts/samples/NAGRANIA.md
#
# System voice prompts (what the protection service says) are imported the same way with their
# prompt name, e.g. `scripts/import_recording.sh ~/Downloads/ostrzezenie.m4a warning_pl`; they go
# to $DATA_DIR/prompts/<name>.ulaw (previous TTS file kept in prompts/tts/). The backend caches
# prompts on first use, so restart it afterwards (scripts/demo-down.sh && scripts/demo-up.sh).
set -euo pipefail
cd "$(dirname "$0")/.."

PROMPTS="warning_pl warning_en password_pl password_en blocked_pl blocked_en"
KNOWN="pl_scam_police pl_scam_grandchild pl_normal_grandchild en_scam_police en_scam_grandchild en_normal_grandchild pl_scam_bank en_scam_bank pl_normal_family en_normal_family"

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <input audio> <name>" >&2
  echo "caller scripts: $KNOWN" >&2
  echo "system prompts: $PROMPTS" >&2
  exit 2
fi
input=$1
name=$2
if [[ ! -f "$input" ]]; then
  echo "error: no such file: $input" >&2
  exit 1
fi
if [[ ! "$name" =~ ^[a-z0-9_]+$ ]]; then
  echo "error: name must be lowercase letters, digits and _ (e.g. pl_scam_police)" >&2
  exit 1
fi
kind=samples
[[ " $PROMPTS " == *" $name "* ]] && kind=prompts
if [[ $kind == samples && " $KNOWN " != *" $name "* ]]; then
  echo "warning: '$name' is not one of the demo clip names, /dev/caller may not list it" >&2
fi
FFMPEG=${FFMPEG:-$(command -v ffmpeg || echo /opt/homebrew/bin/ffmpeg)}
if [[ ! -x "$FFMPEG" ]]; then
  echo "error: ffmpeg not found (brew install ffmpeg)" >&2
  exit 1
fi

out_dir="${DATA_DIR:-data}/$kind"
mkdir -p "$out_dir"
target="$out_dir/$name.ulaw"
if [[ -f "$target" && ! -f "$out_dir/tts/$name.ulaw" ]]; then
  mkdir -p "$out_dir/tts"
  mv "$target" "$out_dir/tts/$name.ulaw"
  echo "kept the previous clip as $out_dir/tts/$name.ulaw"
fi

# Silence trim at both ends: remove leading quiet audio (keeping 0.15 s), then the same on the
# reversed signal for the tail.
trim="silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB:start_silence=0.15"
filters="$trim,areverse,$trim,areverse,highpass=f=120,lowpass=f=3400,loudnorm=I=-18:TP=-2:LRA=11"

tmp="$out_dir/.$name.importing.ulaw"
trap 'rm -f "$tmp"' EXIT
"$FFMPEG" -hide_banner -loglevel error -y -i "$input" -vn -af "$filters" \
  -ar 8000 -ac 1 -f mulaw "$tmp"
bytes=$(wc -c <"$tmp" | tr -d ' ')
if [[ $kind == prompts && "$bytes" -gt 240000 ]]; then
  echo "error: a system prompt must be under 30 s (the backend refuses longer ones)" >&2
  exit 1
fi
if [[ "$bytes" -lt 8000 ]]; then
  echo "error: less than 1 s of audio left after trimming silence (is the recording empty?)" >&2
  exit 1
fi
if [[ "$bytes" -gt 960000 ]]; then
  echo "error: longer than 2 minutes after trimming; /dev/caller ignores such clips" >&2
  exit 1
fi
mv "$tmp" "$target"
trap - EXIT
seconds=$(awk "BEGIN { printf \"%.1f\", $bytes / 8000 }")
echo "$target  ${seconds} s"
if [[ $kind == prompts ]]; then
  echo "restart the backend to use it: scripts/demo-down.sh && scripts/demo-up.sh (from the repo root)"
elif awk "BEGIN { exit !($bytes / 8000 < 20 || $bytes / 8000 > 90) }"; then
  echo "note: demo scripts are usually 40-60 s long" >&2
fi
