# Sprawdzam / Second Ear: mobile app

One React Native code base for two targets:

- **HarmonyOS** through React Native for OpenHarmony (RNOH), packaged as a `.hap` (Huawei challenge target)
- **Android**

The app is the senior's side of Sprawdzam: it keeps a control connection to the backend, shows protected calls full-screen, carries the call audio natively and shows the backend's live scam-risk assessment. See [Screens](#screens), [Platform capabilities](#platform-capabilities) and [CallEngine](#callengine-native-call-audio).

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

## Screens

Minimal, large, high-contrast UI for seniors (team decision): body text ≥ 24 pt, touch targets ≥ 72 dp, WCAG AA contrast (ratios in `src/theme.ts`), few words, all strings in PL and EN in `src/i18n.tsx`. Pure React Native components.

| Screen | File | What it shows |
| --- | --- | --- |
| Home | `src/screens/HomeScreen.tsx` | One big status: green "Jesteś chroniony / You are protected" or amber "Ochrona chwilowo niedostępna / Protection temporarily unavailable" (control channel down, fail-open). One button to Settings. Long-press the app name for 2 s: developer panel. |
| Incoming call | `src/screens/IncomingCallScreen.tsx` | Full screen, masked caller on one line, big Answer (green) and Decline (red). |
| In call | `src/screens/InCallScreen.tsx` | Caller, timer, risk banner (neutral, amber at `warn`, red at `high` with the reasons), on `verify_password` our own big numeric keypad for the family password (compact layout, no system keyboard), big Hang up. |
| Call result | `src/screens/CallEndedScreen.tsx` | Per `call_ended` reason, e.g. red "Rozłączyliśmy podejrzaną rozmowę. Powiadomiliśmy osobę zaufaną." for `scam_blocked`; OK returns home. |
| Settings | `src/screens/SettingsScreen.tsx` | Language PL/EN (UI and the language sent to the backend), trusted person and whitelist from contacts, notifications, developer fields (backend URL, device token, system call screen toggle, test panel). |

Call state lives in `src/useCallEngine.ts`; `App.tsx` lets an incoming or active call take over the screen.

## Platform capabilities

What each platform feature is used for and where it was verified. "Emulator" means the DevEco Studio phone emulator (HarmonyOS 6.1.0.126, API 24) on 2026-10-03.

| Capability | HarmonyOS (ArkTS) | Verified on HarmonyOS | Android (Kotlin) | Verified on Android |
| --- | --- | --- | --- | --- |
| Call audio | Audio Kit: `AudioCapturer` (MIC on the emulator, VOICE_COMMUNICATION on phones) + `AudioRenderer` (VOICE_COMMUNICATION), 16 kHz mono PCM16, 20 ms frames | Emulator: continuous capture at 16/48 kHz, playback audible (human), 20 ms frames both ways with the fake backend | `AudioRecord` VOICE_COMMUNICATION + `AudioTrack` USAGE_VOICE_COMMUNICATION | Build only |
| Backend connection | Network Kit `webSocket` (control + call channels) | Emulator, fake backend: all protocol paths incl. 1008, 4000, timeout, scam_blocked | OkHttp WebSocket | Build only |
| Notifications | Notification Kit (`notificationManager`, `wantAgent` to open the app), permission via `requestEnableNotification` | Emulator: incoming-call notification seen by a person; warn/high/blocked published (hilog) | `NotificationManager`, channel `calls`, POST_NOTIFICATIONS on API 33+ | Build only |
| Contacts | Contacts Kit picker `contact.selectContacts` (no permission; READ_CONTACTS is ACL-restricted) | Emulator: picker opens with "limited access"; picking not tested (no contacts on the emulator) | `ACTION_PICK` on phone numbers (no READ_CONTACTS) | Build only |
| Secure storage | Asset Store Kit for the device token, Preferences for settings and whitelist | Emulator: token stored in Asset Store (hilog) | SharedPreferences (Keystore: TODO) | Build only |
| Microphone permission | `abilityAccessCtrl.requestPermissionsFromUser`, reason string in PL/EN | Emulator (a person tapped Allow) | RECORD_AUDIO runtime request on answer | Build only |
| System call UI | Call Service Kit `voipCall.reportIncomingCall` behind Settings > Developer toggle (default off); UI events map to accept/hangup/mute | Not available on the emulator (`canIUse('SystemCapability.Telephony.VoipCallManager') = false`); needs a physical Huawei phone | — | — |
| Call filtering | Not available to apps (rejecting calls is a system API): operator unconditional forwarding + whitelist in the backend | — | `CallScreeningService` stub (allows all calls); planned: reject non-contacts so "forward when busy" sends them to the backend | Build only |

Not done yet: keeping protection running while the app is closed (HarmonyOS suspends background apps; needs Push Kit VoIP push or a continuous task), home-screen widget, Android Keystore for the token.

## CallEngine (native call audio)

The CallEngine TurboModule connects the app to the backend and carries call audio. Audio stays native:
JS sends commands and receives control events only, so 50 audio frames per second never cross the bridge.

| Layer | Path |
| --- | --- |
| TS spec (codegen input) | `src/native/NativeCallEngine.ts` |
| JS facade with typed events | `src/native/CallEngine.ts` |
| HarmonyOS implementation (ArkTS) | `harmony/entry/src/main/ets/callengine/`: `CallEngineTurboModule` (UITurboModule) on `CallEngineCore`, `ControlChannel`, `CallSession`, `VoiceAudio`, `CallNotifier`, `ContactsBridge`, `SettingsStore`, `SystemCallUi`, `Protocol` |
| Android implementation (Kotlin) | `android/app/src/main/java/pl/sprawdzam/app/callengine/`: `CallEngineModule` (TurboModule), `ControlChannel`, `CallSession`, `VoiceAudio`, `CallNotifier`, `SettingsStore`, `ScreeningService` (stub), `Protocol` |
| Developer panel | `src/DevCallPanel.tsx` |
| Fake backend for local tests (silent) | `tools/fake_backend.py` |

```
JS (senior UI)  ── commands ──►  CallEngine TurboModule  ── control WS ──►  backend /app/control
      ▲                              │   └── call WS (PCM 20 ms frames both ways) ──► /app/call/{id}
      └──── events (DeviceEventEmitter) ┘   mic ⇄ VoiceAudio ⇄ speaker (native only)
```

Both platforms implement the same spec, protocol and events; the HarmonyOS side has been run on the emulator, the Android side is build-verified only.

Codegen: `package.json` → `harmony.codegenConfig` (RNOH `codegen-harmony` v1, run by the hvigor plugin on every build; output in git-ignored `cpp/generated/` and `oh_modules/.../generated/`) and `codegenConfig` (React Native Android codegen, generates `NativeCallEngineSpec`).

API: `connectControl(url, deviceToken)`, `disconnectControl()`, `requestMicrophonePermission()`, `acceptCall(callId)`, `hangup()` (also rejects a ringing call), `sendDtmf(digits)`, `requestNotificationPermission()`, `loadSettings()`, `saveSettings(json)`, `pickTrustedPerson()`, `pickWhitelistContacts()`, `getWhitelistCount()`. Events (via `DeviceEventEmitter`, names `CallEngine.on*`): `incomingCall` `{callId, caller, lang}`, `callActive`, `risk`, `verifyPassword`, `callEnded` `{callId, reason}`, `protectionStatus` `{available, connected}`, `error`. The one-time call token stays in native code.

### Protocol v0

The source of truth is `docs/APP_PROTOCOL.md` in the server repository (branch `feat/server-skeleton`). How the app implements it:

- Control `WS /app/control?device_token=…`: ping every 15 s. Any close (1000, 1008 bad token, 4000 idle after 45 s, network error) triggers a reconnect with backoff 1 s, 2 s, 5 s, then every 10 s; the backoff resets on the first valid message. While disconnected `protectionStatus.connected=false` and the UI shows "protection unavailable". 1008 also emits `error` `control_auth_failed`.
- `incoming_call` opens the call channel `WS /app/call/{callId}?token=…` immediately (state ringing; the caller hears ringback). `call_ended` can arrive while ringing (`timeout` after 30 s, `caller_hangup`).
- `acceptCall` sends `accept` and only then starts mic and speaker (binary PCM16 LE mono 16 kHz, 640-byte frames, both ways). Playback uses a jitter buffer: 60 ms prebuffer after an underrun, at most 200 ms queued.
- `hangup` sends `hangup` (also to reject while ringing); the backend answers `call_ended(senior_hangup)` and closes. If that does not arrive within 2 s the app ends the call locally with `senior_hangup`.
- `sendDtmf` accepts `0-9 * #`, 1–32 characters (family password while `verify_password` is pending).
- `call_ended` reasons: `caller_hangup`, `senior_hangup`, `scam_blocked`, `timeout`, `error`. A call channel that closes without `call_ended` ends with `error` (1008 also emits `error` `call_auth_failed`).
- Unknown message types and fields are ignored. `ws://` only on the localhost dev path; production uses `wss://`.

### Contacts, settings and the `settings` message

- Trusted person and whitelist come from the system contact picker (HarmonyOS: single and multi-select; Android: one contact per pick). No contacts permission on either platform.
- Whitelist numbers stay native and are sent only over the control channel in `{"type":"settings","lang","trustedPerson","whitelist"}` after every (re)connect and settings change (proposed protocol extension: `../docs/APP_PROTOCOL_EXTENSIONS.md`). The app logs counts only. Verified on the emulator with the fake backend: the message arrives on connect and after switching the language.
- Background: notifications and the control channel need the app process to be alive. HarmonyOS suspends background apps; keeping protection running while the app is closed needs a VoIP push (Push Kit `VoIPExtensionAbility`, AppGallery account) or a continuous task. Not done yet; for the demo the app stays in the foreground.

### Audio on the DevEco emulator

- The macOS host must allow the emulator to use the microphone. While that was being sorted out, the first capture runs stalled (VOICE_COMMUNICATION after 3 buffers; MIC after about 8 s, then `stop()` failed with 6800301). After that, 10 s runs of MIC and VOICE_COMMUNICATION at 16 kHz and 48 kHz all delivered continuous buffers (16 kHz: about 32.6 kB/s, 51 callbacks of 640 B per second) and stopped cleanly.
- `VoiceAudio` uses MIC when `deviceInfo.productModel === 'emulator'` and VOICE_COMMUNICATION (echo cancellation) on real phones.
- Capture can still stall mid-call on the emulator (seen once after 5 s: the HAL logs `CaptureReadFrame failed` and no audio arrives). A watchdog emits `error` `audio_capture_stalled` after 1 s without audio and recreates the capturer (up to 3 times per call). The recovery path has not been observed in action yet.
- Playback with `STREAM_USAGE_VOICE_COMMUNICATION` goes to the speaker on the emulator.

### Local end-to-end test (silent)

```bash
cd app
uv run --with websockets python tools/fake_backend.py --port 8766 --call-after 3   # see --help for scenarios
hdc -t 127.0.0.1:5555 rport tcp:8766 tcp:8766
# a) from JS: Settings > Developer > Server address ws://localhost:8766/app/control, Save and connect
# b) natively, without JS (logs: hdc hilog | grep CallEngine):
hdc -t 127.0.0.1:5555 shell aa start -a EntryAbility -b pl.sprawdzam.app --ps spike call \
  --ps url ws://localhost:8766/app/control --ps mode accept|reject|ignore --ps ring 2 --ps secs 16 --ps dtmf 1234
```

Fake backend options: `--scenario scam|benign`, `--password 1234`, `--password-timeout 20`, `--caller-hangup N`, `--idle 45`, `--device-token X` (1008 for any other token). Ports: 8000 on the dev Mac is `basal-serve`, 8765 is the real backend's dev port (the app's default `ws://localhost:8765/app/control`, token `dev-device-1-sprawdzam`; the backend requires at least 16 characters), so the fake backend uses 8766. The fake backend sends only zero PCM frames, so nothing is audible.

