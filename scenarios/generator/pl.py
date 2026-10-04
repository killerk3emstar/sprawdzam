"""Polish call families. Each builder returns a list of (speaker, text) turns before noise.

Slots: senior gender ({pani}, {pania}, {pana}, {panu}, {babciu}, {ss} ...), grandchild gender
({wn}, {gn}, {gv}, {ga}, {gs} ...) and amounts are filled per call, so one template yields many
grammatical variants. All names are generic placeholders; phone numbers are obviously fake.
"""

from __future__ import annotations

import random

from common import C, S, maybe, one

F_SENIORS = [("Halina", "Nowak"), ("Krystyna", "Kowalska"), ("Danuta", "Wiśniewska"), ("Teresa", "Zielińska"),
             ("Barbara", "Wójcik"), ("Irena", "Kamińska"), ("Janina", "Lewandowska"), ("Zofia", "Dąbrowska")]
M_SENIORS = [("Józef", "Nowak"), ("Zdzisław", "Kowalski"), ("Stanisław", "Wiśniewski"), ("Tadeusz", "Zieliński"),
             ("Kazimierz", "Wójcik"), ("Henryk", "Kamiński"), ("Jerzy", "Lewandowski"), ("Ryszard", "Dąbrowski")]
M_KIDS = [("Michał", "Michał"), ("Kuba", "Kuba"), ("Bartek", "Bartku"), ("Tomek", "Tomku"), ("Piotrek", "Piotruś"),
          ("Kacper", "Kacper"), ("Szymon", "Szymek"), ("Paweł", "Pawełku"), ("Adam", "Adaś")]
F_KIDS = [("Kasia", "Kasiu"), ("Ola", "Olu"), ("Ania", "Aniu"), ("Marta", "Martusiu"), ("Zuzia", "Zuziu"),
          ("Natalia", "Natalko"), ("Magda", "Madziu"), ("Julia", "Julciu")]
CITIES = ["Krakowie", "Warszawie", "Katowicach", "Łodzi", "Poznaniu", "Tarnowie", "Kielcach", "Rzeszowie", "Gdańsku"]
OFFICERS = ["Jan Kowalski", "Marek Zając", "Adam Nowicki", "Robert Mazur", "Krzysztof Wrona", "Paweł Sowa"]
RANKS = ["aspirant", "komisarz", "starszy aspirant", "podkomisarz", "sierżant"]
BANKS = ["banku Horyzont", "banku Wisła Plus", "banku Sokół", "banku Mazowia", "banku Kotwica"]  # indeclinable after "banku"
FAKE_PHONES = ["500 000 000", "123 456 789", "600 100 200", "700 800 900", "511 222 333"]


def slots(r: random.Random) -> dict:
    fem = r.random() < 0.6
    first, last = r.choice(F_SENIORS if fem else M_SENIORS)
    kid_m = r.random() < 0.6
    gn, gv = r.choice(M_KIDS if kid_m else F_KIDS)
    return {
        "first": first, "last": last,
        "pani": "pani" if fem else "pan", "pania": "panią" if fem else "panem", "pana": "pani" if fem else "pana",
        "panu": "pani" if fem else "panu", "babciu": "babciu" if fem else "dziadku",
        "babcia": "babcia" if fem else "dziadek", "babci": "babci" if fem else "dziadka",
        "babcie": "babcię" if fem else "dziadka", "ss": "am" if fem else "em", "sa": "a" if fem else "",
        "sama": "sama" if fem else "sam", "moglaby": "mogłaby pani" if fem else "mógłby pan",
        "mogla": "mogła" if fem else "mógł", "tato": "mamo" if fem else "tato", "mama": "mama" if fem else "tata",
        "mamie": "mamie" if fem else "tacie", "sl": "ła" if fem else "ł",
        "wn": "wnuczek" if kid_m else "wnuczka", "wnu": "wnuka" if kid_m else "wnuczki", "wna": "wnuczka" if kid_m else "wnuczkę",
        "gn": gn, "gv": gv, "ga": "" if kid_m else "a", "gs": "em" if kid_m else "am", "gs2": "eś" if kid_m else "aś",
        "on": "on" if kid_m else "ona", "jego": "jego" if kid_m else "jej", "go": "go" if kid_m else "ją",
        "mu": "mu" if kid_m else "jej", "syn": "syn" if kid_m else "córka", "synu": "synu" if kid_m else "córciu",
        "moglem": "mogłem" if kid_m else "mogłam", "sam_g": "sam" if kid_m else "sama",
        "city": r.choice(CITIES), "officer": r.choice(OFFICERS), "rank": r.choice(RANKS), "bankn": r.choice(BANKS),
        "phone": r.choice(FAKE_PHONES),
    }


def amount(r: random.Random, thousands: list[int]) -> str:
    n = r.choice(thousands)
    return one(r, [f"{n} tysięcy złotych", f"{n} tysięcy zł", f"{n} 000 zł", f"{n} tys. zł", f"{n} tysięcy"])


def small(r: random.Random, values: list[int]) -> str:
    n = r.choice(values)
    return one(r, [f"{n} zł", f"{n} złotych", f"{n} złotych"])


SENIOR_SHOCK = ["o matko", "jezus maria", "boże drogi", "o rany", "ale jak to?", "matko święta, co się stało?"]
SENIOR_DOUBT = ["ale ja nie wiem", "muszę się zastanowić", "a skąd mam wiedzieć, że to prawda?", "to jakieś dziwne",
                "nie wiem, czy to dobry pomysł"]
SENIOR_OK = ["no dobrze", "dobrze, dobrze", "aha, rozumiem", "mhm", "tak, słucham", "no tak"]


