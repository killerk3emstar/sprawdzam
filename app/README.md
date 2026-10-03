# Sprawdzam / Second Ear: mobile app

One React Native code base for two targets:

- **HarmonyOS** through React Native for OpenHarmony (RNOH), packaged as a `.hap` (Huawei challenge target)
- **Android**

The current screen is a hello world plus a CallEngine developer panel. Real senior-facing screens and the remaining native modules (contacts, notifications, widget) come next.

## Versions

| Component | Version |
| --- | --- |
| macOS | Apple Silicon (DevEco Studio emulator requires Apple Silicon) |
| Node.js | 22.x (tested with 22.23.3, npm 10.9.9); see `.nvmrc` |
| React Native | 0.77.1 (React 18.3.1) |
| RNOH | `@react-native-oh/react-native-harmony` 0.77.75, `@react-native-oh/react-native-harmony-cli` 0.77.75 (exact pins) |
| DevEco Studio | 6.1.1.280 (bundled HarmonyOS SDK 6.1.1.125 = API 24, hvigor 6.24.2, ohpm 6.1.2.268, hdc 3.2.0d) |
| HarmonyOS product | `runtimeOS: HarmonyOS`, `compatibleSdkVersion: 6.0.0(20)`, `compileSdkVersion` and `targetSdkVersion: 6.1.1(24)` |
| HarmonyOS bundle name | `pl.sprawdzam.app` |
| Android | JDK 21 (Homebrew `openjdk@21`), Android SDK platform 35, build-tools 35.0.0, NDK 27.1.12297006, Gradle 8.10.2 |

## Environment

```bash
# Node 22 (the RN 0.77 toolchain is not tested on newer Node majors)
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"

# HarmonyOS tools from DevEco Studio: hdc, ohpm, hvigorw
export DEVECO_SDK_HOME="/Applications/DevEco-Studio.app/Contents/sdk"
export PATH="$DEVECO_SDK_HOME/default/openharmony/toolchains:/Applications/DevEco-Studio.app/Contents/tools/ohpm/bin:/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin:$PATH"

# Android
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
export ANDROID_HOME=$HOME/Library/Android/sdk
```

## First-time setup

```bash
cd app
npm ci

# build-profile.json5 holds per-developer signing configs, so it is not committed.
# Create it from the committed template (same SDK versions, empty signingConfigs).
cp harmony/build-profile.template.json5 harmony/build-profile.json5
```

## HarmonyOS

### 1. JS bundle

```bash
cd app
npm run bundle:harmony           # dev JS bundle -> harmony/entry/src/main/resources/rawfile/bundle.harmony.js
```

`harmony/entry/src/main/ets/pages/Index.ets` loads the bundle in this order: Metro (debug builds only), `rawfile/hermes_bundle.hbc`, `rawfile/bundle.harmony.js`. The bundle is copied into the HAP at build time, so run this step before step 2.

`npm run bundle:harmony:release` produces minified Hermes bytecode (`rawfile/hermes_bundle.hbc`) with the `hermesc` shipped in `react-native`. It is not yet tested on a device (the bytecode version must match the Hermes inside RNOH). If both files are present, the `.hbc` wins; delete it to go back to the JS bundle.

### 2. Build the HAP from the command line

```bash
cd app/harmony
ohpm install --all
hvigorw assembleHap --mode module -p module=entry@default -p product=default -p buildMode=debug -p requiredDeviceType=phone --no-daemon
```

Output: `app/harmony/entry/build/default/outputs/default/entry-default-unsigned.hap` (about 40 MB in debug, arm64-v8a native libs).
The first build compiles the RNOH C++ core and takes about 1.5 minutes on an M4 Pro; later builds are incremental.

During the build the RNOH hvigor plugin runs codegen and autolinking (generated files are git-ignored) and tries to forward the Metro port with `hdc rport`. Without a connected device it logs `[metro] [Fail]ExecuteCommand need connect-key`, which is harmless. It also logs `ERROR: 00303137 ... No npmrc file is matched` while installing its own pnpm; the build continues and this can be ignored.

Known quirks:

