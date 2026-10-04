#!/usr/bin/env bash
# Builds the Android demo APK (release, JS bundled, no Metro needed, signed with the local debug key),
# installs it on a phone over USB, connects it to the backend and launches the app.
#
#   app/scripts/install-demo-android.sh [--serial SERIAL] [--no-build] [--url URL]
#
#   --serial   adb serial (default: $ANDROID_SERIAL, else the only connected device)
#   --no-build install the last built APK
#   --url      backend for the app instead of the default ws://localhost:8765/app/control, e.g. a Cloudflare
#              tunnel: --url https://xyz.trycloudflare.com  (set through the sprawdzam://config deep link)
#
# Without --url the phone reaches the Mac's backend on 127.0.0.1:8765 through `adb reverse` (USB).
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERIAL="${ANDROID_SERIAL:-}"
BUILD=1
URL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial) SERIAL="$2"; shift 2 ;;
    --no-build) BUILD=0; shift ;;
    --url) URL="$2"; shift 2 ;;
    -h|--help) sed -n 2,13p "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export JAVA_HOME="${JAVA_HOME_21:-/opt/homebrew/opt/openjdk@21}"
export PATH="/opt/homebrew/opt/node@22/bin:$ANDROID_HOME/platform-tools:$PATH"
ADB=(adb)
[[ -n "$SERIAL" ]] && ADB=(adb -s "$SERIAL")
PKG=pl.sprawdzam.app
APK="$APP_DIR/android/app/build/outputs/apk/release/app-release.apk"

"${ADB[@]}" get-state >/dev/null || { echo "No device (adb devices). Use --serial." >&2; exit 1; }
echo "Device: $("${ADB[@]}" shell getprop ro.product.model | tr -d '\r') (Android $("${ADB[@]}" shell getprop ro.build.version.release | tr -d '\r'))"

if [[ $BUILD == 1 ]]; then
  [[ -d "$APP_DIR/node_modules" ]] || (cd "$APP_DIR" && npm ci)
  echo "Building release APK (arm64-v8a, JS bundled)..."
  (cd "$APP_DIR/android" && ./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a -q)
fi
[[ -f "$APK" ]] || { echo "APK not found: $APK" >&2; exit 1; }

echo "Installing..."
if ! "${ADB[@]}" install -r "$APK"; then
  echo "Install failed (maybe a build signed with another key is installed). Uninstalling and retrying..."
  "${ADB[@]}" uninstall "$PKG" || true
  "${ADB[@]}" install "$APK"
fi

# Permissions the demo needs; SEND_SMS is left to the app (asked after choosing the trusted person).
"${ADB[@]}" shell pm grant "$PKG" android.permission.RECORD_AUDIO || true
"${ADB[@]}" shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS 2>/dev/null || true
# Android 14+: full-screen incoming call over the lock screen.
"${ADB[@]}" shell appops set "$PKG" USE_FULL_SCREEN_INTENT allow 2>/dev/null || true

# Backend on the Mac (127.0.0.1:8765) reachable as localhost:8765 on the phone.
"${ADB[@]}" reverse tcp:8765 tcp:8765

"${ADB[@]}" shell am force-stop "$PKG"
if [[ -n "$URL" ]]; then
  # Cold start with the config link (read by Linking.getInitialURL); the URL is stored in the app settings.
  "${ADB[@]}" shell am start -a android.intent.action.VIEW -d "'sprawdzam://config?url=$URL'" "$PKG" >/dev/null
  echo "Backend set to $URL"
else
  "${ADB[@]}" shell am start -n "$PKG/.MainActivity" >/dev/null
fi
echo "Done. The home screen should turn green (\"Jesteś chroniony\") within a few seconds."
echo "Logs: ${ADB[*]} logcat -s CallEngine"