# =========================================================================================== scams
def grandchild_accident(r, s, hard):
    s["amt"] = amount(r, [15, 20, 25, 30, 40, 50, 60])
    t = []
    if hard:
        t += [(C, one(r, ["halo, {babciu}? to ja", "{babciu}, cześć, zgadnij kto dzwoni", "dzień dobry {babciu}, poznajesz mnie?"])),
              (S, one(r, ["{gv}? to ty?", "a kto mówi? {gv}?", "nie poznaję, kto to? {gv}?"])),
              (C, one(r, ["no tak, to ja, {gn}. mam straszny katar, dlatego tak mówię", "tak, {gn}. dzwonię od kolegi, mój telefon się rozładował",
                          "pewnie że ja. jestem przeziębion{ga}, chrypię"])),
              (S, one(r, ["dawno nie dzwonił{gs2}, co u ciebie?", "a jak zdrowie, jak w pracy?", "o, jak miło, co słychać?"])),
              (C, one(r, ["różnie, {babciu}, nie najlepiej szczerze mówiąc", "no właśnie nie za dobrze, dlatego dzwonię",
                          "ogólnie dobrze, ale mam mały kłopot"])),
              (S, one(r, ["a co się stało?", "jaki kłopot?", "mów, dziecko"]))]
        t += [(C, one(r, ["jechał{gs} wczoraj wieczorem i wjechała we mnie taka pani, znaczy ja w nią, nie wiem jak to się stało",
                          "miał{gs} stłuczkę, nic mi nie jest, ale ta druga osoba jest w szpitalu",
                          "był{gs} na imprezie i pożyczył{gs} auto kolegi, no i jest problem, rozbił{gs} je"])),
              (S, one(r, SENIOR_SHOCK)),
              (C, one(r, ["spokojnie, {babciu}, jest załatwione prawie wszystko, jest tu ze mną pan mecenas, on mi pomaga",
                          "rozmawiał{gs} już z adwokatem, mówi, że da się to załatwić polubownie, bez sądu",
                          "ta pani się zgodziła, żeby nie zgłaszać sprawy, jak pokryjemy koszty leczenia"])),
              (S, one(r, ["no i co teraz?", "a rodzice wiedzą?", "to dobrze, że nic ci nie jest"])),
              (C, one(r, ["i tu jest ta sprawa, głupio mi pytać, ale potrzebuję trochę pomocy, takiej finansowej",
                          "{babciu}, nie chcę cię martwić, ale potrzebuję pożyczyć, oddam w miesiąc, przysięgam",
                          "rodzicom nie mogę powiedzieć, bo tata mnie zabije. ty jesteś jedyną osobą, która może pomóc"])),
              (S, one(r, ["ile potrzebujesz?", "a ile to by było?", "nie wiem, czy mam tyle"])),
              (C, one(r, ["mecenas mówi, że {amt}. ile masz w domu?", "chodzi o {amt}, ale jak masz mniej, to daj ile możesz",
                          "{amt}, wiem, że to dużo"]))]
        t += [(S, one(r, ["w domu to mam może z 8 tysięcy", "trzymam trochę na czarną godzinę", "musiał{sa}bym iść do banku"])),
              (C, one(r, ["to wystarczy na początek. za godzinę przyjedzie do ciebie kolega mecenasa, odbierze, ja nie mogę wyjść",
                          "przyjdzie po to pan Robert, asystent mecenasa, daj mu w kopercie", "ja sam{ga} nie mogę przyjechać, przyjedzie kolega"])),
              (S, one(r, SENIOR_DOUBT + SENIOR_OK))]
        if r.random() < 0.5:
            t += [(C, one(r, ["i proszę, nie dzwoń teraz do mamy, ona ma serce, sam{ga} jej powiem", "tylko nie mów nic rodzicom, dobrze?"]))]
    else:
        t += [(C, one(r, ["{babciu}, to ja, {gn}, ratuj mnie", "{babciu}, to ja, mam wielki problem", "halo {babciu}? {babciu}, stało się coś strasznego"])),
              (S, one(r, ["{gv}? co się stało?", "kto mówi? {gv}?", "dziecko, co się dzieje?"])),
              (C, one(r, ["miał{gs} wypadek, potrącił{gs} kobietę na pasach, ona jest w ciąży i jest w szpitalu",
                          "spowodował{gs} wypadek, jest ranna kobieta, policja mnie zatrzymała",
                          "wjechał{gs} w samochód na skrzyżowaniu, ten pan jest w ciężkim stanie"])),
              (S, one(r, SENIOR_SHOCK)),
              (C, one(r, ["grozi mi więzienie, {babciu}, ale jest możliwość, żeby zapłacić i sprawa się zakończy",
                          "jest tu mecenas, mówi, że jak dzisiaj wpłacimy kaucję, to nie pójdę do aresztu",
                          "muszę zapłacić tej rodzinie za leczenie, inaczej sprawa pójdzie do prokuratora"])),
              (S, one(r, ["ile trzeba?", "ile pieniędzy?", "jezu, ile to kosztuje?"])),
              (C, one(r, ["{amt}, i to jeszcze dzisiaj", "potrzebuję {amt} na dziś", "{amt}, ile masz w domu gotówki?"])),
              (S, one(r, ["tyle nie mam w domu", "mam trochę oszczędności w szafie", "musiał{sa}bym iść do banku"])),
              (C, one(r, ["to idź do banku i wypłać, tylko szybko, nie ma czasu", "daj ile masz, resztę wypłać z banku",
                          "wypłać z konta, ja ci wszystko oddam"])),
              (C, one(r, ["przyjedzie po pieniądze kolega mecenasa, daj mu w kopercie", "za godzinę przyjdzie kurier i odbierze gotówkę",
                          "przyjedzie pan od adwokata, przekażesz mu pieniądze"])),
              (S, one(r, SENIOR_OK + SENIOR_DOUBT)),
              (C, one(r, ["i nikomu nie mów, ani mamie, ani sąsiadom, bo będzie jeszcze gorzej", "tylko nie dzwoń do rodziców, proszę, nikomu nie mów",
                          "nie mów nikomu, mecenas mówi, że to tajemnica śledztwa"]))]
    return t


def grandchild_doctor(r, s, hard):
    """Fake doctor: grandchild in hospital, needs an expensive drug or operation now (labelled grandchild)."""
    s["amt"] = amount(r, [12, 18, 24, 35, 48])
    t = [(C, one(r, ["dzień dobry, doktor Marek Nowicki, szpital wojewódzki w {city}", "dzień dobry, mówi lekarz dyżurny, oddział chirurgii, szpital w {city}"])),
         (S, one(r, ["dzień dobry, słucham", "tak? o co chodzi?"])),
         (C, one(r, ["czy to {pani} {first} {last}? przywieźli do nas {pana} {wna} po wypadku, {gn}",
                     "dzwonię w sprawie {pana} {wnu}, {gn}, jest u nas na oddziale"])),
         (S, one(r, SENIOR_SHOCK)),
         (C, one(r, ["stan jest poważny, ale stabilny. potrzebna jest operacja jeszcze dzisiaj", "jest przytomn{ga}, ale potrzebuje leku, którego nie refunduje NFZ"]))]
    if hard:
        t += [(S, "czy mogę z nim porozmawiać?" if s["ga"] == "" else "czy mogę z nią porozmawiać?"),
              (C, "teraz nie, jest po znieczuleniu. proszę się nie martwić, robimy wszystko co trzeba"),
              (S, one(r, ["a co mam zrobić?", "a rodzice już wiedzą?"])),
              (C, one(r, ["rodzice nie odbierają, dlatego dzwonimy do {pana}. jest jeszcze sprawa formalna", "nie możemy się dodzwonić do rodziców. jest jeden problem, lek jest z importu"]))]
    t += [(C, one(r, ["lek kosztuje {amt}, musimy go zamówić w ciągu godziny", "operacja w prywatnej klinice to koszt {amt}, a czas ucieka"])),
          (S, one(r, ["skąd ja wezmę tyle pieniędzy?", "ile? ja tyle nie mam", "boże, a co jeśli nie zapłacę?"])),
          (C, one(r, ["może {pani} przekazać gotówkę naszemu pracownikowi, przyjedzie za pół godziny", "wystarczy przelew na konto fundacji szpitala, podyktuję numer",
                      "może {pani} wypłacić w banku i przekazać kurierowi szpitala"])),
          (S, one(r, SENIOR_DOUBT + SENIOR_OK))]
    if r.random() < 0.6:
        t += [(C, one(r, ["proszę się pospieszyć i nie tracić czasu na telefony, każda minuta się liczy", "proszę działać natychmiast"]))]
    return t


def grandchild_newnumber(r, s, hard):
    """'Mum, I changed my number' pattern: friendly chat, then an urgent loan by transfer or BLIK."""
    s["amt"] = small(r, [1800, 2400, 3500, 4200, 4900, 6000])
    t = [(C, one(r, ["cześć {tato}, to ja, {gn}. piszę, znaczy dzwonię z nowego numeru, stary telefon mi się zepsuł",
                     "hej {tato}, to ja, zapisz sobie ten numer, stary przestał działać"])),
         (S, one(r, ["o, cześć {synu}. a co się stało z telefonem?", "{gv}? masz jakiś inny głos", "aha, dobrze, zapiszę"])),
         (C, one(r, ["wpadł mi do wody, no nieważne. co u ciebie?", "zepsuł się, oddał{gs} do serwisu. jak się czujesz?", "mam przeziębienie, stąd ten głos. a jak u was?"])),
         (S, one(r, ["wszystko dobrze, byłam dzisiaj na zakupach", "a po staremu, kolano trochę boli", "dobrze, ojciec ogląda mecz"] if s["sa"] == "a"
                    else ["wszystko dobrze, byłem dzisiaj na działce", "po staremu, kręgosłup trochę boli", "dobrze, matka ogląda serial"]))]
    if hard:
        t += [(C, one(r, ["to super. słuchaj, mam taką sprawę, trochę mi głupio", "fajnie. a słuchaj, masz dostęp do bankowości w telefonie?"])),
              (S, one(r, ["no mów", "mam, ale mało z niej korzystam", "a o co chodzi?"])),
              (C, one(r, ["muszę dziś zapłacić fakturę, a na nowym telefonie nie mam jeszcze aplikacji banku, nie mogę się zalogować",
                          "mam pilną płatność za mieszkanie, a bank zablokował mi kartę jak zmieniałem telefon"]))]
    else:
        t += [(C, one(r, ["słuchaj, potrzebuję pilnie pieniędzy, muszę dziś zapłacić fakturę", "{tato}, mam problem, potrzebuję pilnie przelewu"]))]
    t += [(C, one(r, ["możesz zrobić przelew {amt}? jutro ci oddam, jak tylko odblokuję konto", "pożycz mi {amt}, oddam jutro rano",
                      "wyślij mi {amt} blikiem, ja ci podam numer telefonu"])),
          (S, one(r, ["a na jakie konto?", "ale ja nie umiem robić blika", "aż tyle?", "dobrze, ale jak to zrobić?"])),
          (C, one(r, ["podam ci numer konta, to konto kolegi, on mi przeleje dalej", "wygeneruj kod blik w aplikacji i mi go podyktuj",
                      "to proste, zaraz cię przeprowadzę"])),
          (C, one(r, ["tylko musi być dzisiaj, do 15, bo będzie kara", "szybko, proszę, bo zamykają o 15"]))]
    if r.random() < 0.6:
        t += [(S, one(r, ["może zadzwonię do ciebie na stary numer?", "może zadzwonię do ojca, on się zna" if s["sa"] == "a" else "może zadzwonię do matki, ona się zna"])),
              (C, one(r, ["nie, stary nie działa mówiłem. i nie mów tacie, bo zrobi aferę", "nie trzeba, nikomu nie mów, sam{ga} wszystko wyjaśnię"]))]
    return t


