# Sprawdzam: ściąga dla osób od prezentacji i pitchu

Bez żargonu. Wszystko, co trzeba wiedzieć, żeby opowiedzieć o projekcie i odpowiedzieć na pytania jury.
Stan: niedziela 4.10, rano. Wszystko z sekcji 3 i 5 działa i było sprawdzone na prawdziwych telefonach (Samsung jako telefon babci, iPhone jako oszust), chyba że przy danej rzeczy jest napisane inaczej.

---

## 1. O co chodzi, w jednym zdaniu

**Sprawdzam słucha rozmów z nieznanych numerów i przerywa je, zanim senior odda pieniądze oszustowi „na wnuczka” albo „na policjanta”.**

## 2. Problem

- Oszustwa telefoniczne na seniorach („na wnuczka”, „na policjanta”, „na pracownika banku”): w 2023 roku policja odnotowała **ponad 14 tys.** takich przestępstw; większość ofiar ma **ponad 70 lat** (Kwartalnik Policyjny 4/2025).
- Scenariusz jest zawsze podobny: ktoś podaje się za krewnego lub instytucję, wywiera presję czasu, każe nikomu nie mówić i prosi o gotówkę, przelew albo kod BLIK.
- Kampanie społeczne pomagają, ale w trakcie rozmowy senior jest sam, w stresie i pod presją.

## 3. Rozwiązanie

„Drugie ucho” w trakcie rozmowy:

1. Rozmowa z **nieznanego numeru** (spoza kontaktów) przechodzi przez Sprawdzam. Rozmowy od rodziny i znajomych nikt nie analizuje.
2. Sztuczna inteligencja na bieżąco zamienia mowę na tekst i ocenia, czy rozmowa wygląda na oszustwo (skala 0–100).
3. Gdy robi się podejrzanie (**50+**), senior dostaje **ostrzeżenie** na ekranie i głosem.
4. Gdy to wyraźne oszustwo (**90+**), system **pyta dzwoniącego o hasło rodzinne** (prawdziwy wnuczek je zna, oszust nie; na odpowiedź jest 12 sekund), **rozłącza rozmowę** i **wysyła SMS do osoby zaufanej** (np. córki), np.: „Sprawdzam 04:31: babcia mogla rozmawiac z oszustem (falszywy policjant, prosba o gotowke, nr ...123). Zadzwon do niej.”
5. Jeśli rodzina nie ustawiła hasła, telefon pokazuje **„Rozłączam za 8 s”** i jeden duży przycisk **„Rozłącz teraz”**. Gdy babcia sama się rozłączy przy wysokim ryzyku, to też liczy się jako zablokowane oszustwo i SMS idzie do rodziny. (Ten wariant sprawdziliśmy na emulatorze i w testach, na prawdziwym telefonie jeszcze go nie pokazywaliśmy.)
6. Po rozłączeniu telefon pokazuje przycisk **„Zadzwoń do: …”** (np. do wnuczki, czyli osoby zaufanej, na jej prawdziwy numer). To dokładnie rada policji: rozłącz się i oddzwoń do bliskich na numer, który znasz.

Senior nie musi niczego obsługiwać. Nie musi nawet wiedzieć, że to oszustwo.

**Kiedy system rozłącza?** Same „podejrzane słowa” nie wystarczą. Model AI musi dwa razy z rzędu ocenić rozmowę na 90+ **i** do tego musi być konkretny sygnał: dzwoniący prosi o tajemnicę, prosi o pieniądze albo padają typowe słowa oszustów (BLIK, gotówka, „nikomu nie mów”). Pieniądze dodaliśmy rano po teście na żywo: „oszust” improwizował, nie prosił o tajemnicę, model był pewny na 98–99, a system nie rozłączał. Teraz rozłącza.

## 4. Dwa modele biznesowe

