# Demo: checklista „setup od zera w 5 minut”

Sprzęt: **MacBook** (serwer, modele, projektor), **Samsung** z kartą SIM (telefon babci, kabel USB do Maca), **iPhone 1** (oszust, Safari), **iPhone 2** (wnuczka, odbiera SMS).
Wszystkie polecenia uruchamiamy w katalogu repo: `cd ~/Dev/HackYeah/2026/sprawdzam`.

## 0. Przed wejściem na salę (raz)

- [ ] Wszystko naładowane, Mac na zasilaczu (modele mocno grzeją), kabel USB-C do Samsunga i kabel do iPhone'a 1 (pokazywanie ekranu).
- [ ] Mac i iPhone 1 mają internet (hotspot albo Wi-Fi sali). Samsung internetu **nie potrzebuje**: łączy się z Makiem przez kabel. SMS idzie przez sieć komórkową.
- [ ] Samsung: apka zainstalowana (`app/scripts/install-demo-android.sh --serial RFCNC0JPWDM`), w ustawieniach apki osoba zaufana = „Wnuczka TEST”, zgoda na SMS. Wygaszanie ekranu: 10 min, tryb „Nie przeszkadzać” wyłączony, głośność rozmowy ok. 60%.
- [ ] Token urządzenia: w `server/.env.dev` ustaw losowy `APP_DEVICE_TOKEN` (`openssl rand -hex 16`), nie domyślny z repo (tunel jest publiczny), i przekaż go apce: `adb -s RFCNC0JPWDM shell am start -a android.intent.action.VIEW -d "'sprawdzam://config?url=ws://localhost:8765/app/control&token=<TOKEN>'" pl.sprawdzam.app`.
- [ ] iPhone 2: dźwięk SMS włączony, telefon pod ręką, żeby pokazać wiadomość.
- [ ] Wasze nagrania głosu zaimportowane (`server/scripts/samples/NAGRANIA.md`) i każde raz przepuszczone przez system.
- [ ] Nagrane wideo demo (plan B), patrz punkt 6.

## 1. Start (ok. 1 min, a modele ok. 3 min, jeśli nie chodzą)

```bash
scripts/demo-up.sh
```

Każdy krok ma się kończyć na zielono `ok`:

| Krok | Na co patrzeć |
| --- | --- |
| 1/5 Modele | `whisper` i `basal-1` działają (pierwsze uruchomienie basal-1 trwa do 3 min) |
| 2/5 Backend | `stt warmup: ok  decision warmup: ok  prompts: True  dry_run: True` |
| 3/5 Android | `adb reverse ... (SM-G996B)` i `USB watcher` (sam przywraca połączenie, gdy kabel mrugnie) |
| 4/5 Tunel | adres `https://….trycloudflare.com` |
| 5/5 Strony | otwierają się dwie karty: strona startowa z kodem QR i konsola jury |

Skrypt można puścić drugi raz w dowolnej chwili: niczego nie restartuje, tylko uzupełnia, czego brakuje. Nowy adres tunelu wymusza `scripts/demo-up.sh --new-tunnel`.

## 2. Telefony (ok. 1 min)

- **Samsung:** otwórz apkę Sprawdzam. Na ekranie ma być zielone **„Jesteś chroniony”** i „Osoba zaufana: Wnuczka TEST”. Zablokuj ekran.
- **iPhone 1:** zeskanuj aparatem kod QR ze strony startowej na Macu. Otworzy się „Symulator sieci operatora” w Safari. Wybierz **Nagrany skrypt** i **PL**. Odsłuch zostaw **wyłączony**.
- **iPhone 2:** odblokowany, leży obok.

## 3. Ekran na projektor (ok. 1 min)

- Konsola jury: karta `http://127.0.0.1:8765/dev/jury`, pełny ekran `Ctrl+Cmd+F`.
- Ekran Samsunga na Macu (okno obok konsoli albo na drugim pulpicie):

```bash
scrcpy -s RFCNC0JPWDM --no-audio --stay-awake --always-on-top --max-size 1200 --window-title "Telefon babci"
```

  `--no-audio` jest ważne: bez niego dźwięk rozmowy leciałby też z głośnika Maca (echo).