def police_bail(r, s, hard):
    s["amt"] = amount(r, [20, 30, 40, 50, 70, 80])
    t = [(C, one(r, ["dzień dobry, {rank} {officer}, komenda miejska policji w {city}", "dzień dobry, policja, {rank} {officer}, komenda w {city}",
                     "mówi {rank} {officer} z komendy policji w {city}"])),
         (C, one(r, ["czy to {pani} {first} {last}?", "czy to {pani} {last}?"])),
         (S, one(r, ["tak, to ja. co się stało?", "tak, słucham, o co chodzi?", "tak. coś się stało?"]))]
    if hard:
        t += [(C, one(r, ["proszę się nie denerwować, nikomu z pani rodziny nic poważnego się nie stało" if s["pani"] == "pani" else "proszę się nie denerwować, nikt z rodziny nie jest w niebezpieczeństwie",
                          "dzwonię w sprawie {pana} wnuka {gn}" if s["ga"] == "" else "dzwonię w sprawie {pana} wnuczki {gn}"])),
              (S, one(r, ["ale co się stało?", "matko, mów pan"])),
              (C, one(r, ["doszło do zdarzenia drogowego, {gn} kierował{ga} samochodem i potrącił{ga} rowerzystę", "{gn} brał{ga} udział w bójce, jest ranny człowiek"])),
              (S, one(r, SENIOR_SHOCK)),
              (C, one(r, ["rowerzysta jest w szpitalu. {gn} jest u nas na komendzie, jest cał{ga} i zdrow{ga}", "jest teraz u nas, przesłuchujemy świadków"])),
              (C, one(r, ["sprawą zajmuje się prokurator. w takich sprawach jest możliwość zastosowania poręczenia majątkowego zamiast aresztu",
                          "prokurator rozważa areszt tymczasowy, ale jest procedura, która to wstrzymuje"])),
              (S, one(r, ["a co to znaczy?", "nie rozumiem, co mam zrobić?"])),
              (C, one(r, ["chodzi o wpłatę poręczenia w kwocie {amt}, pieniądze wracają po zakończeniu sprawy",
                          "trzeba złożyć zabezpieczenie, {amt}, to jest zwrotne"]))]
    else:
        t += [(C, one(r, ["{pana} {wn} {gn} spowodował{ga} wypadek, ranna jest kobieta w ciąży", "{gn}, {pana} {wn}, potrącił{ga} dziecko na przejściu"])),
              (S, one(r, SENIOR_SHOCK)),
              (C, one(r, ["grozi mu do 8 lat więzienia" if s["ga"] == "" else "grozi jej do 8 lat więzienia", "prokurator chce wnioskować o areszt"])),
              (C, one(r, ["żeby uniknąć aresztu, trzeba dziś wpłacić kaucję {amt}", "kaucja wynosi {amt}, płatna jeszcze dzisiaj"])),
              (S, one(r, ["ile? ja tyle nie mam", "boże, skąd ja wezmę tyle pieniędzy", "a ile mam czasu?"]))]
    t += [(C, one(r, ["ile ma {pani} w domu w gotówce?", "jaką kwotę może {pani} przekazać od razu?", "proszę sprawdzić, ile ma {pani} gotówki"])),
          (S, one(r, ["w domu może z 10 tysięcy", "mam trochę odłożone", "resztę mam w banku"])),
          (C, one(r, ["za godzinę przyjedzie do {pana} nasz funkcjonariusz po cywilnemu i odbierze pieniądze", "przyjedzie kurier z komendy, proszę mu przekazać gotówkę w kopercie",
                      "resztę proszę wypłacić w banku, przyjedziemy po wszystko"]))]
    if not hard or r.random() < 0.6:
        t += [(C, one(r, ["proszę nikomu o tym nie mówić, ani rodzinie, ani w banku, bo utrudni to śledztwo", "to jest tajemnica śledztwa, nie wolno o tym nikomu mówić",
                          "proszę nie dzwonić do córki, bo to może zaszkodzić {gn}"]))]
    t += [(S, one(r, SENIOR_OK + SENIOR_DOUBT))]
    return t


def police_cbs(r, s, hard):
    s["amt"] = amount(r, [40, 60, 80, 100, 120])
    t = [(C, one(r, ["dzień dobry, {rank} {officer}, centralne biuro śledcze policji", "dzień dobry, CBŚP, {rank} {officer}",
                     "komisarz {officer}, wydział do walki z przestępczością gospodarczą"])),
         (S, one(r, ["dzień dobry", "słucham?", "tak?"]))]
    if hard:
        t += [(C, one(r, ["proszę się nie niepokoić, nic złego {panu} nie grozi. prowadzimy postępowanie i potrzebujemy pomocy",
                          "dzwonię, bo {pana} dane pojawiły się w sprawie, którą prowadzimy. {pani} jest osobą pokrzywdzoną"])),
              (S, one(r, ["a skąd mam wiedzieć, że pan jest z policji?", "ale o co chodzi?", "jaką sprawę?"])),
              (C, one(r, ["bardzo dobrze, że {pani} pyta. proszę rozłączyć się i zadzwonić na 997, połączą {pana} ze mną",
                          "rozumiem ostrożność. proszę zadzwonić pod 112 i zapytać o mnie, nie odkładając słuchawki"])),
              (S, one(r, ["dobrze, to zadzwonię", "aha, no dobrze"])),
              (C, one(r, ["chodzi o pracownicę {bankn}, która wyprowadza pieniądze z kont seniorów", "w {bankn} działa grupa, która przelewa środki klientów za granicę"])),
              (C, one(r, ["{pana} oszczędności mogą być zagrożone. musimy je zabezpieczyć zanim oni je wypłacą", "chcemy złapać ich na gorącym uczynku, potrzebna jest {pana} pomoc"])),
              (S, one(r, ["a co ja mam zrobić?", "jak mogę pomóc?"]))]
    else:
        t += [(C, one(r, ["{pana} pieniądze w banku są zagrożone, oszuści przejęli {pana} konto", "prowadzimy akcję przeciwko oszustom w {bankn}, {pana} konto jest zagrożone"])),
              (S, one(r, SENIOR_SHOCK)),
              (C, one(r, ["musimy natychmiast zabezpieczyć {pana} pieniądze", "trzeba działać natychmiast, zanim oni je wypłacą"]))]
    t += [(C, one(r, ["proszę pójść do banku, wypłacić {amt} i przekazać je naszemu funkcjonariuszowi", "proszę wypłacić oszczędności i wpłacić je przez wpłatomat na konto techniczne policji",
                      "proszę wypłacić pieniądze, zapakować w reklamówkę i zostawić przy furtce, nasz człowiek je odbierze"])),
          (S, one(r, ["ale wszystkie?", "a dostanę je z powrotem?", "a jak w banku zapytają po co?"])),
          (C, one(r, ["pieniądze wrócą na {pana} konto po zakończeniu akcji, za 2 dni", "wszystko zostanie zwrócone, dostanie {pani} pokwitowanie"])),
          (C, one(r, ["w banku proszę powiedzieć, że to na remont, nie wolno mówić o akcji", "kasjerka może być w zmowie, proszę nic nie mówić",
                      "proszę nikomu nie mówić, nawet rodzinie, to tajna operacja"])),
          (C, one(r, ["proszę się nie rozłączać, będę z {pania} na linii cały czas", "zadzwonię za godzinę, proszę być w domu i nie rozmawiać z nikim"])),
          (S, one(r, SENIOR_OK + SENIOR_DOUBT))]
    return t


