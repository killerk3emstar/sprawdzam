# Sprawdzam (Second Ear)

Ochrona seniorów przed oszustwami telefonicznymi „na wnuczka”, „na policjanta” i „na pracownika banku”, w czasie rzeczywistym, w trakcie rozmowy. Projekt na HackYeah 2026 (zadanie Defence).

## Problem

W 2023 roku policja odnotowała ponad 14 tys. oszustw metodą „na wnuczka” i „na policjanta”; większość ofiar ma ponad 70 lat (Kwartalnik Policyjny 4/2025). Oszust działa w trakcie jednej rozmowy, często w kilka minut. Ostrzeżenia w kampaniach społecznych nie pomagają w chwili, gdy ktoś pod presją mówi „proszę nikomu nie mówić”.

## Rozwiązanie

1. Rozmowa z **numeru spoza kontaktów** trafia do Sprawdzam, a rozmowy z kontaktami dzwonią normalnie i nikt ich nie analizuje.
2. Mowa jest na bieżąco zamieniana na tekst (Whisper), a model decyzyjny basal-1 razem z regułami słów kluczowych ocenia ryzyko oszustwa.
3. Przy średnim ryzyku senior słyszy ostrzeżenie. Przy wysokim system prosi o hasło rodzinne, rozłącza oszusta i powiadamia osobę zaufaną SMS-em.

## Dwa modele wdrożenia

| | **B2B: operator komórkowy** (główny kierunek) | **B2C: aplikacja + przekierowanie** (dodatek, na nim robimy demo) |
| --- | --- | --- |
| Skąd audio | Moduł Sprawdzam na serwerach operatora dostaje kopię dźwięku rozmów z nieznanych numerów (sieć VoLTE/IMS) | Telefon odrzuca nieznany numer, operator przekierowuje go „gdy zajęte” na numer usługi, senior odbiera w aplikacji |
| Co instaluje senior | Nic, włącza usługę u operatora | Aplikację na Androida |
| Alerty | SMS z sieci operatora | SMS wysyłany z telefonu seniora |
| Status | **Zaprojektowane, nie zbudowane** (`docs/ARCHITECTURE.md`) | Backend i aplikacja zbudowane; przekierowanie od prawdziwego operatora nietestowane, w demo zastępuje je symulator sieci |

## Jak to działa (demo)

```
Symulator sieci operatora          Backend (FastAPI, MacBook)                        Telefon seniora (Android)
 /dev/caller w przeglądarce  ──►   μ-law 8 kHz → PCM 16 kHz → cięcie po pauzach  ◄══► aplikacja: połączenie,
 (nagrany skrypt oszusta           → Whisper large-v3-turbo (lokalnie)                  pasek ryzyka, hasło
  albo mikrofon)                   → basal-1.0-4.5B + reguły → wygładzanie              rodzinne, SMS do osoby
                                   → ostrzeżenie / hasło rodzinne / rozłączenie         zaufanej
                                   → /dev/jury: ekran na projektor
```

- Oba modele działają **lokalnie na Macu**; treść rozmowy nie trafia do żadnej zewnętrznej usługi AI.
- Twilio jest podłączone przez adapter, ale w demo działa w trybie dry-run (nic nie dzwoni i nie płaci).
- Jeśli backend albo model nie działa, połączenie przechodzi normalnie (fail-open), a aplikacja pokazuje „Ochrona chwilowo niedostępna”.

## Prywatność

- Nie zapisujemy audio ani transkrypcji: są tylko w pamięci RAM na czas rozmowy. Logi zawierają identyfikatory, wyniki i kategorie, bez treści rozmowy i z zamaskowanymi numerami.
- Dzwoniący przed połączeniem słyszy, że rozmowa jest chroniona i sprawdzana, ale nie nagrywana.
- **Nie rozpoznajemy emocji ani biometrii głosu** (AI Act: rozpoznawanie emocji z głosu to system wysokiego ryzyka). Model widzi tylko tekst z ostatnich ok. 60 s rozmowy.
- Ekran dla jury pokazuje treść rozmowy wyłącznie w trybie demonstracyjnym; widok operatora pokazuje alerty bez treści.

## Co jest zbudowane, a co zaprojektowane