| | **B2B: operator komórkowy** (główny) | **B2C: aplikacja dla rodziny** (dodatek) |
| --- | --- | --- |
| Kto płaci | Operator (np. jako usługa „Bezpieczny Senior” w abonamencie) | Rodzina seniora (subskrypcja) |
| Jak działa | Moduł Sprawdzam stoi **na serwerach operatora** i dostaje kopię dźwięku rozmów z nieznanych numerów u abonentów, którzy wykupili usługę | Apka na telefonie seniora; nieznane numery są przekierowywane do naszej usługi |
| Zaleta | Działa na **każdym telefonie**, także „z klapką”, bez instalowania czegokolwiek. Operator widzi też **kampanie**: ten sam numer dzwoni do wielu seniorów | Można zacząć od razu, bez umowy z operatorem |
| Stan | **Zaprojektowane, nie zbudowane** (opis w `docs/ARCHITECTURE.md`) | **Działa w demo** na prawdziwym telefonie z Androidem |

Na pitchu: B2B to skala i biznes, B2C to dowód, że technologia działa (pokazujemy ją na żywo).

## 5. Co pokazujemy na demo

| Urządzenie | Rola | Co widać |
| --- | --- | --- |
| iPhone | **Oszust**. Strona „Symulator sieci operatora” zastępuje prawdziwą sieć komórkową (otwiera się z kodu QR) | Duży przycisk „Zadzwoń”, wybór scenariusza (policjant, wnuczek, zwykła rozmowa) albo mówienie na żywo do mikrofonu |
| Samsung (Android) | **Telefon babci** z apką Sprawdzam | Połączenie przychodzące na pełnym ekranie, pasek ryzyka z powodami, prośba o hasło z odliczaniem, rozłączenie, „Zadzwoń do: …” |
| Telefon osoby zaufanej | **Wnuczka / córka** | Przychodzi prawdziwy SMS z ostrzeżeniem, wysłany z telefonu babci |
| MacBook + projektor | **Serwer i ekran dla jury** | Na żywo: co mówią obie strony, wykres ryzyka z liniami 50 i 90, powody (pieniądze, tajemnica, podszywanie się pod instytucję, presja czasu), podjęte akcje. Druga zakładka **„Panel operatora”**: lista alertów jak u operatora, **bez treści rozmów** |

Scenariusze rozmów nagraliśmy **własnymi głosami** (nie syntezatorem), więc na sali słychać prawdziwą mowę.

Proponowany przebieg (ok. 2–3 min):

1. **Zwykła rozmowa** (wnuczek dzwoni pogadać, wspomina o pieniądzach): wykres zostaje nisko, nic się nie dzieje. Pokazuje, że nie panikujemy przy każdym słowie „pieniądze”.
2. **„Na policjanta”**: wykres rośnie, babcia dostaje ostrzeżenie, potem system pyta o hasło (odliczanie na ekranie), rozłącza, a osoba zaufana dostaje SMS-a. Pokazać SMS-a i przycisk „Zadzwoń do: …” na telefonie babci.
3. Przełączyć ekran jury na zakładkę **„Panel operatora”**: tak widzi to operator, bez treści rozmów.

Na ekranie jury jest dopisek: „Tryb demonstracyjny. W produkcji treść rozmów nie jest wyświetlana.” Warto to powiedzieć na głos.

