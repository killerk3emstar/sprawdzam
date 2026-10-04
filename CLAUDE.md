# Sprawdzam / Second Ear — instrukcje dla Claude Code

Hackathon HackYeah 2026 (Kraków, 3–4.10.2026). Dwie osoby, 24 h. Ten plik opisuje, **co budujemy, jakie decyzje już zapadły i jak z nami pracować**. Czytaj go na początku każdej sesji.

> **ZMIANA PLANU (niedziela 4.10, ok. 3:30).** Zgłaszamy **tylko do Defence**. Huawei i HarmonyOS są zamrożone: kodu nie usuwamy, ale go nie rozwijamy i nie pracujemy nad .hap. Pitch: **B2B dla operatorów** (moduł Sprawdzam na serwerach operatora dostaje kopię dźwięku rozmów z nieznanych numerów), apka na Androida to dodatek **B2C** i na niej robimy demo. Twilio zostaje za adapterem w trybie dry-run, nic nie kupujemy. **Zamrożenie funkcji 9:00, zgłoszenie 10:45.** Szczegóły w sekcji „Plan od 4.10, 3:30” niżej; tam, gdzie reszta pliku mówi o Huawei, obowiązuje ta zmiana.

Pełny plan dla ludzi (Claude Docs, nie otworzysz go z terminala): https://claude.ai/code/artifact/015c37c5-a70b-43ec-9dff-73d17d380d4b

## Jak z nami pracujesz

- **Rozmawiasz z nami po polsku.** Kod, komentarze, dokumentacja techniczna (`docs/`) i commity są po angielsku. **README jest po polsku** (Defence, decyzja 4.10). Teksty w UI są w dwóch językach (PL i EN).
- **Pytaj, gdy coś jest niejasne.** Przed większym krokiem (nowy moduł, zmiana architektury, nowa zależność, decyzja o UI) daj krótki plan i zbierz pytania w jednym miejscu. Do każdego pytania dodaj 2–3 opcje i swoją rekomendację.
- **Proponuj lepsze rozwiązania i mów o ryzykach.** Chcemy Twoich sugestii. Decyzji z sekcji „Decyzje” nie zmieniaj jednak bez naszej zgody: zaproponuj zmianę i poczekaj na odpowiedź.
- **Drobiazgi decydujesz sam.** Nazwy, struktura plików, drobne biblioteki i odwracalne szczegóły nie wymagają pytania.
- **Limit czasu.** Jeśli coś blokuje dłużej niż ok. 30 minut, przerwij i opisz sytuację: co próbowałeś, co widać w logach, jakie są opcje (plan B jest w tabeli ryzyk niżej).
- **Nie przesadzaj z „działa”.** Piszesz „sprawdzone” tylko wtedy, gdy coś faktycznie uruchomiłeś. Wieloetapowe klikanie po emulatorze zostaw nam: daj krótką instrukcję testu, a my opiszemy wynik.
- **Na koniec każdego zadania:** co zmieniłeś, co sprawdziłeś, czego nie sprawdziłeś, co zostaje do zrobienia lub zdecydowania po naszej stronie.

## Co budujemy

Ochrona seniorów przed oszustwami telefonicznymi („na wnuczka”, „na policjanta”, „na pracownika banku”). W 2023 roku policja odnotowała ponad 14 tys. takich oszustw, większość ofiar ma ponad 70 lat (Kwartalnik Policyjny 4/2025).

- Połączenia od kontaktów dzwonią normalnie i nikt ich nie analizuje.
- Numer spoza kontaktów: telefon go odrzuca, operator przekierowuje go („gdy zajęte”) do naszej usługi w chmurze. Dzwoniący słyszy komunikat o ochronie, a senior odbiera rozmowę w naszej apce (VoIP przez nasz backend).
- Backend zamienia mowę na tekst i na bieżąco ocenia ryzyko. Ryzyko średnie: ostrzeżenie głosowe i powiadomienie. Ryzyko wysokie: pytanie o hasło rodzinne, rozłączenie, telefon i SMS do osoby zaufanej (panel rodziny pominięty, decyzja 3.10).
- Nie zapisujemy audio ani transkrypcji, tylko krótkie streszczenie alertu. Nie rozpoznajemy emocji ani biometrii głosu (AI Act: rozpoznawanie emocji z głosu to system wysokiego ryzyka).