| Element | Status |
| --- | --- |
| Backend: odbiór strumienia audio, konwersja, segmentacja, klient Whisper, ocena ryzyka (basal-1 + reguły + wygładzanie), eskalacja, przekazywanie dźwięku do aplikacji (protokół v0), zabezpieczenia kosztów telefonii | Zbudowane, 287 testów (`uv run pytest`) |
| Ewaluacja na 300 syntetycznych rozmowach PL/EN | Zbudowane, wyniki w `server/bench/eval/RESULTS.md` |
| Aplikacja React Native 0.77.1, moduł natywny CallEngine w Kotlinie (Android) | Zbudowane |
| Port aplikacji na HarmonyOS (RNOH 0.77.75, moduły ArkTS) | Zbudowane i uruchomione na emulatorze, **rozwój wstrzymany** (4.10) |
| Symulator sieci operatora `/dev/caller`, zastępcza aplikacja `/dev/senior` | Zbudowane |
| Ekran dla jury i konsola operatora `/dev/jury`, SMS do osoby zaufanej z telefonu seniora, analiza wypowiedzi seniora, zasada „same reguły nie rozłączają” | W budowie (4.10) |
| Moduł u operatora (IMS/SIPREC), sygnały o kampaniach oszustów, routing pilotażu B2C na wspólny numer | Zaprojektowane, nie zbudowane |

## Wyniki ewaluacji (dane syntetyczne)

300 rozmów (150 oszustw, 150 zwykłych, w tym 115 trudnych, np. syn naprawdę pożycza pieniądze). **Rozmowy napisał model językowy (Claude)**, więc to optymistyczne oszacowanie, a nie wynik z prawdziwych połączeń.

| System | Precyzja (ostrzeżenie) | Czułość (ostrzeżenie) | Odsetek fałszywych alarmów |
| --- | --- | --- | --- |
| Same reguły | 0,92 | 0,61 | 0,05 |
| basal-1.0-4.5B | 0,97 | 0,97 | 0,03 |
| max(basal-4.5B, reguły), tak działa backend | 0,93 | 1,00 | 0,07 |

Szczegóły, odczyty tura po turze i przykłady błędów: `server/bench/eval/RESULTS.md`, `docs/AI_FEATURES.md`.

## Uruchomienie demo od zera (Mac z Apple Silicon)

Wymagania: Homebrew `whisper-cpp`, `ffmpeg`, `uv`, `huggingface-cli`, `cloudflared`; ok. 15 GB miejsca na modele; Android SDK i JDK 21 do aplikacji (szczegóły w `app/README.md`).

**1. Modele** (jednorazowo ok. 11 GB pobierania, potem dwa terminale):

```bash
server/bench/download-models.sh     # Whisper large-v3-turbo + basal-1.0-4.5B + silnik basal z naszą łatką
server/bench/run-whisper.sh         # terminal 1: http://127.0.0.1:8080
server/bench/run-basal.sh           # terminal 2: http://127.0.0.1:8000 (ok. 10 GB RAM)
```

**2. Backend** na porcie 8765:

```bash
cd server
uv sync
scripts/make_prompts.sh && scripts/make_samples.sh   # jednorazowo: komunikaty głosowe i nagrane skrypty (macOS `say`)
cp ../.env.example .env.dev                          # i ustaw w .env.dev:
#   DEV_TOOLS=true
#   APP_DEVICE_TOKEN=<losowy ciąg, min. 16 znaków; ten sam wpisujesz w aplikacji>
#   FAMILY_PASSWORD=<3–12 cyfr, wartość tylko na demo>
#   TELEPHONY_DRY_RUN=true
#   WHISPER_URL=http://127.0.0.1:8080  DECISION_BACKEND=basal  BASAL_URL=http://127.0.0.1:8000
scripts/run_dev.sh --env .env.dev                    # terminal 3; sprawdź http://127.0.0.1:8765/health
```

Twilio nie jest potrzebne: bez `TWILIO_AUTH_TOKEN` webhooki Twilio są odrzucane, a symulator dzwoni przez `/dev/calls`.

**3. Tunel** dla iPhone'a „oszusta” (Safari wymaga HTTPS do mikrofonu):

```bash
cloudflared tunnel --url http://127.0.0.1:8765      # terminal 4; podaje adres https://….trycloudflare.com
```

**4. Aplikacja na Androidzie** (fizyczny telefon z kartą SIM, bo tylko on wyśle prawdziwy SMS):

```bash
# >>> TODO: app/scripts/install-demo-android.sh (przygotowywany równolegle; uzupełnić opis, gdy powstanie) <<<
```

