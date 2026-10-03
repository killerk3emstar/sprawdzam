#!/usr/bin/env bash
# Generate test speech with macOS `say` and push it through a simulated phone path:
#   TTS (22 kHz) -> 300-3400 Hz band-pass -> 8 kHz mono G.711 mu-law (what Twilio Media Streams deliver)
#   -> back to 16 kHz mono PCM s16le WAV (what whisper.cpp expects).
# Audio is written outside the repo (never commit audio). Requires macOS `say` and ffmpeg.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
AUDIO_DIR="${AUDIO_DIR:-$HOME/models/sprawdzam/audio}"
VOICE_PL="${VOICE_PL:-Zosia}"
VOICE_EN="${VOICE_EN:-Samantha}"
mkdir -p "$AUDIO_DIR"

for txt in "$HERE"/scripts/*.txt; do
  name="$(basename "$txt" .txt)"
  case "$name" in
    pl_*) voice="$VOICE_PL" ;;
    *)    voice="$VOICE_EN" ;;
  esac
  aiff="$AUDIO_DIR/$name.aiff"
  say -v "$voice" -o "$aiff" -f "$txt"
  # phone path: band-limit, resample to 8 kHz, encode mu-law
  ffmpeg -loglevel error -y -i "$aiff" -af "highpass=f=300,lowpass=f=3400" -ar 8000 -ac 1 -c:a pcm_mulaw \
    "$AUDIO_DIR/${name}_8k_ulaw.wav"
  # back to 16 kHz PCM for whisper
  ffmpeg -loglevel error -y -i "$AUDIO_DIR/${name}_8k_ulaw.wav" -ar 16000 -ac 1 -c:a pcm_s16le \
    "$AUDIO_DIR/${name}_16k.wav"
  dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$AUDIO_DIR/${name}_16k.wav")"
  echo "$name ($voice): ${dur}s -> $AUDIO_DIR/${name}_16k.wav"
done
