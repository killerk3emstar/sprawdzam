# Nagrania głosu do demo: instrukcja

Syntetyczne głosy z Maca brzmią sztucznie, więc sześć skryptów „dzwoniącego” nagrywamy sami. Nagranie zastępuje plik, który odtwarza strona `/dev/caller` (i skrypt testowy). Nie trzeba nic programować: nagrać, przesłać na Maca, uruchomić jedną komendę.

## 1. Nagraj na iPhonie

1. Otwórz aplikację **Dyktafon** (ang. Voice Memos).
2. Usiądź w cichym miejscu (bez muzyki, wentylatora, rozmów w tle). Na sali hackathonu najlepiej korytarz albo samochód.
3. Trzymaj telefon ok. 20–30 cm od ust, mikrofonem (dół telefonu) w swoją stronę.
4. Naciśnij czerwony przycisk i przeczytaj **jeden** skrypt z sekcji 4. Zatrzymaj nagranie.
5. Zmień nazwę nagrania (stuknij nazwę) na nazwę pliku z tabeli, np. `pl_scam_police`. To ułatwia późniejsze szukanie.

Jedno nagranie = jeden skrypt. Jeśli się pomylisz, nagraj całość od nowa, to szybsze niż montaż.

## 2. Wskazówki do czytania

- **Mów naturalnie**, jak w prawdziwej rozmowie telefonicznej. Oszust brzmi pewnie i trochę ponagla; wnuczka jest zdenerwowana; zwykła rozmowa jest spokojna i ciepła.
- **Między zdaniami rób pauzę ok. 1 sekundy.** System tnie mowę na kawałki właśnie po pauzach. Bez pauz kawałki są za długie i ocena ryzyka spóźnia się o kilka sekund.
- Nie szepcz i nie krzycz. Normalna głośność rozmowy.
- Nie czytaj za szybko. Całe nagranie powinno trwać **40–60 sekund**.
- Cisza na początku i na końcu nie przeszkadza, skrypt ją przytnie.
- Skrypty angielskie najlepiej nagrać głosem innej osoby niż polskie (brzmi wiarygodniej). Policjanta EN może nagrać mężczyzna, wnuczkę kobieta.

## 3. Przenieś na Maca i zaimportuj

1. W Dyktafonie: stuknij nagranie → `…` (trzy kropki) → **Udostępnij** → **AirDrop** → Mac zespołu. Plik trafi do `~/Downloads` (Pobrane), zwykle jako `.m4a`.
2. Na Macu otwórz Terminal i wpisz (podmień nazwę pliku i nazwę skryptu):

```bash
cd ~/Dev/HackYeah/2026/sprawdzam/server
scripts/import_recording.sh ~/Downloads/pl_scam_police.m4a pl_scam_police
```

Skrypt wypisze ścieżkę i długość nagrania, np. `data/samples/pl_scam_police.ulaw  53.1 s`. Stary plik z syntezatora zostaje w `data/samples/tts/` (można do niego wrócić). Przyjmuje też pliki `.mp3`, `.wav` i `.caf`.

3. Sprawdź na stronie `/dev/caller`, czy nagranie się odtwarza (słuchawki!) i czy w konsoli rośnie ryzyko.

Nagrania nie trafiają do repozytorium (katalog `data/` jest ignorowany przez git).

## 4. Skrypty do przeczytania

| Nazwa pliku | Język | Kto mówi | Czego oczekujemy |
| --- | --- | --- | --- |
| `pl_scam_police` | PL | fałszywa policjantka | ostrzeżenie, potem hasło rodzinne i rozłączenie |
| `pl_scam_grandchild` | PL | „wnuczka” po wypadku | ostrzeżenie, potem hasło rodzinne i rozłączenie |
| `pl_normal_grandchild` | PL | prawdziwa wnuczka | brak alarmu (pieniądze w zwykłym kontekście) |
| `en_scam_police` | EN | fake police officer | warning, family password, hang-up |
| `en_scam_grandchild` | EN | granddaughter in trouble | warning, family password, hang-up |
| `en_normal_grandchild` | EN | real granddaughter | no alarm |

Każde zdanie zaczyna się od nowej linii: po każdej linii zrób pauzę ok. 1 sekundy.

### `pl_scam_police`

> Dzień dobry, mówi komisarz Anna Wiśniewska z Centralnego Biura Śledczego Policji.
> Dzwonię do pani w bardzo pilnej sprawie.
> Ktoś próbuje wypłacić wszystkie pieniądze z pani konta w banku.
> To jest tajna akcja policji.
> Proszę nie mówić o tym nikomu, nawet rodzinie, ani córce, ani wnukom.
> Pracownik pani banku współpracuje z przestępcami.
> Musimy działać natychmiast, jeszcze dzisiaj.
> Proszę wypłacić całą gotówkę z banku i przekazać ją naszemu funkcjonariuszowi, który przyjedzie do pani domu.
> Może pani też zrobić przelew na bezpieczne konto policyjne.
> Jeśli pani komuś powie, akcja się nie uda i straci pani wszystkie oszczędności.
> Proszę się nie rozłączać.
> Ile ma pani teraz gotówki w domu?