Pierwotnie zgłaszaliśmy jeden projekt do dwóch zadań (od 4.10, 3:30 **tylko Defence**, Huawei zamrożone):

- ~~**Huawei „Imagine What's Next”**~~ (zamrożone 4.10) (25 tys. zł): aplikacja na HarmonyOS/OpenHarmony z API 20+, paczka .hap, angielski. Pełne wymagania: `reference/challenges/huawei_challenge.md`.
- **Defence** (8 tys. zł): PL albo EN, PDF z maks. 10 slajdami. Kryteria: pomysł 30%, zgodność z kategorią 20%, użyteczność 20%, design 20%, kompletność 10%. Szczegóły: `reference/challenges/defence.md`.

Kryteria Huawei: oryginalność 20%, użyteczność 20%, wykonanie techniczne 20% (działa, testy, obsługa błędów, brak sekretów), **użycie możliwości platformy 20%** (apka, która działa wszędzie tak samo, dostaje tu mniej), demo 10%, odtwarzalność i przejrzystość pracy z AI 10%.

## Decyzje (nie zmieniaj bez pytania)

| Temat | Decyzja |
| --- | --- |
| **Zakres (4.10, 3:30)** | **Tylko Defence.** Huawei/HarmonyOS zamrożone (kod zostaje, bez rozwoju, bez .hap). Pitch B2B dla operatorów, demo na apce Android (B2C) |
| Apka | React Native **0.77.1** + RNOH **0.77.75** (`@react-native-oh/react-native-harmony`, `@react-native-oh/react-native-harmony-cli`). Jeden kod na Androida i HarmonyOS |
| Funkcje systemowe | Moduły natywne (TurboModules): ArkTS na HarmonyOS, Kotlin na Androidzie |
| Wersje SDK HarmonyOS | `compatibleSdkVersion` = `6.0.0(20)` (minimum wymagane przez Huawei, nie obniżać), kompilacja i cel API 24 (`6.1.1(24)`), emulator z najnowszym obrazem |
| Plan B dla RNOH | Jeśli do soboty 23:00 „hello world” z RN nie działa na emulatorze HarmonyOS: apka Huawei w ArkTS, Android zostaje w RN. Decyzję podejmujemy razem. **3.10, 22:33: GO dla RNOH** (hello world działa na emulatorze API 24, .hap ma min. API 20 i cel API 24, Android też się buduje), plan B nieaktywny |
| Backend | Python, FastAPI, WebSockety |
| Mowa na tekst | Whisper large-v3-turbo (whisper.cpp, `whisper-server` z Homebrew, Metal), na Macu natywnie, ok. 0,5 s na kawałek. Kawałki 3–8 s cięte po pauzach. Język wymuszony z ustawień seniora (PL albo EN) |
| Ocena ryzyka | **basal-1.0-4.5B** (`Remek/basal-1.0-4.5B`, polski model decyzyjny na bazie Bielika, Apache 2.0) + reguły słów kluczowych. Lżejszy zapas: `basal-1.0-1.5B` (to samo API, ok. 3 razy szybszy). Clef-Flash (`Cloudflare/clef-flash`, 19 GB) do porównania, głównie po angielsku, pobieramy dopiero, jeśli starczy czasu (łącze to hotspot). Zapas na CPU: embeddingi `PKOBP/embed-modernbert-68m` + regresja logistyczna |
| Telefonia | **Od 4.10: Twilio niepotrzebne do demo, zostaje za adapterem w dry-run, nic nie kupujemy.** Dawniej: Twilio, dwukierunkowe Media Streams (`<Connect><Stream>`; na koncie próbnym `<Stream>` jest zablokowany). Polski numer: Zadarma (przekierowanie na SIP → Twilio SIP Domain) albo numer Twilio PL; numer z USA tylko awaryjnie. Zakup konta (min. 20 USD) odkładamy do pierwszego prawdziwego telefonu; kod operatora siedzi za adapterem, tańsza alternatywa to SignalWire (cXML, ok. 5 USD, cena niesprawdzona) |
| Testy połączeń w trakcie budowy | Z przeglądarki, przez nasze strony `/dev/caller` (dzwoniący, format Twilio Media Streams) i `/dev/senior` (zastępuje apkę), bez operatora i bez kosztów. Z telefonu tylko test przekierowania i demo |
| Wdrożenie | docker compose. Na Macu modele działają natywnie (Docker na Macu nie daje kontenerom GPU), backend w kontenerze łączy się z nimi przez `host.docker.internal`. Na AWS jedna maszyna EC2 + Caddy z automatycznym HTTPS |
| Języki | PL i EN wszędzie: UI, komunikaty głosowe, rozpoznawanie mowy, reguły, scenariusze testowe |
| UI apki seniora | Minimalny, duży, kontrastowy: jeden duży status na ekranie głównym, pełnoekranowe połączenie przychodzące i ostrzeżenie, ustawienia schowane. Tekst od 24 pt, przyciski od 56 dp, kontrast WCAG AA (decyzja 3.10) |
| Ekran dla jury / panel operatora (4.10) | Strona na MacBooku (projektor): transkrypcja na żywo obu stron, wykres ryzyka z progami 50 i 90, powody i typ oszustwa, akcje; dopisek „Tryb demonstracyjny. W produkcji treść rozmów nie jest wyświetlana.” Druga zakładka: lista alertów jak u operatora, bez treści rozmów |
| SMS do osoby zaufanej (4.10) | Wysyła **telefon babci** (`SmsManager`, `SEND_SMS` w czasie działania, numer z ustawień) po wiadomości z backendu o rozłączeniu z powodu oszustwa; treść bez polskich znaków i linków; maks. jeden alert na rozmowę po stronie serwera |
| Reguły vs rozłączenie (4.10) | Same reguły mogą ostrzegać, **nie mogą rozłączać** (nie rozumieją zaprzeczeń). Analizujemy też wypowiedzi seniora |
| Panel rodziny | **Pomijamy** (decyzja 3.10). Rodzina dostaje SMS i telefon do osoby zaufanej. Hasło rodzinne na razie w `.env` (`FAMILY_PASSWORD`), ewentualnie później w ustawieniach apki |
| Funkcje HarmonyOS w apce | Notification Kit (alerty), Contacts Kit (osoba zaufana i biała lista), Call Service Kit (voipCall) po krótkim teście na emulatorze. Widżet odpuszczamy (decyzja 3.10) |