def bank_security(r, s, hard):
    s["amt"] = small(r, [2400, 3850, 4999, 7200, 9500, 12000])
    t = [(C, one(r, ["dzień dobry, Anna Michalska, dział bezpieczeństwa {bankn}", "dzień dobry, dzwonię z działu bezpieczeństwa {bankn}, nazywam się Tomasz Lis",
                     "dzień dobry, konsultant {bankn}, dzwonię w sprawie {pana} konta"])),
         (S, one(r, ["dzień dobry", "tak? słucham", "a o co chodzi?"]))]
    if hard:
        t += [(C, one(r, ["dla bezpieczeństwa najpierw potwierdzę, czy to {pani} {first} {last}?", "czy rozmawiam z właścicielem rachunku? {pani} {first} {last}?"])),
              (S, "tak, to ja"),
              (C, "dziękuję. nasz system zauważył nietypową operację na {pana} rachunku, chcemy tylko potwierdzić"),
              (C, one(r, ["czy zlecała pani płatność na {amt} do sklepu internetowego?", "czy próbowała pani zalogować się dziś z nowego telefonu?"]) if s["sa"] == "a" else
               one(r, ["czy zlecał pan płatność na {amt} do sklepu internetowego?", "czy próbował pan zalogować się dziś z nowego telefonu?"])),
              (S, one(r, ["nie, nic takiego nie robiłam" if s["sa"] == "a" else "nie, nic takiego nie robiłem", "nie, ja nie kupuję w internecie"])),
              (C, one(r, ["dobrze, że dzwonimy. operacja jest wstrzymana, ale musimy zabezpieczyć konto", "w takim razie ktoś ma dostęp do {pana} danych. spokojnie, pomogę to zablokować"])),
              (S, one(r, ["a co trzeba zrobić?", "matko, a pieniądze są bezpieczne?"])),
              (C, one(r, ["proszę zainstalować aplikację do weryfikacji, nazywa się QuickSupport, przeprowadzę {pana} krok po kroku",
                          "zaraz przyjdzie SMS z kodem, proszę mi go przeczytać, to zablokuje transakcję",
                          "przeniesiemy środki na nowy, bezpieczny rachunek, a stary zamkniemy"]))]
    else:
        t += [(C, one(r, ["na {pana} koncie wykryliśmy podejrzaną transakcję na {amt}", "ktoś próbuje zaciągnąć kredyt na {pana} dane", "{pana} konto zostało zaatakowane przez hakerów"])),
              (S, one(r, SENIOR_SHOCK)),
              (C, one(r, ["żeby zablokować przelew, proszę podać kod blik", "proszę podać numer karty i kod z SMS-a", "musimy przelać pieniądze na bezpieczne konto techniczne",
                          "proszę zainstalować aplikację AnyDesk, zabezpieczę konto zdalnie"]))]
    t += [(S, one(r, ["a to jest bezpieczne?", "ale ja się na tym nie znam", "nie wiem, czy mogę to podać przez telefon"])),
          (C, one(r, ["oczywiście, rozmowa jest nagrywana i szyfrowana", "proszę się nie martwić, jestem pracownikiem banku", "to standardowa procedura bezpieczeństwa"])),
          (C, one(r, ["musimy to zrobić natychmiast, za 15 minut przelew zostanie zaksięgowany", "nie ma czasu, każda minuta się liczy", "proszę się pospieszyć"]))]
    if r.random() < 0.6:
        t += [(C, one(r, ["i proszę nie rozmawiać o tym z nikim, w oddziale może być osoba współpracująca z oszustami", "proszę nie dzwonić na infolinię, bo przestępcy podsłuchują",
                          "proszę o tym nie mówić rodzinie, to poufne postępowanie"]))]
    if r.random() < 0.3:
        t += [(C, "zaraz zadzwoni do {pana} policjant, który prowadzi tę sprawę, proszę wykonać jego polecenia")]
    t += [(S, one(r, SENIOR_OK + SENIOR_DOUBT))]
    return t


def investment(r, s, hard):
    s["amt"] = small(r, [800, 1000, 2000, 5000, 10000])
    t = [(C, one(r, ["dzień dobry, Piotr Lewandowski, doradca inwestycyjny", "dzień dobry, dzwonię z platformy inwestycyjnej Złoty Kapitał",
                     "dzień dobry, Karolina z działu inwestycji, czy to {pani} {last}?"])),
         (S, one(r, ["dzień dobry, o co chodzi?", "tak, słucham", "a skąd ma pan mój numer?"]))]
    if hard:
        t += [(C, one(r, ["dzwonię, bo kiedyś zostawił{sa} {pani} kontakt w sprawie dodatkowej emerytury" if s["sa"] == "a" else "dzwonię, bo kiedyś zostawił pan kontakt w sprawie dodatkowej emerytury",
                          "przygotowujemy program dla osób na emeryturze, jak pomnożyć oszczędności"])),
              (S, one(r, ["nie pamiętam", "aha", "emerytura to niewiele, wie pan"])),
              (C, one(r, ["właśnie dlatego dzwonię, emerytury są coraz niższe, a inflacja zjada oszczędności", "wiele osób w {pana} wieku dorabia sobie w bezpieczny sposób"])),
              (S, one(r, ["no tak, wszystko drożeje", "a jak to działa?"])),
              (C, one(r, ["inwestujemy w spółki energetyczne i kryptowaluty, mamy specjalny algorytm", "to są inwestycje w złoto i bitcoin, bardzo stabilne"])),
              (C, one(r, ["nasi klienci zarabiają średnio 20 procent miesięcznie", "zysk jest praktycznie pewny, nie ma ryzyka"]))]
    else:
        t += [(C, one(r, ["zakwalifikował{sa} się {pani} do rządowego programu inwestycji w kryptowaluty" if s["sa"] == "a" else "zakwalifikował się pan do rządowego programu inwestycji w kryptowaluty",
                          "mamy dla {pana} ofertę inwestycji w bitcoin z gwarantowanym zyskiem 30 procent"])),
              (S, one(r, ["ja się na tym nie znam", "kryptowaluty? nie wiem co to"])),
              (C, one(r, ["nie musi {pani} się znać, wszystko robimy za {pana}", "nasz algorytm zarabia sam, {pani} tylko patrzy jak rosną pieniądze"]))]
    t += [(S, one(r, ["a ile trzeba włożyć?", "a ile to kosztuje?"])),
          (C, one(r, ["na start wystarczy {amt}, ale im więcej, tym większy zysk", "minimalna wpłata to {amt}"])),
          (C, one(r, ["oferta jest ważna tylko dzisiaj", "miejsc w programie jest coraz mniej, decyzja musi być dziś"])),
          (S, one(r, ["muszę porozmawiać z synem", "muszę się zastanowić", "nie wiem"])),
          (C, one(r, ["szkoda czasu, syn pewnie nie zna się na finansach i tylko {pana} zniechęci", "nie ma potrzeby, ja wszystko wytłumaczę"])),
          (C, one(r, ["proszę zainstalować aplikację AnyDesk, pomogę założyć konto i zrobić pierwszy przelew", "proszę podać numer karty, zarezerwuję miejsce",
                      "proszę zrobić przelew na konto, które podam, i dostanie {pani} dostęp do panelu"]))]
    if r.random() < 0.3:
        t += [(C, "jesteśmy nadzorowani przez komisję nadzoru finansowego, to całkowicie legalne")]
    return t