- Ekran iPhone'a (opcjonalnie): iPhone kablem do Maca, QuickTime Player → Plik → Nowe nagranie filmowe → strzałka obok przycisku nagrywania → wybierz iPhone'a jako kamerę.

## 4. Przebieg demo (2–3 min)

1. **Zwykła rozmowa** (iPhone 1: „Zwykła rozmowa” → Zadzwoń). Samsung budzi się z połączeniem na pełnym ekranie → **Odbierz**. Babcia odpowiada na żywo. Na konsoli wynik zostaje nisko, nic się nie dzieje. Rozłącz z iPhone'a.
2. **„Na policjanta”** (iPhone 1 → Zadzwoń → Samsung Odbierz). Babcia odpowiada („Policja? A co się stało?”). Kolejno: wykres rośnie, żółte ostrzeżenie, potem czerwony ekran i pytanie o hasło rodzinne z odliczaniem 12 s. Wpisz złe hasło albo poczekaj → **„Rozłączyliśmy podejrzaną rozmowę”** i „Wysłaliśmy SMS do: Wnuczka TEST”.
3. **iPhone 2:** pokaż SMS („Sprawdzam 05:12: babcia mogla rozmawiac z oszustem…”).
4. **Konsola → zakładka „Panel operatora”** (klawisz `2`): tak to widzi operator, bez treści rozmów.
5. Na Samsungu przycisk **„Zadzwoń do: Wnuczka TEST”** (rada policji: rozłącz się i oddzwoń do bliskich). Wystarczy pokazać, nie trzeba dzwonić.

Mówiąc na żywo jako oszust (Mikrofon na żywo): system rozłącza, gdy model jest pewny (90+) **i** padnie prośba o pieniądze albo „nikomu nie mów”. Bez tego tylko ostrzega.

Między próbami nic nie trzeba resetować: nowa rozmowa czyści widok „Na żywo”. Lista alertów u operatora zostaje do restartu backendu.

## 5. Gdy coś padnie

| Objaw | Co zrobić |
| --- | --- |
| Samsung: „Ochrona chwilowo niedostępna” | Sprawdź kabel USB i `adb devices`, potem `scripts/demo-up.sh`. Watcher zwykle sam naprawia w ciągu 5 s |
| Samsung nie dzwoni po „Zadzwoń” | Apka na Samsungu musi być otwarta lub w tle, a ekran główny zielony. Na emulatorze apka musi być zamknięta (skrypt ją zamyka). Spróbuj jeszcze raz |
| iPhone: strona się nie ładuje | `scripts/demo-up.sh --new-tunnel`, odśwież stronę startową, zeskanuj QR jeszcze raz |
| Brak internetu na sali | Symulator na Macu: `http://127.0.0.1:8765/dev/caller` (wtedy głos oszusta leci tylko z Samsunga, tak ma być) |
| Wykres stoi, brak transkrypcji | `curl -s 127.0.0.1:8765/health`: jeśli `warmup` nie jest `ok`, poczekaj albo zrestartuj modele (`scripts/demo-down.sh --all`, potem `scripts/demo-up.sh`) |
| SMS nie dochodzi | Ekran wyniku na Samsungu pokazuje, czy telefon go wysłał. Zasięg, karta SIM. Pokaż wynik na ekranie i jedź dalej |
| Echo / pisk | Ścisz Samsunga, odsuń iPhone'a 1 dalej od Samsunga |
| Wszystko leży | Puść nagrane wideo (punkt 6) |

## 6. Plan B: nagranie wideo (zrobić przed 10:00)

1. Ułóż na ekranie Maca konsolę jury i okno `scrcpy` obok siebie.
2. QuickTime Player → Plik → Nowe nagranie ekranu → nagraj cały ekran. W opcjach wybierz mikrofon Maca, żeby było słychać rozmowę.
3. Zagraj przebieg z punktu 4 (zwykła rozmowa, potem „na policjanta”, potem SMS na iPhonie 2 pokazany do kamery albo dograny zrzut ekranu).
4. Zapisz plik w dwóch miejscach (Mac + pendrive albo dysk w chmurze).

## 7. Po demo

```bash
scripts/demo-down.sh
```

Wyłącza tunel (strony demo przestają być dostępne z internetu), watcher USB i backend. `--all` wyłącza też modele.