Verified on the emulator (2026-10-03, native path): accept + correct password (call continues, then `senior_hangup`), wrong password (`scam_blocked` after the timeout), reject while ringing (`senior_hangup`), ignore (`timeout` after 30 s), `caller_hangup`, wrong device token (1008, backoff 1/2/5/10 s), 4000 idle close followed by a reconnect.

### Debug spikes

`EntryAbility` runs debug checks from launch parameters (`aa start -a EntryAbility -b pl.sprawdzam.app --ps spike ...`):

- `--ps spike audio [--ps source mic|voice|recognition|unprocessed] [--ps rate 16000|48000] [--ps secs 10] [--ps play 0|1]`: capture test with RMS per 100 ms and throughput logs (`hdc hilog | grep SprawdzamAudio`). Silent unless `play 1`.
- `--ps spike beep`: **audible** siren via MUSIC and VOICE_COMMUNICATION. Agree on audible tests with the team before running them on a shared emulator.
- `--ps spike call [--ps mode accept|reject|ignore]`: native call self-test (see above).
- `--ps spike voip --ps mode check|report [--ps secs 10]`: Call Service Kit spike. `check` is silent (logs `canIUse('SystemCapability.Telephony.VoipCallManager')`); `report` calls `voipCall.reportIncomingCall` and **may ring** through the system incoming-call UI (agree with the team first). Logs: `hdc hilog | grep VoipSpike`.

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
  App.tsx, index.js        shared React Native code (TypeScript), screen routing
  src/screens/             senior UI screens; src/components/ (BigButton, Keypad, RiskBanner)
  src/i18n.tsx, theme.ts   PL/EN strings, design tokens
  src/settings.ts          settings model (persisted natively)
  src/useCallEngine.ts     call state from CallEngine events
  src/native/              TurboModule spec and JS facade (CallEngine)
  src/DevCallPanel.tsx     CallEngine developer panel
  tools/fake_backend.py    silent protocol v0 backend for local tests
  metro.config.js          adds the "harmony" platform (createHarmonyMetroConfig)
  harmony/                 HarmonyOS container (created with `react-native init-harmony`)
    AppScope/app.json5     bundle name pl.sprawdzam.app
    build-profile.template.json5   SDK versions; copy to build-profile.json5
    entry/                 entry module: ArkTS (EntryAbility, Index.ets, callengine/), C++ glue (CMakeLists.txt, PackageProvider.cpp)
  android/                 Android container (Kotlin, callengine/)
```