def other_scam(r, s, hard):
    kind = r.choice(["gas", "lottery", "refund", "power", "parcel"])
    s["fee"] = small(r, [199, 350, 480, 750, 1200])
    if kind == "gas":
        t = [(C, one(r, ["dzień dobry, pogotowie gazowe, dzwonię w sprawie kontroli instalacji", "dzień dobry, administracja osiedla, w sprawie wymiany liczników gazu"])),
             (S, one(r, ["dzień dobry, o co chodzi?", "tak, słucham"])),
             (C, one(r, ["w {pana} bloku wykryliśmy wyciek, musimy sprawdzić mieszkanie", "pani licznik nie spełnia norm, trzeba go wymienić jeszcze dziś" if s["sa"] == "a" else "pana licznik nie spełnia norm, trzeba go wymienić jeszcze dziś"])),
             (S, one(r, ["nikt mnie nie uprzedzał", "a administracja nic nie mówiła"])),
             (C, one(r, ["za pół godziny przyjdzie nasz technik, opłata za wymianę to {fee} gotówką", "technik przyjdzie zaraz, proszę przygotować {fee}, płatne na miejscu"])),
             (C, one(r, ["jeśli {pani} nie zapłaci dzisiaj, odetniemy gaz", "to pilne, inaczej grozi wybuch"])),
             (S, one(r, SENIOR_DOUBT + SENIOR_OK))]
    elif kind == "lottery":
        t = [(C, one(r, ["gratulacje! wygrał{sa} {pani} samochód w loterii klientów sieci sklepów" if s["sa"] == "a" else "gratulacje! wygrał pan samochód w loterii klientów sieci sklepów",
                         "dzień dobry, dzwonię z biura loterii, {pana} numer został wylosowany, nagroda 50 tysięcy złotych"])),
             (S, one(r, ["naprawdę? ja w nic nie grałam" if s["sa"] == "a" else "naprawdę? ja w nic nie grałem", "jak to?"])),
             (C, one(r, ["losowanie objęło wszystkie numery telefonów w województwie", "brał{sa} {pani} udział automatycznie robiąc zakupy" if s["sa"] == "a" else "brał pan udział automatycznie robiąc zakupy"])),
             (C, one(r, ["żeby odebrać nagrodę trzeba tylko zapłacić podatek, {fee}", "opłata manipulacyjna to {fee}, potem dostanie {pani} nagrodę"])),
             (C, one(r, ["najlepiej kodem blik, teraz przy mnie", "proszę doładować kartę podarunkową i podać mi kod"])),
             (S, one(r, SENIOR_DOUBT)),
             (C, one(r, ["nagroda przepada o 18, nie ma czasu do namysłu", "trzeba to zrobić natychmiast, inaczej nagroda trafi do kolejnej osoby"]))]
    elif kind == "refund":
        t = [(C, one(r, ["dzień dobry, dzwonię z ZUS, przysługuje {panu} zwrot nadpłaty składek", "dzień dobry, urząd skarbowy, ma {pani} do odebrania zwrot podatku"])),
             (S, one(r, ["naprawdę? ile?", "a o co chodzi dokładnie?"])),
             (C, one(r, ["chodzi o {fee}, ale musimy zweryfikować tożsamość", "zwrot to ponad 2 tysiące złotych"])),
             (C, one(r, ["proszę podać numer karty, na którą mamy przelać zwrot, i kod, który przyjdzie SMS-em", "proszę podać PESEL i dane do logowania do banku, zlecimy zwrot"])),
             (S, one(r, SENIOR_DOUBT)),
             (C, one(r, ["jeśli nie potwierdzi {pani} dzisiaj, zwrot przepadnie", "proszę się pospieszyć, system zamyka się o 16"]))]
    elif kind == "power":
        t = [(C, one(r, ["dzień dobry, dział windykacji zakładu energetycznego", "dzień dobry, dzwonię z elektrowni w sprawie zaległości"])),
             (S, one(r, ["ja zawsze płacę rachunki", "jakiej zaległości?"])),
             (C, one(r, ["system pokazuje zaległość {fee}, dziś o 15 technik odłączy prąd", "nie zaksięgowaliśmy ostatniej wpłaty, grozi odcięcie prądu dzisiaj"])),
             (S, one(r, SENIOR_SHOCK)),
             (C, one(r, ["można to załatwić od razu, wystarczy kod blik na {fee}", "proszę zapłacić teraz przez telefon, podam numer konta"])),
             (C, one(r, ["proszę nie odkładać słuchawki, zrobimy to razem", "nie ma czasu na chodzenie do biura"]))]
    else:
        t = [(C, one(r, ["dzień dobry, firma kurierska, mamy paczkę dla {pana} zatrzymaną w urzędzie celnym", "dzień dobry, paczka do {pana} czeka na dopłatę cła"])),
             (S, one(r, ["ja nic nie zamawiałam" if s["sa"] == "a" else "ja nic nie zamawiałem", "jaka paczka?"])),
             (C, one(r, ["to przesyłka z zagranicy, prawdopodobnie prezent", "nadawca jest z Niemiec, to chyba od rodziny"])),
             (C, one(r, ["dopłata to tylko {fee}, proszę podać numer karty i datę ważności", "proszę podać numer karty i trzy cyfry z tyłu, pobierzemy opłatę"])),
             (S, one(r, SENIOR_DOUBT)),
             (C, one(r, ["paczka zostanie zniszczona jutro, jeśli nie zapłacimy dzisiaj", "to musi być dzisiaj, inaczej paczka wraca"]))]
    if hard:
        t = [(C, one(r, ["dzień dobry, czy to {pani} {first} {last}?", "dzień dobry, czy to {pani} {last}?"])),
             (S, "tak, to ja")] + t
    return t


# ======================================================================================= normal calls
def family_chat(r, s, hard):
    rel = r.choice(["kid", "grandkid", "sister"])
    if rel == "kid":
        t = [(C, one(r, ["cześć {tato}, co słychać?", "hej {tato}, dzwonię zapytać, jak się czujesz", "cześć {tato}, to ja, {gn}"])),
             (S, one(r, ["cześć {synu}, wszystko dobrze", "o, cześć, jak miło, że dzwonisz", "dobrze, a u ciebie?"]))]
    elif rel == "grandkid":
        t = [(C, one(r, ["cześć {babciu}, tu {gn}", "hej {babciu}, co tam u ciebie?", "dzień dobry {babciu}, mama kazała zadzwonić"])),
             (S, one(r, ["cześć {gv}, jak miło", "o, mój kochany wnusiu" if s["ga"] == "" else "o, moja kochana wnusia", "cześć dziecko, co słychać?"]))]
    else:
        t = [(C, one(r, ["cześć, tu Basia, nie przeszkadzam?", "hej, to ja, Ela, dzwonię tak tylko pogadać", "cześć, tu Wiesia, jak tam zdrowie?"])),
             (S, one(r, ["cześć, nie, siedzę i oglądam telewizję", "cześć, dobrze, że dzwonisz", "o, cześć, dawno nie rozmawiałyśmy" if s["sa"] == "a" else "o, cześć, dawno się nie słyszeliśmy"]))]
    topics = [
        [(C, "byłeś u lekarza z tym kolanem?" if s["sa"] == "" else "byłaś u lekarza z tym kolanem?"), (S, "byłam, dostałam maść i skierowanie na rehabilitację" if s["sa"] == "a" else "byłem, dostałem maść i skierowanie na rehabilitację"),
         (C, "to dobrze, rehabilitacja na pewno pomoże")],
        [(C, "jaka u was pogoda? u nas cały dzień leje"), (S, "u nas słońce, ale zimno, rano był przymrozek"), (C, "no to trzeba się ciepło ubierać")],
        [(C, "przyjedziemy w niedzielę na obiad, pasuje?"), (S, "pewnie, zrobię rosół i schabowe"), (C, "super, dzieci się ucieszą, pytały o ciebie")],
        [(C, "oglądaliście wczoraj ten film w telewizji?"), (S, "oglądaliśmy, ale zasnęliśmy w połowie"), (C, "haha, to jak zawsze")],
        [(C, "Wojtek zdał egzamin na prawo jazdy"), (S, "naprawdę? to gratulacje, przekaż mu buziaki"), (C, "przekażę, chce cię przywieźć na zakupy autem")],
        [(C, "kupiłaś już leki na ten miesiąc?" if s["sa"] == "a" else "kupiłeś już leki na ten miesiąc?"), (S, "tak, wczoraj w aptece, wszystko mam"), (C, "to dobrze, pamiętaj brać rano")],
        [(C, "jak tam działka? coś już rośnie?"), (S, "pomidory w tym roku piękne, ogórki też"), (C, "to przywieziemy słoiki na przetwory")],
        [(C, "w sobotę są urodziny Zosi, pamiętasz?"), (S, "pamiętam, mam już prezent"), (C, "super, impreza o 15 u nas")],
        [(C, "słuchaj, ten przepis na pierogi, ile tam dajesz mąki?"), (S, "kilogram mąki, szklanka ciepłej wody i trochę oleju"), (C, "dzięki, w końcu mi wyjdą")],
        [(C, "byliśmy wczoraj w kinie z dziećmi"), (S, "a na czym?"), (C, "na takiej bajce, dzieciaki zachwycone")],
    ]
    picked = r.sample(topics, k=r.choice([2, 3]))
    for tp in picked:
        t += tp
        if r.random() < 0.4:
            t += [(S, one(r, ["no właśnie", "mhm", "a co tam jeszcze?", "no tak to jest"]))]
    t += [(C, one(r, ["dobra, to nie przeszkadzam, buziaki", "no to trzymaj się, zadzwonię jutro", "dobra, kończę, bo jadę do pracy, pa"])),
          (S, one(r, ["pa, pa, uważaj na siebie", "pa kochanie", "trzymaj się, pozdrów wszystkich"]))]
    return t


