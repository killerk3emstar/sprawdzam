# Sprawdzam / Second Ear: mobile app

One React Native code base for two targets:

- **HarmonyOS** through React Native for OpenHarmony (RNOH), packaged as a `.hap` (Huawei challenge target)
- **Android**

The current screen is a hello world. Real screens and native modules (CallEngine, contacts, notifications, widget) come next.

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

During the build the RNOH hvigor plugin runs codegen and autolinking (generated files are git-ignored) and tries to forward the Metro port with `hdc rport`. Without a connected device it logs `[metro] [Fail]ExecuteCommand need connect-key`, which is harmless.

### 3. Install and launch on the emulator

Start the emulator in DevEco Studio (Device Manager, phone, newest image), then:

```bash
hdc list targets                 # e.g. 127.0.0.1:5555
hdc install -r app/harmony/entry/build/default/outputs/default/entry-default-unsigned.hap
hdc shell aa start -a EntryAbility -b pl.sprawdzam.app
hdc hilog | grep -iE "rnoh|sprawdzam"   # logs
```

The RNOH CLI (`run-harmony`) installs the unsigned HAP on emulators, so this should work without signing. If the emulator rejects it, sign the app in DevEco Studio instead (see below).

### 4. Development with Metro (hot reload)

```bash
cd app
npm start                        # Metro on port 8081
hdc rport tcp:8081 tcp:8081      # device localhost:8081 -> Mac
```

Debug builds try Metro first, then the bundled file.

### 5. Signing (DevEco Studio)

1. Open `app/harmony` in DevEco Studio and wait for sync.
2. **File > Project Structure > Signing Configs**, tick **Automatically generate signature** (needs a Huawei Developer account), OK.
3. DevEco writes `signingConfigs` into `harmony/build-profile.json5`, which is git-ignored on purpose. Never commit signing material (`.p12`, `.cer`, `.p7b`, `.csr`) or passwords.
4. Rebuild: the output becomes `entry-default-signed.hap`.

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
  metro.config.js          adds the "harmony" platform (createHarmonyMetroConfig)
  harmony/                 HarmonyOS container (created with `react-native init-harmony`)
    AppScope/app.json5     bundle name pl.sprawdzam.app
    build-profile.template.json5   SDK versions; copy to build-profile.json5
    entry/                 entry module: ArkTS (EntryAbility, Index.ets), C++ glue (CMakeLists.txt, PackageProvider.cpp)
  android/                 Android container (Kotlin)
```