### `pl_scam_grandchild`

> Babciu, cześć, to ja, twoja wnuczka.
> Babciu, stało się coś strasznego.
> Miałam wypadek samochodowy, potrąciłam kobietę na pasach.
> Jestem teraz na komisariacie policji.
> Policjant mówi, że jeśli dzisiaj nie zapłacę kaucji, pójdę do więzienia.
> Potrzebuję trzydziestu tysięcy złotych w gotówce, i to natychmiast.
> Babciu, nie mów nic mamie ani tacie, ani nikomu z rodziny.
> To ma być tajemnica, nie mów nikomu, bardzo cię proszę.
> Za godzinę przyjedzie po pieniądze pan mecenas, mój adwokat.
> Ile masz pieniędzy w domu?
> Jak nie masz, to idź szybko do banku i wypłać.
> Tylko w banku nie mów, na co to jest.

### `pl_normal_grandchild`

> Cześć babciu, tu Kasia.
> Dzwonię, bo dostałam od ciebie kartkę urodzinową i sto złotych, bardzo dziękuję.
> Kupię sobie za to książki na studia.
> Babciu, pamiętasz, że pożyczyłam od ciebie pieniądze w zeszłym miesiącu?
> Oddam ci je w niedzielę, jak przyjedziemy na obiad.
> Mama mówi, że będziemy około pierwszej.
> Upiekę sernik, taki jak lubisz.
> Czy mam ci coś kupić po drodze, może chleb albo mleko?
> A jak twoje kolano, byłaś już u lekarza?
> To dobrze.
> Dobrze, babciu, nie będę ci już przeszkadzać.
> Buziaki, do zobaczenia w niedzielę.

### `en_scam_police`

> Good afternoon, this is Detective Sergeant James Carter from the police fraud squad.
> I am calling about a very urgent matter.
> Someone is trying to withdraw all the money from your bank account.
> This is a confidential police operation.
> Please do not tell anyone about this call, not even your family.
> Someone at your bank branch is working with the criminals.
> We must act right now, today.
> You need to withdraw all your cash from the bank and hand it to our officer, who will come to your house this afternoon.
> Or you can transfer the money to a secure police account that I will give you.
> If you tell anyone, the operation will fail and you will lose all your savings.
> Please stay on the line.
> How much cash do you have at home right now?

### `en_scam_grandchild`

> Grandma, hi, it's me, your granddaughter.
> Grandma, something terrible has happened.
> I had a car accident, I hit a woman on a pedestrian crossing.
> I'm at the police station right now.
> The officer says that if I don't pay bail today, I will go to jail.
> I need ten thousand dollars in cash, right now.
> Please, Grandma, don't tell Mum or Dad, don't tell anyone in the family.
> This has to stay just between us.
> My lawyer will come to pick up the money in an hour.
> How much cash do you have at home?
> If you don't have enough, go to the bank quickly and withdraw it.
> And don't tell the bank what it's for.

### `en_normal_grandchild`

> Hi Grandma, it's Emma.
> I got your birthday card today, and the fifty dollars, thank you so much.
> I'm going to buy some books for university with it.
> And remember I borrowed some money from you last month?
> I'll pay you back on Sunday, when we come over for lunch.
> Mum says we'll be there around one.
> I'm baking a cheesecake, the one you like.
> Do you need anything from the shop on the way, maybe bread or milk?
> How is your knee, did you see the doctor?
> Oh, that's good.
> Okay Grandma, I won't keep you.
> Love you, see you on Sunday.

## 5. Gdy coś nie działa

- `error: no such file`: sprawdź nazwę pliku w `~/Downloads` (Finder → Pobrane). Spacje w nazwie: weź ścieżkę w cudzysłów albo przeciągnij plik do okna Terminala.
- `error: less than 1 s of audio`: nagranie jest puste albo bardzo ciche. Nagraj ponownie bliżej telefonu.
- `note: demo scripts are usually 40-60 s long`: tylko podpowiedź; nagranie działa, ale sprawdź, czy to cały skrypt.
- Ryzyko nie rośnie na `/dev/caller`: sprawdź, czy w nagraniu są pauzy między zdaniami, i czy działają modele (strona `/health`).
- Powrót do głosu z syntezatora: `mv data/samples/tts/pl_scam_police.ulaw data/samples/`.