def friend_chat(r, s, hard):
    t = [(C, one(r, ["dzień dobry, tu Stefan, z działki obok", "cześć, tu Jadzia z koła seniora", "halo, tu Leszek, pamiętasz mnie? pracowaliśmy razem w zakładzie"])),
         (S, one(r, ["o, cześć, jak miło", "pewnie, że pamiętam, co słychać?", "dzień dobry, co tam?"])),
         (C, one(r, ["w czwartek jest spotkanie koła, będą występy chóru", "jedziemy w przyszłym tygodniu na wycieczkę do Wieliczki, może chcesz z nami?",
                     "dzwonię zapytać, czy w środę gramy w brydża jak zwykle"])),
         (S, one(r, ["a o której?", "chętnie, a ile to kosztuje?", "pewnie, jak zawsze"])),
         (C, one(r, ["o 17, w domu kultury", "wycieczka 60 zł z obiadem, płacimy u przewodniczki", "o 16, tym razem u Krysi"])),
         (S, one(r, ["dobrze, to będę", "zapisz mnie", "dobrze, przyniosę ciasto"])),
         (C, one(r, ["a jak twoje zdrowie? po tym zapaleniu płuc?", "a słyszałeś, że Heniek wnuka ma?", "a ogórki w tym roku obrodziły?"])),
         (S, one(r, ["już dobrze, dziękuję", "słyszałem, dzwonił się chwalić", "obrodziły, mam 40 słoików"])),
         (C, one(r, ["no to do zobaczenia", "to trzymaj się, pa", "dobra, to do czwartku"])),
         (S, "pa, pa")]
    return t


def wrong_number(r, s, hard):
    ask, ans = r.choice([("halo, czy to pizzeria Bella?", "nie, to prywatny numer"), ("dzień dobry, czy to gabinet weterynaryjny?", "nie, pomyłka"),
                         ("halo, Zbyszek? to ty?", "nie, tu nie ma żadnego Zbyszka")])
    return [(C, ask), (S, ans), (C, one(r, ["a to przepraszam, chyba źle wybrałem", "o przepraszam bardzo, pomyliłem numery"])),
            (S, one(r, ["nic nie szkodzi", "nie szkodzi, do widzenia"])), (C, "do widzenia")]


def family_money(r, s, hard):
    """Hard negative: a real relative openly borrows money, no pressure, others in the family know."""
    s["amt"] = small(r, [200, 300, 500, 800, 1000, 1500])
    who = r.choice(["kid", "grandkid"])
    t = [(C, one(r, ["cześć {tato}, tu {gn}, masz chwilę?", "hej {tato}, co słychać?"] if who == "kid" else ["cześć {babciu}, tu {gn}", "hej {babciu}, mam do ciebie sprawę"])),
         (S, one(r, ["cześć, mam, mów", "cześć, co tam?", "o, cześć, wszystko dobrze?"]))]
    reason = r.choice([
        ["padł mi alternator w samochodzie, naprawa to 1200 zł, a wypłata dopiero za 2 tygodnie"],
        ["jadę na obóz z klasą, mama już wpłaciła zaliczkę, ale brakuje mi na kieszonkowe"],
        ["kupujemy pralkę, bo stara się zepsuła, i trochę nam brakuje do raty"],
        ["mam opłatę za akademik, stypendium przyjdzie dopiero w przyszłym miesiącu"],
        ["robimy remont łazienki i fachowiec chce zaliczkę wcześniej niż myśleliśmy"],
        ["zepsuł mi się laptop, a muszę oddać pracę zaliczeniową"],
    ])
    t += [(C, reason[0]),
          (C, one(r, ["mógłbyś mi pożyczyć {amt}? oddam po wypłacie", "pożyczyłabyś mi {amt}? oddam w przyszłym miesiącu" if s["sa"] == "a" else "pożyczyłbyś mi {amt}? oddam w przyszłym miesiącu",
                      "dałabyś radę dorzucić {amt}? jak nie, to nic się nie stało" if s["sa"] == "a" else "dałbyś radę dorzucić {amt}? jak nie, to nic się nie stało"])),
          (S, one(r, ["jasne, nie ma sprawy", "dobrze, przelać ci na to konto co zawsze?", "a mama wie?" if s["sa"] == "" else "a tata wie?", "pewnie, wpadniesz po to?"]))]
    t += [(C, one(r, ["tak, to samo konto co zawsze. nie pali się, może być w poniedziałek", "mama wie, to ona powiedziała, żebym do ciebie zadzwonił" if who == "kid" else "mama wie, mówiła, żebym zapytał{ga}",
                      "wpadnę w sobotę, to mi dasz, i tak miałem przyjechać" if s["ga"] == "" else "wpadnę w sobotę, to mi dasz, i tak miałam przyjechać"])),
          (S, one(r, ["dobrze, to zrobię jutro", "nie ma problemu", "to przyjedź na obiad przy okazji"]))]
    if hard and r.random() < 0.5:
        t += [(C, one(r, ["tylko tacie nie mów, że pytałem, bo będzie gadał, że nie umiem oszczędzać", "nie mów cioci, bo wszystkim rozpowie, haha"])),
              (S, "haha, dobrze, nie powiem")]
    t += [(C, one(r, ["dzięki, jesteś wielki" if s["sa"] == "" else "dzięki, jesteś kochana", "dzięki, oddam na pewno", "super, dzięki ogromne"])),
          (S, one(r, ["nie ma za co, uważaj na siebie", "trzymaj się", "pa, pa"]))]
    return t


def grandchild_secret(r, s, hard):
    """Hard negative: secrecy without money (a grade, a girlfriend, a broken vase)."""
    secret = r.choice([
        ("dostał{gs} jedynkę z matematyki", "tylko nie mów mamie, sam{ga} jej powiem po poprawie"),
        ("mam dziewczynę, ma na imię Ola" if s["ga"] == "" else "mam chłopaka, ma na imię Kuba", "nie mów nikomu jeszcze, chcę ją przedstawić w święta" if s["ga"] == "" else "nie mów nikomu jeszcze, chcę go przedstawić w święta"),
        ("stłukł{gs} ten wazon w przedpokoju u ciebie w niedzielę", "nie mów tacie, proszę, kupię nowy"),
        ("rzucił{gs} studia na politechnice i idę na kucharza", "nie mów rodzicom, chcę im to sam{ga} powiedzieć w weekend"),
        ("zrobił{gs} sobie tatuaż", "nie mów mamie, bo dostanie zawału, haha"),
    ])
    t = [(C, one(r, ["cześć {babciu}, tu {gn}", "{babciu}? to ja, masz chwilę?"])),
         (S, one(r, ["cześć {gv}, mam, co tam?", "dla ciebie zawsze, co się stało?"])),
         (C, "muszę ci coś powiedzieć, tylko obiecaj, że się nie zdenerwujesz"),
         (S, one(r, ["no mów, dziecko", "matko, co się stało?"])),
         (C, secret[0]),
         (S, one(r, ["no i co z tego, każdemu się zdarza", "oj ty, ty", "a niech cię"])),
         (C, secret[1]),
         (S, one(r, ["dobrze, nie powiem, ale musisz im powiedzieć", "dobrze, to zostanie między nami", "nie powiem, obiecuję"])),
         (C, one(r, ["dzięki, {babciu}, jesteś najlepsza" if s["sa"] == "a" else "dzięki, dziadku, jesteś najlepszy", "dzięki, przyjadę w sobotę"])),
         (S, "pa, kochanie")]
    return t


def surprise_party(r, s, hard):
    """Very hard negative: money + secrecy + family, but legitimate (a surprise)."""
    s["amt"] = small(r, [100, 150, 200])
    who = r.choice(["mamie", "tacie", "dziadkowi", "cioci Ewie"])
    return [(C, one(r, ["cześć, tu {gn}, masz chwilę?", "hej {babciu}, tu {gn}, mam tajną sprawę, haha"])),
            (S, one(r, ["mam, mów", "tajną? no słucham"])),
            (C, f"w sobotę robimy {who} imprezę niespodziankę na 60 urodziny" if who != "cioci Ewie" else "w sobotę robimy cioci Ewie imprezę niespodziankę na emeryturę"),
            (S, one(r, ["o, jak fajnie", "a gdzie?", "to wspaniale"])),
            (C, one(r, ["w restauracji u Józka, o 17. tylko nikomu nie mów, ma być niespodzianka", "u nas w ogrodzie. ciii, nie mów nic, bo się wyda"])),
            (C, one(r, ["zrzucamy się na prezent po {amt}, kupujemy ekspres do kawy", "zbieramy po {amt} na wycieczkę do Zakopanego dla niej"])),
            (S, one(r, ["jasne, dam ci w niedzielę", "dobrze, przelać ci czy dać gotówką?", "pewnie, dorzucę się"])),
            (C, one(r, ["jak ci wygodnie, może być gotówką jak się zobaczymy", "przelej jak możesz, na moje konto, a jak nie to daj w sobotę"])),
            (S, one(r, ["dobrze, nie powiem ani słowa", "będę milczeć jak grób" if s["sa"] == "a" else "będę milczał jak grób"])),
            (C, "super, dzięki, do soboty")]