- **Keep the checkout path short.** hvigor installs the RNOH plugin through pnpm, whose cache file name contains the full path to `node_modules/@react-native-oh/react-native-harmony-cli/harmony/rnoh-hvigor-plugin-0.77.75.tgz`. A deep checkout fails with `ERR_PNPM_ENAMETOOLONG` / `00308002 Operation Error` (observed with a 120-character path; `/Users/<you>/Dev/HackYeah/2026/sprawdzam-app` works).
- **`harmony/oh-package.json5` gains an empty line on every build.** The RNOH 0.77.75 autolinker rewrites the file and appends `\n` each time (`JSON5Writer.updateDependencies` in the CLI). Discard it before committing: `git checkout -- app/harmony/oh-package.json5`.

### 3. Install and launch on the emulator

Start the emulator in DevEco Studio (Device Manager, phone, newest image), then:

```bash
hdc list targets                 # e.g. 127.0.0.1:5555 (add -t <target> below if several are connected)
hdc install -r app/harmony/entry/build/default/outputs/default/entry-default-unsigned.hap
hdc shell aa start -a EntryAbility -b pl.sprawdzam.app
hdc hilog | grep -iE "rnoh|sprawdzam"   # logs

# screenshot
hdc shell snapshot_display -f /data/local/tmp/s.jpeg && hdc file recv /data/local/tmp/s.jpeg ./s.jpeg
```

The DevEco Studio emulator accepts the unsigned debug HAP (verified on the phone emulator, HarmonyOS 6.1.0.126, API 24: `install bundle successfully`, the screen shows "Platform: harmony"). A physical device needs a signed HAP (see below).

### 4. Development with Metro (hot reload)

```bash
cd app
npm start                        # Metro on port 8081
hdc rport tcp:8081 tcp:8081      # device localhost:8081 -> Mac
```

Debug builds try Metro first, then the bundled file. Restart the app after starting Metro (`hdc shell aa force-stop pl.sprawdzam.app`, then `aa start` as above); Metro logs `BUNDLE ./index.js` when the device fetches the bundle. Remove the forward afterwards with `hdc fport rm tcp:8081 tcp:8081`.

### 5. Signing (DevEco Studio)

1. Open `app/harmony` in DevEco Studio and wait for sync.
2. **File > Project Structure > Signing Configs**, tick **Automatically generate signature** (needs a Huawei Developer account), OK.
3. DevEco writes `signingConfigs` into `harmony/build-profile.json5`, which is git-ignored on purpose. Never commit signing material (`.p12`, `.cer`, `.p7b`, `.csr`) or passwords.
4. Rebuild: the output becomes `entry-default-signed.hap`.

For the release HAP, the RNOH hvigor plugin can run `bundle-harmony` by itself in release mode: set `bundler: { enabled: true, dev: false }` in `createRNOHProjectPlugin()` in `harmony/hvigorfile.ts` (not enabled yet).

According to the Huawei hackathon FAQ, Run/Debug from DevEco Studio also works for debug builds without an account (automatic debug certificate).

## Android

```bash
cd app/android
./gradlew assembleDebug          # add -PreactNativeArchitectures=arm64-v8a for a faster local build
# APK: app/android/app/build/outputs/apk/debug/app-debug.apk

cd ..
npm start                        # Metro
npm run android                  # build, install and launch on a running emulator/device
```

No keystore is committed. Debug builds use the Android Gradle Plugin default `~/.android/debug.keystore`.

## CallEngine (native call audio)

The CallEngine TurboModule connects the app to the backend and carries call audio. Audio stays native:
JS sends commands and receives control events only, so 50 audio frames per second never cross the bridge.

| Layer | Path |
| --- | --- |
| TS spec (codegen input) | `src/native/NativeCallEngine.ts` |
| JS facade with typed events | `src/native/CallEngine.ts` |
| Dev panel (connect, incoming call, accept, risk, password, hang up) | `src/DevCallPanel.tsx` |
| HarmonyOS implementation (ArkTS) | `harmony/entry/src/main/ets/callengine/` |
| Android stub (Kotlin, rejects with `E_NOT_IMPLEMENTED`) | `android/app/src/main/java/pl/sprawdzam/app/callengine/` |
| Fake backend for local tests (silent) | `tools/fake_backend.py` |

Codegen: `package.json` → `harmony.codegenConfig` (RNOH `codegen-harmony` v1, run by the hvigor plugin on every build; output in git-ignored `cpp/generated/` and `oh_modules/.../generated/`) and `codegenConfig` (React Native Android codegen, generates `NativeCallEngineSpec`).