## Plan od 4.10, 3:30 (Defence)

Sprzęt na demo: iPhone 1 = oszust, Android z kartą SIM = telefon babci, iPhone 2 = wnuczka (osoba zaufana), MacBook = serwer z modelami i ekran na projektor. Emulator Androida służy do pracy; prawdziwy SMS wyśle tylko fizyczny Android.

Priorytety, jeśli zabraknie czasu:

1. Pełny przepływ na fizycznym Androidzie z symulatorem sieci (`/dev/caller` jako „Symulator sieci operatora”: Safari na iPhonie przez Cloudflare Tunnel, duży przycisk „Zadzwoń”, nagrany skrypt albo mikrofon; skrypty PL/EN: policjant, wnuczek, zwykła rozmowa; zapas: laptop). Na telefonie: pełny ekran połączenia, odbiór, dźwięk w obie strony, pasek ryzyka z powodami, klawiatura hasła rodzinnego, rozłączenie, ekran wyniku. Echo: domyślnie skrypt z pliku, sprawdzić, czy głos z głośnika apki nie wraca jako wypowiedź seniora.
2. SMS do osoby zaufanej z telefonu babci (rozszerzenie protokołu v0 w `docs/APP_PROTOCOL.md`).
3. Ekran dla jury i panel operatora.
4. Analiza wypowiedzi seniora i reguły bez rozłączania; fail-open (apka: „Ochrona chwilowo niedostępna”, komunikat „proszę zadzwonić później” usunąć/zmienić).
5. README po polsku, `docs/ARCHITECTURE.md` (sekcje „Docelowe wdrożenie u operatora” i „Pilotaż B2C z przekierowaniem i routing”, wyraźnie oznaczone jako zaprojektowane, nie zbudowane).
6. Routing na wspólny numer (dopasowanie po zgłoszeniu z apki „odrzuciłam +48…, godz. …”), tylko jeśli zostanie czas.