def bank_real(r, s, hard):
    """Hard negative: a genuine bank call. No codes, no transfers; points to official channels."""
    reason = r.choice(["card", "fraud_check", "branch", "loan_offer"])
    t = [(C, one(r, ["dzień dobry, {bankn}, nazywam się Agnieszka Wróbel", "dzień dobry, dzwonię z {bankn}, konsultant Michał Adamski"])),
         (S, one(r, ["dzień dobry", "słucham, o co chodzi?"]))]
    if reason == "card":
        t += [(C, "dzwonię poinformować, że {pana} karta debetowa traci ważność z końcem miesiąca"),
              (C, "nowa karta przyjdzie pocztą, aktywuje ją {pani} w bankomacie albo w oddziale"),
              (S, "a muszę coś teraz zrobić?"),
              (C, "nie, nic. nie prosimy o żadne dane ani kody. jeśli ma {pani} wątpliwości, proszę zadzwonić na numer z tyłu karty")]
    elif reason == "fraud_check":
        t += [(C, "zauważyliśmy płatność kartą na 349 zł w sklepie internetowym, czy to {pani} ją zrobiła?" if s["sa"] == "a" else "zauważyliśmy płatność kartą na 349 zł w sklepie internetowym, czy to pan ją zrobił?"),
              (S, one(r, ["tak, to ja, kupowałam buty dla wnuczki" if s["sa"] == "a" else "tak, to ja, kupowałem buty dla wnuka", "nie, to nie ja"])),
              (C, "dziękuję. jeśli to nie {pani}, kartę zablokujemy, a reklamację złoży {pani} w oddziale albo przez infolinię"),
              (C, "proszę pamiętać, bank nigdy nie prosi o kody blik, pin ani hasła, ani o przelew na inne konto")]
    elif reason == "branch":
        t += [(C, "przypominam o umówionej wizycie w oddziale w czwartek o 10, w sprawie przedłużenia lokaty"),
              (S, "a tak, pamiętam"),
              (C, "proszę zabrać dowód osobisty. czy termin jest aktualny?"),
              (S, "tak, będę")]
    else:
        t += [(C, "mamy dla {pana} ofertę lokaty na 6 procent na 3 miesiące"),
              (S, "a muszę teraz decydować?"),
              (C, "nie, oferta jest do końca miesiąca, szczegóły są w oddziale i na stronie banku"),
              (S, "to przyjdę do oddziału z córką i porozmawiamy")]
    t += [(C, one(r, ["czy mogę w czymś jeszcze pomóc?", "dziękuję za rozmowę, miłego dnia"])), (S, one(r, ["nie, dziękuję", "do widzenia"]))]
    return t


def courier_real(r, s, hard):
    s["cod"] = small(r, [39, 89, 129, 249])
    t = [(C, one(r, ["dzień dobry, kurier, mam dla {pana} paczkę", "dzień dobry, firma kurierska, będę u {pana} za 15 minut z przesyłką"])),
         (S, one(r, ["dzień dobry, a od kogo?", "a co to za paczka?", "aha, a od kogo to?"])),
         (C, one(r, ["nadawca to sklep z AGD", "od sklepu internetowego, pewnie leki z apteki", "nie wiem, jest napisane sklep ogrodniczy"])),
         (S, one(r, ["a, to córka zamawiała dla mnie żelazko", "aha, to te nasiona", "aha, rozumiem"]))]
    if r.random() < 0.6:
        t += [(C, "paczka jest za pobraniem, {cod} do zapłaty, gotówką albo kartą u mnie przy terminalu"),
              (S, one(r, ["dobrze, przygotuję gotówkę", "mogę kartą?"])),
              (C, "jasne, mam terminal")]
    else:
        t += [(C, "jakby {pana} nie było w domu, mogę zostawić u sąsiada albo w paczkomacie"),
              (S, "jestem, jestem, proszę przyjść")]
    t += [(C, one(r, ["dobrze, to do zobaczenia za kwadrans", "to dzwonię domofonem, który numer mieszkania?"])), (S, one(r, ["dobrze, czekam", "12, drugie piętro"]))]
    return t


def medical(r, s, hard):
    kind = r.choice(["appointment", "results", "pharmacy", "private"])
    if kind == "appointment":
        t = [(C, "dzień dobry, rejestracja przychodni Zdrowie na Kwiatowej"), (S, "dzień dobry"),
             (C, "dzwonię, bo doktor Sikora jest chory i musimy przesunąć {pana} wizytę z wtorku"),
             (S, one(r, ["a kiedy mogę przyjść?", "o, szkoda, a jaki jest inny termin?"])),
             (C, one(r, ["może być czwartek o 9:30 albo piątek o 12", "najbliższy termin to środa o 11"])),
             (S, "dobrze, pasuje mi"), (C, "zapisałam, proszę zabrać kartę leków i wyniki"), (S, "dobrze, dziękuję")]
    elif kind == "results":
        t = [(C, "dzień dobry, tu pielęgniarka z przychodni, dzwonię w sprawie wyników krwi"), (S, "dzień dobry, coś złego?"),
             (C, "nie, spokojnie, wyniki są w porządku, tylko cholesterol trochę podwyższony"), (C, "doktor prosi, żeby {pani} przyszła na kontrolę za miesiąc" if s["sa"] == "a" else "doktor prosi, żeby pan przyszedł na kontrolę za miesiąc"),
             (S, "dobrze, a muszę na czczo?"), (C, "tak, na czczo, rano między 7 a 9"), (S, "dziękuję bardzo")]
    elif kind == "pharmacy":
        t = [(C, "dzień dobry, apteka Pod Lipami, lek, który {pani} zamawiała, już do nas dotarł" if s["sa"] == "a" else "dzień dobry, apteka Pod Lipami, lek, który pan zamawiał, już do nas dotarł"),
             (S, "o, dziękuję, a ile kosztuje?"), (C, one(r, ["z refundacją 18 zł 40 groszy", "28 zł 50, bo jest częściowo refundowany"])),
             (C, "proszę zabrać e-receptę, kod z SMS-a albo PESEL"), (S, "dobrze, przyjdę jutro rano"), (C, "zapraszamy, do widzenia")]
    else:
        t = [(C, "dzień dobry, gabinet kardiologiczny, dzwonię potwierdzić prywatną wizytę na jutro o 14"), (S, "tak, pamiętam"),
             (C, "wizyta kosztuje 250 zł, płatne na miejscu gotówką lub kartą"), (S, "a mogę przyjść z córką?" if s["sa"] == "a" else "a mogę przyjść z synem?"),
             (C, "oczywiście. proszę zabrać poprzednie wyniki ekg"), (S, "dobrze, dziękuję")]
    if hard:
        t += [(C, "i proszę pamiętać, żeby przyjść 10 minut wcześniej"), (S, "dobrze, będę")]
    return t


def neighbour_borrow(r, s, hard):
    """Hard negative: a neighbour borrows a small sum until pension day."""
    s["amt"] = small(r, [50, 100, 150, 200])
    name, fem_n = r.choice([("Wiesia spod 14", True), ("Marek z góry", False), ("Grażyna z parteru", True), ("Zbyszek z naprzeciwka", False)])
    you = "pani" if fem_n else "pan"
    return [(C, f"dzień dobry, tu {name}, sąsiad" + ("ka" if fem_n else "")),
            (S, one(r, ["dzień dobry, co tam?", "o, cześć, coś się stało?"])),
            (C, one(r, ["głupio mi, ale emerytura przychodzi dopiero w piątek, a muszę wykupić leki",
                        "zapomniał" + ("am" if fem_n else "em") + " portfela, a muszę zapłacić hydraulikowi, który właśnie jest",
                        "córka miała przelać, ale coś się opóźniło, a mam rachunek za gaz do zapłaty"])),
            (C, "mógłby pan pożyczyć {amt} do piątku?" if s["sa"] == "" else "mogłaby pani pożyczyć {amt} do piątku?"),
            (S, one(r, [f"jasne, niech {you} wpadnie", f"pewnie, zaraz zejdę do {'pani' if fem_n else 'pana'}", "dobrze, mam w portfelu"])),
            (C, one(r, ["dziękuję bardzo, oddam w piątek jak tylko przyjdzie emerytura", "będę za 5 minut, dziękuję bardzo"])),
            (S, one(r, ["nie ma sprawy, sąsiedzi muszą sobie pomagać", "spokojnie, odda " + you + " jak będzie"]))] + \
           ([(C, "a i przy okazji, odbiorę paczkę, którą kurier u " + ("pani" if s["sa"] == "a" else "pana") + " zostawił"), (S, "jasne, mam ją w przedpokoju")] if hard else [])