Zespół techniczny stawia całe demo jedną komendą (modele, serwer, tunel do iPhone'a, kod QR, ekran jury). Lista kontrolna: `docs/DEMO_CHECKLIST.md`. Plan B: nagranie wideo demo.

## 6. Liczby, które możemy podawać (i jak je opisywać)

Test na **300 rozmowach testowych** (polskich i angielskich, połowa to oszustwa, połowa zwykłe rozmowy, w tym trudne: syn naprawdę pożycza pieniądze, prawdziwy bank, kurier z pobraniem):

- **Wykrywa 150 na 150 oszustw** (próg ostrzeżenia).
- Fałszywe ostrzeżenia przy zwykłych rozmowach: **7%**. Rozłączenie zwykłej rozmowy: **1%** (1 na 150) w teście zasady „rozłącza tylko model AI, nie same słowa kluczowe”. Obecna zasada wymaga jeszcze sygnału tajemnicy, pieniędzy albo słów kluczowych, więc może być tylko ostrożniejsza; tego dokładnego wariantu nie przeliczaliśmy ponownie.
- Ostrzeżenie pojawia się średnio po **ok. 12 sekundach** mowy oszusta.
- Dlaczego słuchamy też seniora: gdy analizujemy tylko dzwoniącego, fałszywych ostrzeżeń jest **26%** zamiast 7%. Zdanie babci „na to samo konto co zawsze?” zmienia sens rozmowy.

**Uczciwie (mówić, jeśli jury dopyta):** rozmowy testowe są **syntetyczne**, napisała je sztuczna inteligencja, więc wyniki są optymistyczne. Na prawdziwych rozmowach będą gorsze. Nie mamy jeszcze danych od policji ani operatora; to pierwszy krok pilotażu.

## 7. Prywatność i prawo (pytania jury na pewno padną)

- **Nie nagrywamy.** Dźwięk i tekst rozmowy są tylko w pamięci serwera w trakcie rozmowy i znikają po jej końcu. Zostaje krótkie streszczenie alertu (np. „fałszywy policjant, prośba o gotówkę”).
- **Analizujemy tylko nieznane numery** i tylko u osób, które się zgodziły (abonent usługi).
- **Nie rozpoznajemy emocji ani głosu** (biometrii). Unijny AI Act traktuje rozpoznawanie emocji jako system wysokiego ryzyka, więc świadomie tego nie robimy. Oceniamy wyłącznie **treść**: o co dzwoniący prosi.
- **Modele AI działają na naszym serwerze** (w przyszłości u operatora), nie wysyłamy rozmów do zewnętrznych firm typu OpenAI czy Google.
- Szczegóły prawne (tajemnica telekomunikacyjna, podstawa prawna u operatora) wymagają konsultacji z prawnikami. Mówimy to wprost.

## 8. Co jeśli coś nie działa?

**Zasada: lepiej przepuścić rozmowę niż zablokować prawdziwą.** Jeśli serwer albo AI padnie, rozmowy mają przechodzić normalnie, a apka pokazuje „Ochrona chwilowo niedostępna” (to widzieliśmy na żywo, gdy rozłączył się kabel). Senior nigdy nie zostaje bez telefonu przez naszą awarię.

- Pada sam model AI: działa dziś, zostają słowa kluczowe (mogą ostrzec, nie rozłączą).
- Apka babci nie jest połączona: dzwoniący słyszy „Łączę bez ochrony” i rozmowa idzie prosto do babci. Zbudowane, ale z prawdziwym operatorem jeszcze niesprawdzone.
- Pada cały serwer: przepuszczanie rozmów ustawia się u operatora telefonii; to projekt, nie zbudowane.

Dodatkowo:

- Słowa kluczowe (BLIK, przelew, „nikomu nie mów”, policja…) działają jako zabezpieczenie, gdy AI zawiedzie, ale **mogą tylko ostrzec, nigdy rozłączyć**. Nie rozumieją zaprzeczeń: zdanie „bank nigdy nie prosi o BLIK” zawiera słowo BLIK, a nie jest oszustwem.
- Rozłączenie wymaga **dwóch wysokich ocen modelu z rzędu** i konkretnego sygnału (tajemnica, pieniądze albo słowa oszustów). Pojedyncze przejęzyczenie nie wystarczy.
- Hasło rodzinne to ostatnia szansa dla prawdziwego wnuczka. A po rozłączeniu babcia jednym przyciskiem dzwoni do bliskiej osoby.
- Słuchamy też babci, ale głośnik telefonu wraca do mikrofonu (echo). Filtr echa to wycina: w jednej rozmowie na żywo wyrzucił 17 takich fragmentów, żeby system nie pomylił słów oszusta ze słowami babci.

## 9. Jak to działa w środku (wersja na 30 sekund)

```
dzwoniący → sieć operatora → Sprawdzam (serwer)
                               1. zamiana mowy na tekst (Whisper)
                               2. ocena ryzyka (basal-1, polski model AI) + słowa kluczowe
                               3. akcje: ostrzeżenie → hasło → rozłączenie → SMS do rodziny
                            ⇄ telefon seniora (apka) / docelowo zwykły telefon przez operatora
```

- **Whisper**: model AI zamieniający mowę na tekst, open source, działa na naszym komputerze. Ok. 0,5 s na kawałek mowy.
- **basal-1**: polski model AI, który odpowiada na pytania o rozmowę („czy dzwoniący prosi o pieniądze?”, „czy każe zachować tajemnicę?”, „czy podaje się za policję?”). Ok. 0,8 s na ocenę.
- Wszystko działa na jednym MacBooku; u operatora byłby to kontener na jego serwerach.

## 10. Czego nie ma (żeby nie obiecać za dużo)

- Brak umowy i integracji z operatorem; część B2B to projekt.
- W demo zamiast prawdziwej sieci komórkowej jest „Symulator sieci operatora” (strona w przeglądarce). Prawdziwa telefonia (Twilio) jest przygotowana w kodzie, ale nie kupowaliśmy numeru.
- Tylko język polski i angielski.
- Wersja na Huawei/HarmonyOS powstała w nocy, ale jej nie rozwijamy; zgłaszamy projekt tylko do Defence.

## 11. Pytania, których się spodziewamy

| Pytanie | Odpowiedź w skrócie |
| --- | --- |
| „A jak oszust zna hasło rodzinne?” | Hasło to dodatkowa bariera, nie jedyna. SMS do rodziny idzie i tak, a rodzina może oddzwonić |
| „Co, jeśli prawdziwy wnuczek ma kłopoty?” | Zna hasło, a nawet jeśli rozmowa się przerwie, babcia ma przycisk „Zadzwoń do: …”, a rodzina dostaje SMS-a; wyjaśnia to jeden telefon na znany numer (tak radzi policja) |
| „A jak rodzina nie ustawi hasła?” | Wtedy przy wyraźnym oszustwie telefon odlicza 8 sekund z przyciskiem „Rozłącz teraz” i rozłącza; SMS do rodziny idzie tak samo |
| „Czy to podsłuch?” | Nie nagrywamy, nie przechowujemy treści, analizujemy tylko nieznane numery za zgodą abonenta. Operator i tak przetwarza te rozmowy, żeby je zestawić |
| „Dlaczego operator miałby to kupić?” | Usługa dodatkowa w abonamencie, mniej reklamacji i strat klientów, wizerunek, dane o kampaniach oszustów dla CERT i policji |
| „Ile kosztuje?” | Modele są open source; koszt to moc obliczeniowa u operatora. Nie mamy jeszcze wyceny, mówimy to otwarcie |
| „Czym to się różni od blokowania spamu?” | Spam blokuje się po numerze. Oszuści zmieniają numery codziennie; my rozpoznajemy **treść** rozmowy |
| „Czy użyliście AI do budowy?” | Tak, jawnie: Claude (Anthropic) do planowania i pisania kodu. Pełny opis jest w `AI_WORKFLOW.md`. Modele w produkcie: Whisper i basal-1, oba działają lokalnie |

## 12. Słowniczek

- **Operator**: Play, Orange, T-Mobile, Plus.
- **B2B / B2C**: sprzedaż firmie (operatorowi) / sprzedaż klientowi indywidualnemu (rodzinie).
- **Transkrypcja**: zamiana mowy na tekst.
- **Fałszywe ostrzeżenie**: system ostrzegł przy zwykłej rozmowie.
- **Fail-open**: przy awarii system „otwiera drzwi”, czyli rozmowy przechodzą normalnie.
- **Tryb demonstracyjny**: tylko na pokazie widać treść rozmowy na ekranie; w produkcji nikt jej nie widzi.