API: `connectControl(url, deviceToken)`, `disconnectControl()`, `requestMicrophonePermission()`, `acceptCall(callUrl)`, `hangup()`, `sendDtmf(digits)`. Events (via `DeviceEventEmitter`, names `CallEngine.on*`): `incomingCall` (includes the derived `callUrl`), `risk`, `verifyPassword`, `callEnded`, `protectionStatus`, `error`.

### Protocol v0

- Control: `WS /app/control?device_token=<token>`. Backend → app `{"type":"incoming_call","callId","token","caller","lang"}`, `{"type":"protection_status","available":true}`; app → backend `{"type":"ping"}` every 15 s, answered with `{"type":"pong"}`. The app reconnects with exponential backoff (1 s up to 30 s) and reports `protectionStatus.connected=false` meanwhile (fail-open: calls are not blocked).
- Call: `WS /app/call/{callId}?token=<one-time token>`. Binary frames are PCM16 LE mono 16 kHz, 20 ms = 640 bytes, in both directions. Backend → app `{"type":"risk","score","level":"none|warn|high","scamType","reasons":[]}`, `{"type":"verify_password"}`, `{"type":"call_ended","reason"}`; app → backend `{"type":"accept"}`, `{"type":"hangup"}`, `{"type":"dtmf","digits"}`.
- `ws://` is only for the localhost dev path; production uses `wss://`.

### Audio on the DevEco emulator

- Capture with `SOURCE_TYPE_VOICE_COMMUNICATION` stalls after a few buffers on the emulator; `SOURCE_TYPE_MIC` delivers about 32 kB/s at 16 kHz. `VoiceAudio` uses MIC when `deviceInfo.productModel === 'emulator'` and VOICE_COMMUNICATION (echo cancellation) on real phones. A watchdog emits `error` with code `audio_capture_stalled` if no buffers arrive for 1 s.
- Playback with `STREAM_USAGE_VOICE_COMMUNICATION` goes to the speaker on the emulator.

### Local end-to-end test (silent)

```bash
cd app
uv run --with websockets python tools/fake_backend.py --port 8765 --call-after 3
hdc -t 127.0.0.1:5555 rport tcp:8765 tcp:8765
# a) from JS: open the app, tap Connect, then Accept; risk updates arrive after 3, 6 and 9 s, then the password prompt
# b) natively, without JS (auto-accept, DTMF 1234, hang up after 12 s; logs: hdc hilog | grep CallEngine):
hdc -t 127.0.0.1:5555 shell aa start -a EntryAbility -b pl.sprawdzam.app --ps spike call --ps url ws://127.0.0.1:8765/app/control --ps secs 12
```

Port 8000 is used by `basal-serve` on the dev Mac, hence 8765. The fake backend sends only zero PCM frames, so nothing is audible.

### Debug spikes

`EntryAbility` runs debug checks from launch parameters (`aa start -a EntryAbility -b pl.sprawdzam.app --ps spike ...`):

- `--ps spike audio [--ps source mic|voice|recognition|unprocessed] [--ps rate 16000|48000] [--ps secs 10] [--ps play 0|1]`: capture test with RMS per 100 ms and throughput logs (`hdc hilog | grep SprawdzamAudio`). Silent unless `play 1`.
- `--ps spike beep`: **audible** siren via MUSIC and VOICE_COMMUNICATION. Agree on audible tests with the team before running them on a shared emulator.
- `--ps spike call`: native call self-test (see above).

## Checks

```bash
cd app
npm test          # Jest
npm run typecheck # tsc --noEmit
npm run lint      # ESLint
```

## Project layout

```
app/
  App.tsx, index.js        shared React Native code (TypeScript)
  src/native/              TurboModule specs and JS facades (CallEngine)
  src/DevCallPanel.tsx     CallEngine developer panel
  tools/fake_backend.py    silent protocol v0 backend for local tests
  metro.config.js          adds the "harmony" platform (createHarmonyMetroConfig)
  harmony/                 HarmonyOS container (created with `react-native init-harmony`)
    AppScope/app.json5     bundle name pl.sprawdzam.app
    build-profile.template.json5   SDK versions; copy to build-profile.json5
    entry/                 entry module: ArkTS (EntryAbility, Index.ets, callengine/), C++ glue (CMakeLists.txt, PackageProvider.cpp)
  android/                 Android container (Kotlin, callengine/ stub)
```