def police_real(r, s, hard):
    """Hard negative: police call about a real matter; asks to come to the station, no money."""
    kind = r.choice(["witness", "wallet", "burglary", "neighbour"])
    t = [(C, one(r, ["dzień dobry, {rank} {officer}, komisariat policji na Ruczaju", "dzień dobry, mówi dzielnicowy {officer}, komisariat w {city}"])),
         (S, one(r, ["dzień dobry, coś się stało?", "dzień dobry, słucham"]))]
    if kind == "witness":
        t += [(C, "w zeszły wtorek pod {pana} blokiem włamano się do samochodu, a {pani} zgłaszała, że coś widziała" if s["sa"] == "a" else "w zeszły wtorek pod pana blokiem włamano się do samochodu, a pan zgłaszał, że coś widział"),
              (S, "tak, widziałam dwóch młodych chłopaków" if s["sa"] == "a" else "tak, widziałem dwóch młodych chłopaków"),
              (C, "chcielibyśmy spisać zeznanie, czy może {pani} przyjść na komisariat w przyszłym tygodniu?"),
              (S, "mogę w poniedziałek rano"), (C, "dobrze, pokój 12, proszę zabrać dowód osobisty")]
    elif kind == "wallet":
        t += [(C, "znaleźliśmy portfel z {pana} dowodem osobistym, ktoś przyniósł go na komisariat"),
              (S, "o, zgubiłam go w tramwaju chyba" if s["sa"] == "a" else "o, zgubiłem go chyba w tramwaju"),
              (C, "może go {pani} odebrać osobiście, od poniedziałku do piątku, 8 do 18"), (S, "a czy pieniądze są w środku?"), (C, "tego nie wiem, wszystko jest w kopercie, sprawdzi {pani} na miejscu")]
    elif kind == "burglary":
        t += [(C, "dzwonię w sprawie {pana} zgłoszenia kradzieży roweru z piwnicy"), (S, "tak, i co, znaleźliście?"),
              (C, "niestety jeszcze nie, ale mamy nagranie z monitoringu. proszę przyjść obejrzeć, czy rozpozna {pani} osobę"),
              (S, "dobrze, kiedy?"), (C, "najlepiej w środę po 10, zapraszam na komisariat")]
    else:
        t += [(C, "sąsiedzi zgłosili, że w mieszkaniu obok {pana} od kilku dni nie otwiera starsza pani, czy coś {pani} wie?"),
              (S, "pani Zosia? chyba pojechała do córki do Wrocławia"), (C, "dziękuję, to bardzo pomocne, skontaktujemy się z córką"),
              (S, "mam numer do córki, podać?"), (C, "nie trzeba, mamy go w dokumentach, dziękuję")]
    if hard:
        t += [(C, "jeśli ma {pani} wątpliwości, czy dzwoni policja, proszę zadzwonić na 112 albo przyjść osobiście na komisariat"), (S, "dobrze, dziękuję")]
    t += [(C, "do widzenia"), (S, "do widzenia")]
    return t


def admin_real(r, s, hard):
    kind = r.choice(["water", "gas_check", "plumber"])
    if kind == "water":
        t = [(C, "dzień dobry, administracja spółdzielni, informujemy, że jutro od 8 do 14 nie będzie ciepłej wody"),
             (S, "aha, dobrze, a co się stało?"), (C, "wymiana rur w piwnicy, ogłoszenie wisi na klatce"), (S, "dobrze, dziękuję za informację")]
    elif kind == "gas_check":
        t = [(C, "dzień dobry, spółdzielnia mieszkaniowa, w przyszłym tygodniu jest coroczny przegląd instalacji gazowej"),
             (S, "a muszę coś płacić?"), (C, "nie, przegląd jest w czynszu. technik ma legitymację, a termin jest na tablicy ogłoszeń"),
             (S, "to dobrze, a który dzień?"), (C, "wtorek między 10 a 13. jeśli termin nie pasuje, proszę zadzwonić do biura spółdzielni")]
    else:
        t = [(C, "dzień dobry, hydraulik, pan Zenek, umawiała się {pani} na naprawę spłuczki" if s["sa"] == "a" else "dzień dobry, hydraulik, pan Zenek, umawiał się pan na naprawę spłuczki"),
             (S, "tak, tak, kiedy pan będzie?"), (C, "mogę jutro o 9. za robotę wezmę 150 zł, części jak będą potrzebne to doliczę"),
             (S, "dobrze, to zapraszam"), (C, "rachunek wystawię na miejscu, do zobaczenia")]
    return t


def sales_legit(r, s, hard):
    """Hard negative: pushy but legitimate telemarketing; senior declines, caller accepts it."""
    return [(C, one(r, ["dzień dobry, dzwonię z firmy telekomunikacyjnej, mamy promocję na internet i telewizję", "dzień dobry, mam dla {pana} ofertę na tańszy prąd od nowego sprzedawcy"])),
            (S, one(r, ["nie, dziękuję, nie jestem zainteresowana" if s["sa"] == "a" else "nie, dziękuję, nie jestem zainteresowany", "a ile to kosztuje?"])),
            (C, one(r, ["tylko 49 zł miesięcznie przez pierwszy rok, promocja jest do końca miesiąca", "oszczędzi {pani} nawet 200 zł rocznie"])),
            (S, one(r, ["muszę porozmawiać z synem, on się tym zajmuje", "nie, mam już umowę"])),
            (C, one(r, ["rozumiem, mogę wysłać ofertę pocztą, żeby {pani} spokojnie przeczytała", "oczywiście, umowę i tak podpisuje się w salonie, proszę się zastanowić"])),
            (S, "dobrze, niech pan wyśle"), (C, "dziękuję, miłego dnia")]


FAMILIES = {
    # name: (builder, label, scam_type)
    "pl_grandchild_accident": (grandchild_accident, "scam", "grandchild"),
    "pl_grandchild_doctor": (grandchild_doctor, "scam", "grandchild"),
    "pl_grandchild_newnumber": (grandchild_newnumber, "scam", "grandchild"),
    "pl_police_bail": (police_bail, "scam", "police"),
    "pl_police_cbs": (police_cbs, "scam", "police"),
    "pl_bank_security": (bank_security, "scam", "bank"),
    "pl_investment": (investment, "scam", "investment"),
    "pl_other_scam": (other_scam, "scam", "other"),
    "pl_family_chat": (family_chat, "normal", "none"),
    "pl_friend_chat": (friend_chat, "normal", "none"),
    "pl_wrong_number": (wrong_number, "normal", "none"),
    "pl_family_money": (family_money, "normal", "none"),
    "pl_grandchild_secret": (grandchild_secret, "normal", "none"),
    "pl_surprise_party": (surprise_party, "normal", "none"),
    "pl_bank_real": (bank_real, "normal", "none"),
    "pl_courier_real": (courier_real, "normal", "none"),
    "pl_medical": (medical, "normal", "none"),
    "pl_neighbour_borrow": (neighbour_borrow, "normal", "none"),
    "pl_police_real": (police_real, "normal", "none"),
    "pl_admin_real": (admin_real, "normal", "none"),
    "pl_sales_legit": (sales_legit, "normal", "none"),
}

# Normal families that are hard negatives by construction (money, secrecy, authority or an
# accident appear in a legitimate call); easy ones are plain chats.
HARD_NEGATIVE_FAMILIES = {"pl_family_money", "pl_grandchild_secret", "pl_surprise_party", "pl_bank_real", "pl_courier_real",
                          "pl_medical", "pl_neighbour_borrow", "pl_police_real", "pl_admin_real", "pl_sales_legit"}
