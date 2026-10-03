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

## Workflow

### Ideation and architecture

AI helped compare the hackathon challenges against their rules and judging criteria, then researched each technical choice before the team decided. Key decisions made with AI input and confirmed by the team: React Native with RNOH for one Android + HarmonyOS code base; native ArkTS/Kotlin modules for platform capabilities; self-hosted Whisper and the basal-1 decision model instead of third-party APIs; no emotion recognition (EU AI Act high-risk category); Twilio Media Streams for call audio.

### Implementation

[Describe the AI-assisted coding workflow and how generated output was reviewed before acceptance.]

### Testing and debugging

[Record builds, linting, tests, device/emulator runs, UI inspection, logs, screenshots, and manual checks.]

## Unsuccessful approaches

- [What was tried, why it failed, and what changed afterward.]

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