Na koniec: checklista „setup od zera w 5 minut” (modele → backend → tunel → apka → strony; `scrcpy` dla Androida, QuickTime dla iPhone'a; plan B: nagranie wideo demo). Kryteria Defence: pomysł 30%, zgodność z kategorią 20%, użyteczność 20%, design 20%, kompletność 10%; PDF maks. 10 slajdów; trzeba ujawnić użycie AI i usług zewnętrznych.

## Architektura

```
Dzwoniący ──► telefon seniora (odrzuca nieznany numer) ──► operator przekierowuje
     ──► numer (Twilio / Zadarma→SIP→Twilio) ──► komunikat o ochronie
     ──► <Connect><Stream> wss:// ──► backend FastAPI
            ├─ audio μ-law 8 kHz → 16 kHz → VAD (Silero) → Whisper (kawałki 2–4 s)
            ├─ ocena: basal-1 (schemat pytań) + reguły → wynik wygładzony
            ├─ akcje: ostrzeżenie, hasło rodzinne, rozłączenie (Twilio REST), telefon + SMS do osoby zaufanej
            └─ przekazywanie dźwięku w obie strony: Twilio ⇄ WS /app/{callId} ⇄ apka seniora
     (panel rodziny pominięty; alerty idą SMS-em i telefonem do osoby zaufanej)
```

### Moduły natywne

| Moduł | HarmonyOS (ArkTS) | Android (Kotlin) | Po co |
| --- | --- | --- | --- |
| CallEngine | WebSocket + AudioCapturer i AudioRenderer w trybie rozmowy | AudioRecord i AudioTrack | Dźwięk rozmowy z backendu i z powrotem |
| Ekran połączenia | Call Service Kit (voipCall), jeśli działa na emulatorze | Ekran w apce | Rozmowa wygląda jak zwykłe połączenie |
| Filtr połączeń | Brak (odrzucanie to API systemowe), więc przekierowanie bezwarunkowe + biała lista w chmurze | CallScreeningService | Odrzucanie numerów spoza kontaktów |
| Kontakty | Contacts Kit | ContactsContract | Biała lista, wybór osoby zaufanej |
| Alerty | Notification Kit | NotificationManager | Ostrzeżenie na ekranie |
| Widżet | Karta na ekranie głównym (FormExtensionAbility) | Opcjonalnie | Status ochrony, punkty za platformę |

Uprawnienia tylko te potrzebne: mikrofon, internet, odczyt kontaktów, powiadomienia; na Androidzie rola filtra połączeń.

### Ocena ryzyka (basal-1)

`basal-serve` wystawia `POST /v1/systemone` (repo: https://github.com/rkinas/basal). Na Macu działa tryb `--mode mps` (GPU Apple) z naszą łatką `--share-state` (wszystkie pytania w jednym przebiegu, ok. 2,2 razy szybciej; `server/bench/basal/basal-share-state.patch`). Zmierzone na M4 Pro (szczegóły w `server/bench/README.md`): samo `risk` 0,76 s, `risk` + `scam_type` 1,07 s, 6 pytań 1,94 s, ok. 10 GB pamięci. Dlatego co 3–4 s pytamy tylko o `risk` (z `scam_type`), a pełne 6 pytań liczymy raz, po ostrzeżeniu, do streszczenia alertu. Serwery modeli uruchamiamy skryptami `server/bench/run-whisper.sh` i `run-basal.sh` (słuchają na 127.0.0.1). Przy starcie backend wysyła zapytanie rozgrzewające; timeout 3 s.

Szkic schematu (do dopracowania razem z nami):

```json
{
  "state": "<ostatnie ~60 s transkryptu z oznaczeniem, kto mówi>",
  "questions": {
    "money": {"type": "noul", "instructions": "Does the caller ask for money, a bank transfer, cash handover or a BLIK code?"},
    "secrecy": {"type": "noul", "instructions": "Does the caller ask to keep the call secret from family or the bank?"},
    "authority": {"type": "noul", "instructions": "Does the caller claim to be police, a bank, a prosecutor or another authority?"},
    "urgency": {"type": "noul", "instructions": "Does the caller pressure the person to act immediately?"},
    "scam_type": {"type": "choice", "instructions": "Which scam pattern fits best?",
      "criteria": {"none": "Normal conversation", "grandchild": "Relative in trouble needs money", "police": "Fake police officer or prosecutor", "bank": "Fake bank employee, account at risk", "other": "Another fraud pattern"}},
    "risk": {"type": "score", "instructions": "How likely is this call a scam?",
      "criteria": {"low": "No signs", "medium": "Some warning signs", "high": "Clear scam pattern", "critical": "Money is about to be handed over"}}
  }
}
```

Wynik modelu: `100·(1−P(low))` z pytania `risk` (model prawie nigdy nie wybiera „critical”, więc oczekiwany poziom nie przekracza ok. 65). Progi (decyzja 3.10, do strojenia na `scenarios/`): ostrzeżenie przy ≥50 dwa odczyty z rzędu; hasło rodzinne i rozłączenie, gdy **sam wynik modelu** ≥90 dwa odczyty z rzędu **oraz** (`secrecy` ≥0,8 albo trafienie reguły albo `money` ≥0,5 z modelu; `money` dodane 4.10 po teście na żywo bez wzmianki o tajemnicy). Same reguły tylko ostrzegają (4.10). Łączenie z regułami: max(model, reguły). Wygładzanie jest konieczne: zwykła rozmowa o pożyczce dla syna skoczyła na jeden odczyt do 58. Whisper zapisuje kwoty cyframi („30 tysięcy”, „200 zł”), więc reguły łapią też cyfry. Reguły (PL i EN: BLIK, przelew, gotówka, „nikomu nie mów”, policja, prokurator…) to bezpiecznik, gdy model się pomyli. Obsłuż: timeout modelu, błąd HTTP, dziwną odpowiedź. Wtedy działają same reguły, a w logach jest ślad.

Ewaluacja: kilkaset syntetycznych rozmów w `scenarios/` (oszustwa i zwykłe rozmowy, także o pieniądzach w rodzinie, PL i EN). Porównujemy basal, Clef-Flash i same reguły: precyzja, czułość, macierz pomyłek, wyniki w README.

### Zachowanie przy awarii

Jeśli backend albo model nie działa, połączenia przechodzą normalnie (fail-open), a apka pokazuje „ochrona chwilowo niedostępna”. To ważne i dla Defence (ciągłość działania), i dla Huawei (obsługa błędów).

## Bezpieczeństwo (Huawei to sprawdza)

- Twilio → backend tylko po `wss://`. Sprawdzamy podpis `X-Twilio-Signature` na webhookach.
- Backend ↔ apka: WSS (TLS), jednorazowy token na rozmowę ważny kilka minut.
- Audio i transkrypt tylko w RAM, kasowane po rozmowie. Zapisujemy samo streszczenie alertu.
- Sekrety w `.env` (wzór w `.env.example`), nigdy w repo ani w historii. Plików do podpisu (`.p12`, `.cer`, `.p7b`) nie commitujemy.
- Repo jest publiczne od początku: przed każdym commitem sprawdź `git status` i `git diff`.

## Struktura repo (propozycja)

```
app/          React Native 0.77.1 (TypeScript)
  harmony/    kontener HarmonyOS (init-harmony) + moduły ArkTS
  android/    kontener Android + moduły Kotlin
server/       FastAPI: webhook Twilio, WebSockety, STT, ocena ryzyka, akcje
panel/        (pominięty, decyzja 3.10)
scenarios/    rozmowy testowe PL i EN
deploy/       docker-compose.yml, Caddyfile
docs/         ARCHITECTURE.md, AI_FEATURES.md
reference/    materiały organizatorów (wymagania, FAQ Huawei, emulator); w .gitignore, bo nie mają licencji
AI_WORKFLOW.md
```

## Środowisko na Macu (Apple Silicon, 48 GB RAM)

- DevEco Studio 6.1.1.280 jest w `/Applications/DevEco-Studio.app` (wbudowane SDK HarmonyOS 6.1.1, API 24). Narzędzia CLI 6.1.1.280 rozpakowane w `~/command-line-tools` (to samo SDK, na tym Macu duplikat). Ścieżki do PATH:
  `export DEVECO_SDK_HOME="/Applications/DevEco-Studio.app/Contents/sdk"`
  `export PATH="$DEVECO_SDK_HOME/default/openharmony/toolchains:/Applications/DevEco-Studio.app/Contents/tools/ohpm/bin:/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin:$PATH"`
- Łącze to hotspot z telefonu: unikaj dużych pobrań bez pytania.
- DevEco Studio: po pierwszym uruchomieniu zamknij je i ustaw region na Chiny, bo inaczej emulator ma tylko zegarki: `~/Library/Application Support/Huawei/DevEcoStudio6.1/options/country.region.xml` → `<countryregion name="CN"/>` (zrobione 3.10).
- Emulator tworzymy sami w GUI (Device Manager → Phone → najnowszy obraz). Ty z niego korzystasz przez `hdc`. Jest: Pura 90, HarmonyOS 6.1.1 (API 24), `hdc` widzi go jako `127.0.0.1:5555`. Niepodpisany debug HAP instaluje się na emulatorze bez konta. Audio na emulatorze: nagrywanie działa ze źródłem `SOURCE_TYPE_MIC` (tryb `VOICE_COMMUNICATION` się zacina), odtwarzanie idzie na głośnik. Testy z dźwiękiem albo wymagające kliknięć zapowiadaj nam wcześniej (co robimy, na co patrzymy) i nie puszczaj głośnych tonów na sali.
- Debug build z DevEco działa bez konta. Do podpisanego .hap na zgłoszenie potrzebne jest konto Huawei Developer.
- Node: domyślny `node` to v26, ale `app/` budujemy na Node 22 (`/opt/homebrew/opt/node@22/bin`, `app/.nvmrc`). Android SDK jest w `~/Library/Android/sdk`; do Gradle używaj `JAVA_HOME=/opt/homebrew/opt/openjdk@21` (Java 25 z Android Studio jest za nowa dla RN 0.77). Python w backendzie: 3.12 przez `uv`.
- W `.claude/skills/` są skille od Huawei (ArkTS, ArkUI, praca z aplikacją). Nie commitujemy ich, bo repo Huawei nie ma licencji (są w `.gitignore`); źródło: https://github.com/onirodeveloper/hackyeah2026-challenge. Część z nich zakłada `devecocli` (`@deveco/deveco-cli` 1.3.4, Node 22+). Instalator Huawei był tylko na Windows, więc na Macu sprawdź, czy da się go zainstalować, zanim na nim oprzesz pracę.

### Start projektu RN na HarmonyOS (zweryfikuj z dokumentacją RNOH 0.77)

Zrobione 3.10. Sprawdzone komendy (bundle, build HAP z CLI, instalacja, Metro, build Androida) i znane problemy RNOH 0.77.75 są w `app/README.md`. Ścieżka do repo musi być krótka (hvigor/pnpm: `ENAMETOOLONG`). Poniżej pierwotny plan.

1. `npx @react-native-community/cli init Sprawdzam --version 0.77.1` (potem przenieś do `app/` albo użyj odpowiedniej opcji katalogu).
2. `npm i --save-exact @react-native-oh/react-native-harmony@0.77.75 @react-native-oh/react-native-harmony-cli@0.77.75`
3. `npx react-native init-harmony --bundle-name pl.sprawdzam.app` (tworzy katalog `harmony/` z szablonu).
4. W `harmony/build-profile.json5` ustaw wersje SDK jak w tabeli decyzji. Szablon ma `5.0.0(12)`, a tego nie zostawiamy.
5. `npx react-native bundle-harmony --dev`, potem build i instalacja przez `hvigorw`/`hdc` albo `npx react-native run-harmony`.

Dokumentacja RNOH (EN): https://gitcode.com/CPF-RN/ohos_react_native/tree/0.77-main/docs/en. Przykład od Oniro (https://github.com/eclipse-oniro4openharmony/app-rnoh-example) jest na RN 0.72 i API 12, więc służy tylko do podglądu. Bierz tylko biblioteki RN, które mają port na HarmonyOS; WebSocket i fetch są w samym RN.

## Ryzyka i plan B

| Ryzyko | Jak sprawdzamy | Plan B |
| --- | --- | --- |
| RNOH nie buduje się na API 20+ albo na Macu | „Hello world” na emulatorze do 23:00 | Apka Huawei w ArkTS, Android w RN |
| basal-1 za wolny na Macu | Czas decyzji w trybie eager + 20 rozmów testowych | Clef-Flash; potem klasyfikator PKO BP + reguły |
| Mikrofon albo głośnik nie działa na emulatorze | Pierwszy test CallEngine | Telefon Huawei od mentorów |
| Call Service Kit nie działa na emulatorze | Pytanie do mentorów | Własny ekran połączenia w apce |
| Brak polskiego numeru na czas | Status weryfikacji w Zadarma i Twilio | Numer z USA, dzwonimy prosto na niego |
| Odrzucenie nie uruchamia przekierowania „gdy zajęte” | Test `**67*<numer>#` na naszych kartach | Przekierowanie bezwarunkowe + biała lista w chmurze |
| Whisper za wolny albo słaby na audio 8 kHz | Nagrany skrypt oszustwa przez telefon | Parakeet TDT 0.6B v3; awaryjnie Amazon Transcribe przez adapter |
| Limit 0 na maszyny GPU w AWS | Service Quotas | Na AWS wersja bez GPU: Transcribe + basal eager albo klasyfikator na CPU |

## Harmonogram (sobota → niedziela)

- 21:00–23:00: konfiguracja. A: Twilio, numer, modele, repo, szkielet backendu. B: DevEco, emulator, RNOH „hello world”.
- 23:00: decyzja w sprawie RNOH.
- 23:00–02:00: A: potok audio i ocena ryzyka. B: ekrany RN i CallEngine.
- 02:00–04:00: razem pierwsza pełna rozmowa od dzwoniącego do alertu.
- 04:00–07:00: na zmianę sen; Android i test przekierowania; Docker na AWS i testy.
- 07:00–09:00: wygląd, PL/EN, README, podpisany .hap.
- 09:00–10:45: nagranie demo, PDF, zgłoszenia. **Termin: niedziela 11:00.**

## Wymagane na koniec (Defence, od 4.10)

- [ ] PDF, maks. 10 slajdów (PL albo EN)
- [ ] Demo na żywo: iPhone (symulator sieci) → Android babci → SMS do wnuczki; ekran jury na projektorze
- [ ] Nagranie wideo demo jako plan B
- [ ] README po polsku, `docs/ARCHITECTURE.md`, `docs/AI_FEATURES.md`, `AI_WORKFLOW.md` (ujawnienie AI i usług zewnętrznych)
- [ ] Brak sekretów w repo i w historii

## Wymagane na koniec (Huawei, zamrożone 4.10)

- [ ] Publiczne repo z historią commitów
- [ ] README: wersje (DevEco, SDK, Node, RNOH), build, instalacja, uruchomienie od zera
- [ ] Podpisana paczka .hap
- [ ] Krótkie nagranie demo z emulatora
- [ ] `docs/ARCHITECTURE.md`: architektura i implementacja
- [ ] `AI_WORKFLOW.md`: wszystkie narzędzia AI, główne prompty, przebieg pracy, jak weryfikowaliśmy, co nie wyszło
- [ ] `docs/AI_FEATURES.md`: modele, przepływ danych, prywatność, ograniczenia, walidacja, zachowanie przy błędach
- [ ] Testy kluczowych scenariuszy (silnik ryzyka, błędna odpowiedź modelu, timeout, brak sieci)
- [ ] Brak sekretów w repo i w historii

## AI_WORKFLOW.md (wymóg Huawei, 10% oceny)

Na początku każdej sesji przeczytaj `AI_WORKFLOW.md` i dopisz nowe narzędzia (model, agent, MCP, skill). Po każdym większym kawałku pracy dopisz wiersz do dziennika: zadanie, co powstało, jak to sprawdziliśmy. Bez sekretów i danych osobowych. Nie loguj każdej komendy.

## Git

- Jeśli nie ma `.gitignore`, dodaj go przed pierwszym commitem (build, cache DevEco, `oh_modules`, `node_modules`, `.env`, pliki do podpisu).
- Commituj często, małymi działającymi krokami, z opisowymi wiadomościami po angielsku.
- Ryzykowne rzeczy rób na osobnych gałęziach. Gałąź `main` ma się zawsze budować. Scalanie do `main` zostaw nam.

## Pierwsza sesja (zrobione 3.10)

1. Przeczytaj ten plik, `reference/challenges/huawei_challenge.md`, `reference/hackathon-resources/emulator-capability-comparison.md` i `AI_WORKFLOW.md`. Dopisz Claude Code z wersją do tabeli narzędzi.
2. Sprawdź środowisko: `node -v`, `python3 --version`, `git`, `brew`, `uv`, Android SDK, DevEco Studio w `/Applications`, zawartość obu ZIP-ów z `~/Downloads`.
3. Zainicjuj git, jeśli go nie ma (pierwszy commit: `CLAUDE.md`, `AI_WORKFLOW.md`, `.gitignore`, `.env.example`).
4. Zaproponuj podział pierwszej godziny na dwie osoby (A: backend i AI, B: apka) i zadaj pytania, które blokują start.

## Otwarte pytania (pytaj, gdy staną się potrzebne)

- ~~Czy jeden projekt można zgłosić do Defence i Huawei?~~ Nieaktualne: od 4.10 tylko Defence.
- (Nieaktualne od 4.10) Odpowiedzi mentorów Huawei: Call Service Kit i mikrofon na emulatorze, znane problemy RNOH 0.77 z API 20+, podpis .hap pod ich telefon.
- Który numer przejdzie weryfikację (Zadarma, Twilio PL)?
- Czy mamy konto AWS i jaki ma limit na maszyny z GPU?
- ~~Hasło rodzinne ustawiane w panelu rodziny?~~ Panel pominięty (3.10): hasło w `.env`, później może w ustawieniach apki.
