# AI Workflow

This project uses AI-assisted development. Keep this document current and public-safe. Do not include credentials, tokens, personal data, private endpoints, or confidential prompts.

## Tools used

| Model, agent, MCP server, or Agent Skill | Version or source | Role in the project |
| --- | --- | --- |
| Claude (Cowork mode in the Claude desktop app) | Anthropic, model `claude-opus-5-5` | Ideation, challenge analysis, technology research (RNOH, speech-to-text, decision models, telephony, costs, legal constraints), architecture and schedule planning |
| Claude Code | Anthropic, Claude Code 2.1.283 in the Claude desktop app (Code tab), model `claude-opus-5-5` (Opus 5.5) | Environment checks, implementation, builds, tests, debugging |
| Huawei hackathon Agent Skills (`hmos-arkts-knowledge-retriever`, `hmos-arkui-develop-skill`, `hmos-arkui-scenario-development`, `hmos-arkui-mvvm-pattern`, `ohos-app-dev`, `ohos-app-scaffold`, `ohos-system-app-dev`) | https://github.com/onirodeveloper/hackyeah2026-challenge (`skills/`) | ArkTS/ArkUI reference and HarmonyOS app development workflows for the native modules |

## Important prompts and instructions

- `CLAUDE.md` — project context, confirmed decisions, architecture, working agreement with the coding agent (written in Polish, the team's language).
- Planning brief given to Claude in Cowork: build one app for the Huawei "Imagine What's Next" and Defence challenges, in React Native, protecting elderly people from phone scams; keep audio processing on our own infrastructure; make the demo work in Polish and English.

## AI-assisted work log

| Date | Tool/model | Request or task | Generated or changed | Human review and validation |
| --- | --- | --- | --- | --- |
| 2026-10-03 | Claude (Cowork) | Compare challenges, check rules, pick an idea | Challenge overview and idea notes | Team chose the idea and the two challenges |
| 2026-10-03 | Claude (Cowork) | Research RNOH, the Huawei/Oniro challenge repository, emulator setup without an account, telephony options and costs, self-hosted speech-to-text and decision models (basal-1, Clef-Flash, Jev), AI Act and GDPR constraints | Project plan (decisions, architecture diagram, schedule, risks, costs), `CLAUDE.md`, this file | Team reviewed the plan, changed the risk model choice and the phone number strategy, confirmed hardware (Mac, 48 GB RAM) |
| 2026-10-03 | Claude Code (Opus 5.5) | First session: read the brief and challenge rules, check the Mac toolchain, unpack the HarmonyOS command-line tools, initialise the repository | Environment report with tool versions and PATH entries, `.gitignore` entry for local agent settings, initial commit | Versions read from the installed tools (`node -v`, `python3 --version`, `git`, `uv`, Android SDK, ZIP listings); report handed to the team for review |
| 2026-10-03 | Claude Code sub-agent (Opus 5.5) | Backend skeleton (`feat/server-skeleton`): Twilio webhook with signature check, Media Streams WebSocket, G.711 decoding and resampling, PL/EN keyword rules, smoothing, model fallback; then hard cost limits on telephony (dry-run by default, outbound allowlist, daily caps, one alert per call, concurrency, call duration, rate limit) | `server/` (FastAPI app, 139 tests), `.env.example` entries | Coordinator re-ran `uv run pytest` (139 passed) and `ruff check`, scanned for secrets; sub-agent ran a smoke test on a live uvicorn with a WebSocket client and tested every commit separately |
| 2026-10-03 | Claude Code sub-agent (Opus 5.5) | React Native 0.77.1 + RNOH 0.77.75 hello world (`feat/app-rnoh`): HarmonyOS container with API 20 minimum / API 24 target, CLI build of the HAP, Android debug build | `app/` (RN project, `harmony/`, `android/`, README with build steps and RNOH quirks) | HAP installed and launched on the DevEco emulator (API 24) with a screenshot, Metro dev loop checked, clean rebuild from README steps, `module.json` in the HAP inspected (min API 20, target API 24), Gradle `assembleDebug` succeeded, jest/tsc/eslint pass; team saw the screenshot |
| 2026-10-03 | Claude Code sub-agent (Opus 5.5) | Model bench (`feat/model-bench`): serve Whisper large-v3-turbo (whisper.cpp, Metal) and basal-1 on Apple Silicon, measure latency and answers on phone-quality synthetic audio and 14 hand-written PL/EN transcripts, document both HTTP APIs | `server/bench/` (run/download scripts, bench scripts, transcripts, results, README), `--share-state` patch for basal-serve (one forward pass for all questions, about 2.2x faster) | All numbers from real runs on the M4 Pro: Whisper about 0.5 s per 3 s chunk; basal-1 4.5B on MPS with the patch 0.76 s (risk only) to 1.94 s (6 questions); answers compared with expected labels; coordinator checked that no weights or audio are committed and changed the servers to bind to localhost |
| 2026-10-03 | Claude Code sub-agent (Opus 5.5) | HarmonyOS audio spike on the emulator: microphone permission, AudioCapturer and AudioRenderer in voice-communication and media modes | `AudioSpike.ets` behind a debug launch flag | Human tapped the permission dialog and confirmed the test sound was audible; hilog showed continuous capture with `SOURCE_TYPE_MIC` (VOICE_COMMUNICATION capture stalls on the emulator) and playback routed to the speaker |
| 2026-10-03 | Team + Claude Code (Opus 5.5) | Decisions after the first measurements: RNOH GO (22:33), risk score `100·(1−P(low))` with warn ≥50 and hang-up ≥90 (two readings in a row, plus a secrecy or rule signal), Clef-Flash only if time allows, telephony purchase postponed in favour of free browser test pages | `CLAUDE.md` updated with measured facts and decisions | Team chose from options with trade-offs prepared by the coordinator from the sub-agents' measurements |
| 2026-10-03 | Claude Code sub-agent (Opus 5.5) | Telephony provider adapter (Twilio implemented, SignalWire differences documented), senior app relay (protocol v0 in `docs/APP_PROTOCOL.md`), browser test pages `/dev/caller` and `/dev/senior` | `server/app/telephony/`, `server/app/relay/`, `server/app/calls/`, `server/app/dev/` | Coordinator re-ran the suite (198 passed); sub-agent tested every commit separately, ran a live uvicorn with Python WebSocket clients (ringback, accept, 1 kHz / 500 Hz tones arriving at the right pitch in both directions, token masked in logs), checked the pages in a browser pane and the AudioWorklet in an OfflineAudioContext, and compared the JS μ-law codec with Python (0 differences) |
| 2026-10-03 | Claude Code sub-agent (Opus 5.5) | Plug in the real models: pause-based 3–8 s segments, whisper.cpp client with hallucination filtering, basal-1 client with two-tier questions and the team's score/thresholds, digit-based money rules, local voice prompts, e2e smoke script | `server/app/stt/whisper.py`, `server/app/risk/basal.py`, `server/app/audio/segmenter.py`, `server/scripts/` | Coordinator re-ran the suite (272 passed); sub-agent ran live tests against the local model servers and an end-to-end smoke with TTS clips streamed in real time: PL/EN scam clips ended in `scam_blocked` 21–42 s after call start, normal family calls stayed below the warn threshold (max 48 and 23); paid telephony actions only logged (dry-run) |

## Workflow

### Ideation and architecture

AI helped compare the hackathon challenges against their rules and judging criteria, then researched each technical choice before the team decided. Key decisions made with AI input and confirmed by the team: React Native with RNOH for one Android + HarmonyOS code base; native ArkTS/Kotlin modules for platform capabilities; self-hosted Whisper and the basal-1 decision model instead of third-party APIs; no emotion recognition (EU AI Act high-risk category); Twilio Media Streams for call audio.

### Implementation

Claude Code runs as a coordinator in the main checkout and delegates independent tracks to parallel sub-agents (Claude Code `Agent` tool, same model). Each sub-agent gets a self-contained brief (scope, fixed decisions from `CLAUDE.md`, environment paths, commit rules, a 30-minute "stop and report" limit) and works in its own git worktree on a feature branch, so agents never edit the same files:

| Track | Worktree / branch | Brief (summary) |
| --- | --- | --- |
| Backend skeleton | `sprawdzam-server` / `feat/server-skeleton` | FastAPI app: Twilio webhook with signature check, Media Streams WebSocket, μ-law decoding, PL/EN keyword rules, smoothing, model fallback, tests; all external services behind interfaces with fakes |
| App | `sprawdzam-app` / `feat/app-rnoh` | React Native 0.77.1 + RNOH 0.77.75 project, HarmonyOS container with API 20 minimum / API 24 target, CLI build of the HAP |
| Models | `sprawdzam-models` / `feat/model-bench` | Download and serve Whisper large-v3-turbo (whisper.cpp) and basal-1 on Apple Silicon, measure latency and answers on synthetic PL/EN calls, document the HTTP APIs |

Sub-agents commit but never push or merge. The coordinator reviews each report and diff, and the team merges feature branches into `main` themselves.

### Testing and debugging

[Record builds, linting, tests, device/emulator runs, UI inspection, logs, screenshots, and manual checks.]

## Unsuccessful approaches

- Twilio trial account: `<Stream>` is blocked on trial accounts, so the free plan cannot carry our core flow; the team postponed buying credit and built browser test pages that speak the Media Streams format instead.
- HarmonyOS emulator: `AudioCapturer` with `SOURCE_TYPE_VOICE_COMMUNICATION` delivers a few buffers and then stalls; `SOURCE_TYPE_MIC` streams continuously, so the app uses MIC on the emulator.
- basal-1 out of the box on Apple Silicon: 7.6 s per 6-question decision in eager mode and 4.5 s in MLX mode, too slow for a 3–4 s cycle; fixed with MPS mode, a share-state patch and fewer questions per cycle.
- Whisper: `--audio-ctx 256` cut encoder time but produced garbage; a keyword prompt made it invent words; 2 s chunks were clearly less accurate than 3–8 s.
- Installing `node@22` with Homebrew upgraded a shared library (`simdutf`) and broke the default `node`; fixed by rebuilding `merve`.

## Known limitations

- [Product, platform, model, data, testing, or tooling limitation.]

## Lessons learned

- [Concise lesson that would help reproduce or improve the work.]

## AI feature disclosure

- Model or service: Whisper large-v3-turbo (speech-to-text), basal-1.0-4.5B (risk decisions), Clef-Flash (comparison); all self-hosted. Details to be completed in `docs/AI_FEATURES.md`.
- Inference flow: [To be completed]
- Data handling and privacy: audio and transcripts stay in memory and are discarded after the call; only a short alert summary is stored.
- Failure and fallback behavior: keyword rules work without the model; if the backend is down, calls pass through normally and the app shows that protection is unavailable.
- Evaluation: [To be completed: synthetic PL/EN call set, precision, recall, confusion matrix]