Do tego czasu: build i instalacja według `app/README.md` (sekcja Android), potem w aplikacji Ustawienia → Developer: adres backendu (`wss://….trycloudflare.com/app/control` albo `ws://localhost:8765/app/control` po `adb reverse tcp:8765 tcp:8765`) i ten sam `APP_DEVICE_TOKEN`. Ekran główny ma pokazać „Jesteś chroniony”.

**5. Strony:**

| Adres | Kto | Co |
| --- | --- | --- |
| `https://….trycloudflare.com/dev/caller` | iPhone „oszusta” | Symulator sieci operatora: wybór skryptu (np. `pl_scam_police`, `pl_normal_family`) albo mikrofon, przycisk „Zadzwoń” |
| `http://127.0.0.1:8765/dev/jury` | Projektor | Transkrypcja na żywo, wykres ryzyka z progami 50 i 90, konsola operatora bez treści rozmów (w budowie) |
| `http://127.0.0.1:8765/dev/senior` | Zapas | Przeglądarkowa wersja aplikacji seniora, gdy telefon zawiedzie |

Ekran telefonu na projektor: `scrcpy`. Plan B: nagranie wideo demo.

## Testy i ewaluacja

```bash
cd server && uv run pytest                 # testy backendu, bez sieci i bez modeli
cd server && uv run pytest -m live         # opcjonalnie: z działającymi serwerami modeli
cd app && npm test && npm run typecheck    # aplikacja

# ewaluacja (z katalogu głównego repo, przy działającym basal-serve na :8000)
uv run scenarios/generator/generate.py --stats
uv run server/bench/eval/run_eval.py collect --url http://127.0.0.1:8000 --name basal-4.5B
uv run server/bench/eval/run_eval.py report
```

Pełna lista poleceń (model 1.5B, widok tylko dzwoniącego, tura po turze): `server/bench/eval/RESULTS.md`, sekcja „Reproduce”.

## Ograniczenia

- **Dane syntetyczne.** Ewaluację przeprowadziliśmy na rozmowach napisanych przez model językowy, a Whisper testowaliśmy na mowie syntezowanej przez telefoniczny filtr, nie na prawdziwych połączeniach z głosami starszych osób.
- **Brak umowy z operatorem.** Wariant B2B jest projektem; nie testowaliśmy dostępu do audio w sieci IMS ani przekierowania od polskiego operatora.
- **Tylko polski i angielski.** Język rozpoznawania mowy jest wymuszony z ustawień seniora.
- **Modele lokalnie na Macu.** Demo działa na jednym komputerze (M4 Pro, 48 GB RAM): kilka rozmów naraz, bez wysokiej dostępności.
- **Jedno urządzenie seniora na backend** (protokół v0), progi nie strojone na osobnym zbiorze danych.

## Dokumentacja

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): architektura, wdrożenie u operatora, pilotaż B2C (EN)
- [`docs/AI_FEATURES.md`](docs/AI_FEATURES.md): modele, przepływ danych, prywatność, walidacja (EN)
- [`docs/APP_PROTOCOL.md`](docs/APP_PROTOCOL.md): protokół backend ⇄ aplikacja (EN)
- [`AI_WORKFLOW.md`](AI_WORKFLOW.md): jak używaliśmy AI przy budowie (EN)
- `server/README.md`, `server/bench/README.md`, `app/README.md`, `scenarios/README.md`: szczegóły techniczne (EN)

## Użycie AI i usług zewnętrznych

- **W produkcie:** Whisper large-v3-turbo (OpenAI, MIT, przez whisper.cpp) i basal-1.0-4.5B (`Remek/basal-1.0-4.5B`, Apache 2.0, na bazie Bielika); oba uruchamiane lokalnie. Twilio za adapterem, w demo w trybie dry-run. Cloudflare Quick Tunnel tylko do demo.
- **Przy budowie:** Claude (Anthropic) i Claude Code, opis w `AI_WORKFLOW.md`. Rozmowy testowe w `scenarios/` napisał model językowy.

## Licencje

Backend ma w `server/pyproject.toml` licencję Apache-2.0, zbiór `scenarios/` jest na CC BY 4.0. Wagi modeli nie są w repozytorium i mają własne licencje (patrz wyżej). Materiały organizatorów i skille Huawei nie są dołączone.
