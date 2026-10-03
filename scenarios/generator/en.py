"""English call families (US/UK mix). Same structure as pl.py. Names are generic placeholders."""

from __future__ import annotations

import random

from common import C, S, one

F_SENIORS = [("Margaret", "Miller"), ("Dorothy", "Taylor"), ("Helen", "Clark"), ("Betty", "Walker"), ("Joan", "Harris")]
M_SENIORS = [("Robert", "Miller"), ("Walter", "Taylor"), ("George", "Clark"), ("Frank", "Walker"), ("Harold", "Harris")]
M_KIDS = ["Jamie", "Tom", "Danny", "Michael", "Chris", "Ben", "Kevin"]
F_KIDS = ["Emily", "Sarah", "Katie", "Megan", "Lucy", "Rachel"]
BANKS = ["Northgate Bank", "Riverside Savings", "Harbor Federal", "Maple Trust Bank", "Lakeside Credit Union"]
TOWNS = ["Springfield", "Riverton", "Oakdale", "Fairview", "Milltown"]
OFFICERS = ["Officer Daniels", "Sergeant Brooks", "Detective Morgan", "Deputy Collins", "Officer Reyes"]


def slots(r: random.Random) -> dict:
    fem = r.random() < 0.6
    first, last = r.choice(F_SENIORS if fem else M_SENIORS)
    kid_m = r.random() < 0.6
    return {"first": first, "last": last, "title": "Mrs." if fem else "Mr.", "maam": "ma'am" if fem else "sir",
            "grandma": "grandma" if fem else "grandpa", "mom": "mom" if fem else "dad",
            "gn": r.choice(M_KIDS if kid_m else F_KIDS), "he": "he" if kid_m else "she", "him": "him" if kid_m else "her",
            "his": "his" if kid_m else "her", "grandson": "grandson" if kid_m else "granddaughter",
            "son": "son" if kid_m else "daughter", "bank": r.choice(BANKS), "town": r.choice(TOWNS), "officer": r.choice(OFFICERS),
            "phone": r.choice(["555 0100", "555 0199", "555 0142"])}


def usd(r, values):
    n = r.choice(values)
    return one(r, [f"${n:,}", f"{n:,} dollars", f"${n}", f"{n} dollars"])


SHOCK = ["oh my god", "oh no", "oh dear", "what happened?", "oh goodness, are you okay?"]
DOUBT = ["I don't know", "that sounds strange", "I need to think about it", "how do I know this is real?"]
OK = ["okay", "alright", "I see", "uh huh", "yes, go on"]


# =========================================================================================== scams
def grandchild(r, s, hard):
    s["amt"] = usd(r, [2500, 3000, 4500, 6000, 8000, 9500])
    t = []
    if hard:
        t += [(C, one(r, ["hi {grandma}, it's me", "hey {grandma}, guess who", "{grandma}? it's your favorite {grandson}"])),
              (S, one(r, ["{gn}? is that you?", "who is this? {gn}?", "you sound different, {gn}?"])),
              (C, one(r, ["yeah it's me, I have a bad cold, that's why I sound weird", "yeah, I'm calling from a friend's phone, mine died"])),
              (S, one(r, ["how are you, sweetheart? how's school?", "it's so nice to hear from you", "how's the new job?"])),
              (C, one(r, ["it's good, mostly, but I'm kind of in a situation", "honestly not great, that's why I'm calling"])),
              (S, "what's wrong?"),
              (C, one(r, ["I went to a wedding in Mexico with friends and there was a car accident, I wasn't driving but they took everybody in",
                          "I hit a parked car and the guy was really mad, and then the police came and found something in the car that wasn't mine",
                          "I got into a fender bender and the other driver says he's hurt, there's a lawyer involved now"])),
              (S, one(r, SHOCK)),
              (C, one(r, ["I'm okay, really. the lawyer says this can all go away today if we settle it", "they gave me a public defender, he's really nice, he says it can be fixed"])),
              (S, one(r, ["what do you need?", "do your parents know?"])),
              (C, one(r, ["I'm so embarrassed, I hate asking, but I need help with the fees", "I don't want mom and dad to find out, they'd never trust me again. could you help me out?"])),
              (C, one(r, ["it's {amt}, I'll pay you back, I promise", "the lawyer says {amt} covers everything"]))]
    else:
        t += [(C, one(r, ["{grandma}, it's me, {gn}, I'm in big trouble", "{grandma}, please help me, it's {gn}", "{grandma}? I've been arrested"])),
              (S, one(r, ["{gn}? what happened?", "oh my god, what's going on?"])),
              (C, one(r, ["I was in a car accident and the police arrested me, I need bail money", "I hit a woman with my car, she's in the hospital and I'm in jail",
                          "I got arrested, they found drugs in my friend's car, I need money for bail"])),
              (S, one(r, SHOCK)),
              (C, one(r, ["bail is {amt} and I have to pay it today", "I need {amt} right now or they'll keep me here over the weekend"]))]
    t += [(S, one(r, ["I don't have that much at home", "how am I supposed to do that?", "where do I send it?"])),
          (C, one(r, ["you can buy gift cards at the pharmacy and read me the numbers", "my lawyer's assistant will come to your house to pick up the cash",
                      "you can wire it through western union, I'll give you the name", "a courier will come by in an hour to collect it"])),
          (S, one(r, DOUBT + OK))]
    if not hard or r.random() < 0.6:
        t += [(C, one(r, ["please don't tell mom and dad, they'll kill me", "and please keep this between us, okay?", "don't tell anybody, promise me"]))]
    if r.random() < 0.6:
        t += [(C, one(r, ["please hurry, I don't have much time", "you have to do it right now, please", "the lawyer only has an hour"]))]
    return t


def police(r, s, hard):
    kind = r.choice(["warrant", "jury", "bail_officer"])
    s["amt"] = usd(r, [1500, 2800, 4000, 7500])
    t = [(C, one(r, ["this is {officer} with the {town} county sheriff's office", "good afternoon, {officer}, {town} police department"])),
         (C, one(r, ["am I speaking with {first} {last}?", "is this {title} {last}?"])),
         (S, one(r, ["yes, this is {first}", "yes, what's this about?"]))]
    if kind == "warrant":
        t += [(C, "there is a warrant out for your arrest for failing to respond to a federal summons"),
              (S, one(r, SHOCK + ["a warrant? I've never done anything wrong"]))]
    elif kind == "jury":
        t += [(C, "you missed jury duty last month and the judge has issued a bench warrant"),
              (S, "I never got any letter about jury duty")]
    else:
        t += [(C, "your {grandson} {gn} was arrested this morning after a traffic accident"), (S, one(r, SHOCK))]
    if hard:
        t += [(C, one(r, ["I understand this is upsetting, ma'am. this is a courtesy call so we can resolve it without officers coming to your home" if s["maam"] == "ma'am" else "I understand this is upsetting, sir. this is a courtesy call so we can resolve it without officers coming to your home",
                          "please stay calm, nobody is in danger. we just need to clear this up today"])),
              (S, one(r, ["what do I have to do?", "how can I fix this?"])),
              (C, one(r, ["you can call the station back to verify, but please stay on the line while I transfer you", "you're welcome to verify my badge number, it's 4471"]))]
    t += [(C, one(r, ["to avoid arrest you need to pay a fine of {amt} today", "the bond is {amt}, payable today"])),
          (C, one(r, ["the court accepts payment in gift cards or bitcoin at the kiosk", "an officer will come to collect the cash in person", "you can wire it to the court's holding account"])),
          (S, one(r, DOUBT + OK))]
    if r.random() < 0.7:
        t += [(C, one(r, ["do not discuss this with anyone, it's a confidential matter", "don't tell your family, it could compromise the case", "don't hang up, stay on the line"]))]
    t += [(C, one(r, ["you need to do this immediately", "if this isn't paid within the hour, deputies will be sent", "time is of the essence"]))]
    return t


def bank(r, s, hard):
    s["amt"] = usd(r, [980, 1499, 2350, 4200])
    t = [(C, one(r, ["hello, this is Karen from the fraud department at {bank}", "hi, I'm calling from {bank} security team, my name is Mark", "good morning, {bank}, account security"])),
         (S, one(r, ["hello", "yes?", "what's this about?"]))]
    if hard:
        t += [(C, "for security, can you confirm I'm speaking with {first} {last}?"), (S, "yes, that's me"),
              (C, one(r, ["thank you. we've noticed some unusual activity and just want to check a couple of things", "nothing to worry about, we're just doing a routine security check"])),
              (C, one(r, ["did you make a purchase of {amt} at an electronics store in Florida?", "did you just try to log in from a new device?"])),
              (S, one(r, ["no, I didn't", "no, I don't even have a computer"])),
              (C, one(r, ["okay, then someone may have your details. don't worry, we'll protect your account", "alright, I've put a hold on it, now we just need to secure your funds"])),
              (S, one(r, ["what do I need to do?", "is my money safe?"]))]
    else:
        t += [(C, one(r, ["your account has been compromised and there is a suspicious transaction of {amt}", "someone is trying to empty your account right now"])),
              (S, one(r, SHOCK))]
    t += [(C, one(r, ["I'll send a verification code to your phone, please read it back to me", "we need to move your money to a safe account while we investigate",
                      "please install the app called anydesk so I can secure your account remotely", "please confirm your card number and PIN so we can block the card"])),
          (S, one(r, ["is that safe?", "I'm not sure I should give that out", "okay, hold on"])),
          (C, one(r, ["absolutely, this line is secure and recorded", "yes, I'm from the bank, this is standard procedure"])),
          (C, one(r, ["we need to do this right now before the transfer goes through", "please hurry, the criminals are still active"]))]
    if r.random() < 0.6:
        t += [(C, one(r, ["and please don't discuss this with branch staff, we think someone inside is involved", "don't tell anyone about this call, it's part of an investigation"]))]
    t += [(S, one(r, OK + DOUBT))]
    return t


def investment(r, s, hard):
    s["amt"] = usd(r, [250, 500, 1000, 5000])
    t = [(C, one(r, ["hi, this is David from Summit Wealth Partners", "hello, I'm calling about an exclusive investment opportunity", "good afternoon, is this {title} {last}? I'm Alex, a financial advisor"])),
         (S, one(r, ["yes?", "who is this?", "how did you get my number?"]))]
    if hard:
        t += [(C, "you signed up a while ago for information about retirement income, I'm just following up"),
              (S, "I don't remember that"),
              (C, "that's okay. a lot of retirees are worried about inflation eating their savings, are you?"),
              (S, "well, everything is more expensive these days"),
              (C, "exactly. we help people like you grow their nest egg with a very safe strategy")]
    t += [(C, one(r, ["we trade crypto with an AI system, our clients make 25 percent a month", "it's a guaranteed return, completely risk free", "bitcoin is going to double this year and you can get in early"])),
          (S, one(r, ["I don't know anything about that", "that sounds too good to be true", "how much does it cost?"])),
          (C, one(r, ["you only need {amt} to start", "the minimum deposit is {amt}"])),
          (C, one(r, ["this offer closes today", "spots are limited, I need an answer now"])),
          (S, one(r, ["I should talk to my son first", "let me think about it"])),
          (C, one(r, ["your son won't understand this, it's a once in a lifetime chance", "there's no need, I'll walk you through everything"])),
          (C, one(r, ["just install this app on your computer and I'll set up your account", "read me your card number and I'll reserve your spot", "you can wire the deposit to our partner account"]))]
    return t


def other_scam(r, s, hard):
    kind = r.choice(["tech", "prize", "utility", "ssa", "medicare"])
    s["fee"] = usd(r, [199, 299, 499, 850])
    if kind == "tech":
        t = [(C, "hello, this is the technical department at Microsoft, your computer has been sending us error messages"), (S, "my computer?"),
             (C, "yes, it has a dangerous virus and hackers can see your bank details"), (S, one(r, SHOCK)),
             (C, "please turn on your computer and install our remote support tool so I can fix it"),
             (C, "there is a one time fee of {fee}, you can pay with gift cards or your card number"), (C, "please do it now before they steal your money")]
    elif kind == "prize":
        t = [(C, "congratulations! you've won 2 million dollars and a new car in the national sweepstakes"), (S, "really? I don't remember entering"),
             (C, "everyone in your area was entered automatically"), (C, "to release the prize you just need to pay the taxes and processing fee, {fee}"),
             (S, one(r, DOUBT)), (C, "you can pay with gift cards from any store, but it has to be today or the prize goes to the next winner")]
    elif kind == "utility":
        t = [(C, "this is the power company, your account is past due"), (S, "I always pay my bill"),
             (C, "our records show {fee} overdue, a crew is on the way to disconnect your power in 45 minutes"), (S, one(r, SHOCK)),
             (C, "you can avoid disconnection by paying right now with a prepaid card"), (C, "please don't hang up, I'll stay on the line while you get the card")]
    elif kind == "ssa":
        t = [(C, "this is the social security administration, your social security number has been suspended due to suspicious activity"), (S, "suspended? why?"),
             (C, "it was used in a money laundering case in Texas. to protect your benefits we need to verify your identity"),
             (C, "please confirm your social security number and bank account"), (S, one(r, DOUBT)),
             (C, "if you don't act immediately your benefits will be frozen and a warrant will be issued")]
    else:
        t = [(C, "hello, I'm calling from medicare about your new benefits card"), (S, "a new card?"),
             (C, "yes, the old cards are expiring, we need to verify your medicare number and bank details to send the new one"),
             (C, "there's a small activation fee of {fee}, I can take your card number now"), (S, one(r, DOUBT)),
             (C, "this has to be done today or your coverage will lapse")]
    if hard:
        t = [(C, one(r, ["good morning, is this {title} {last}?", "hi there, am I speaking with {first}?"])), (S, "yes, speaking"),
             (C, "thank you, I hope you're having a nice day, this will only take a minute")] + t
    return t


# ======================================================================================= normal calls
def family_chat(r, s, hard):
    t = [(C, one(r, ["hi {mom}, it's me", "hey {grandma}, it's {gn}", "hi, it's your sister, Carol, are you busy?"])),
         (S, one(r, ["oh hi sweetheart", "hi honey, how are you?", "no, not at all, how are you?"]))]
    topics = [
        [(C, "how's your back? did the new pills help?"), (S, "a little bit, I can sleep through the night now"), (C, "that's good, don't forget the physical therapy")],
        [(C, "we're thinking of coming over on sunday for lunch"), (S, "oh wonderful, I'll make pot roast"), (C, "the kids can't wait to see you")],
        [(C, "did you see the game last night?"), (S, "I fell asleep in the third quarter"), (C, "you missed a great finish")],
        [(C, "Lily got into college, we just found out"), (S, "oh that's wonderful, tell her I'm so proud"), (C, "I will, she wants to call you later")],
        [(C, "what's the weather like there? it's pouring here"), (S, "sunny but cold, there was frost this morning"), (C, "bundle up then")],
        [(C, "how's the garden doing?"), (S, "the tomatoes are finally ripening"), (C, "save some for me")],
        [(C, "I'm making your apple pie recipe, how much cinnamon do you use?"), (S, "two teaspoons and a pinch of nutmeg"), (C, "thanks, it never tastes like yours")],
        [(C, "did you get the photos I sent?"), (S, "yes, the baby is getting so big"), (C, "she's crawling everywhere now")],
    ]
    for tp in r.sample(topics, k=r.choice([2, 3])):
        t += tp
        if r.random() < 0.4:
            t += [(S, one(r, ["oh I know", "uh huh", "anyway, what else is new?", "that's how it goes"]))]
    t += [(C, one(r, ["okay, I'll let you go, love you", "alright, talk to you tomorrow", "I have to run, bye"])), (S, one(r, ["love you too, bye", "bye honey", "take care"]))]
    return t


def family_money(r, s, hard):
    s["amt"] = usd(r, [100, 200, 300, 500, 800])
    t = [(C, one(r, ["hi {mom}, got a minute?", "hey {grandma}, it's {gn}"])), (S, one(r, ["sure, what's up?", "hi sweetie, what's going on?"])),
         (C, one(r, ["my car needs new brakes and it's more than I expected, payday is next friday", "my textbooks cost way more this semester",
                     "the vet bill for the dog was bigger than we planned", "we're short on rent this month because my hours got cut"])),
         (C, one(r, ["could you lend me {amt}? I'll pay you back on the 15th", "would it be okay to borrow {amt}? no rush, whenever is fine"])),
         (S, one(r, ["of course, honey", "sure, should I send it to the same account?", "does your dad know?" if s["mom"] == "mom" else "does your mom know?"])),
         (C, one(r, ["yeah, same account is fine, there's no rush", "yeah, actually mom suggested I ask you", "I'll come by on saturday, you can just give it to me then"])),
         (S, one(r, ["okay, I'll do it tomorrow", "no problem", "come for dinner on saturday then"]))]
    if hard and r.random() < 0.5:
        t += [(C, "and maybe don't mention it to uncle Steve, he'll make jokes for a year"), (S, "ha, my lips are sealed")]
    t += [(C, one(r, ["thanks so much, you're the best", "thank you, really"])), (S, "anytime, love you")]
    return t


def surprise_party(r, s, hard):
    s["amt"] = usd(r, [40, 50, 100])
    return [(C, one(r, ["hi {grandma}, it's {gn}, I have a secret mission for you", "hey, it's {gn}, can you keep a secret?"])), (S, "oh, what is it?"),
            (C, one(r, ["we're throwing mom a surprise party for her 50th on saturday", "we're planning a surprise retirement party for uncle Joe"])),
            (S, one(r, ["oh how lovely", "where is it?"])),
            (C, "at the italian place on main street, 6 o'clock. don't tell anyone, it has to be a surprise"),
            (C, "we're all chipping in {amt} for a gift, a weekend at a spa"), (S, one(r, ["count me in", "should I give you cash or send it?"])),
            (C, "whatever's easier, you can give it to me at the party"), (S, "my lips are sealed"), (C, "thanks, see you saturday")]


def grandchild_secret(r, s, hard):
    secret = r.choice([("I failed my driving test again", "please don't tell mom, I want to pass first and then tell her"),
                       ("I got a tattoo", "don't tell dad, he'll freak out"),
                       ("I broke the vase in your hallway at thanksgiving", "please don't tell anyone, I'll buy you a new one"),
                       ("I'm dating someone new", "don't tell anyone yet, I want to bring them at christmas")])
    return [(C, "hey {grandma}, it's {gn}, can I tell you something?"), (S, "of course, sweetie"), (C, "promise you won't be mad"), (S, "I promise"),
            (C, secret[0]), (S, one(r, ["oh, that's not the end of the world", "oh you", "well, these things happen"])), (C, secret[1]),
            (S, one(r, ["okay, it stays between us", "alright, but you should tell them soon"])), (C, "thanks, love you"), (S, "love you too")]


def bank_real(r, s, hard):
    kind = r.choice(["card", "fraud_check", "appointment"])
    t = [(C, "hello, this is Linda from {bank}"), (S, "hello")]
    if kind == "card":
        t += [(C, "I'm calling to let you know your debit card expires at the end of the month, a new one is in the mail"), (S, "do I need to do anything?"),
              (C, "no, just activate it at an atm. we will never ask for your PIN or codes over the phone"), (S, "okay, thank you")]
    elif kind == "fraud_check":
        t += [(C, "we saw a card payment of 89 dollars at an online store, can you confirm if that was you?"),
              (S, one(r, ["yes, I ordered a sweater for my granddaughter", "no, that wasn't me"])),
              (C, "thank you. if it wasn't you, we'll block the card and you can call the number on the back of your card to dispute it"),
              (C, "remember, we will never ask you to move money or read us a code")]
    else:
        t += [(C, "just a reminder of your appointment at the branch on thursday at 10 about your savings account"), (S, "yes, I'll be there"),
              (C, "please bring a photo id. if you need to reschedule, call the branch directly")]
    t += [(C, "is there anything else I can help with?"), (S, "no, thank you"), (C, "have a nice day")]
    return t


def delivery_real(r, s, hard):
    return [(C, one(r, ["hi, I'm your delivery driver, I have a package for you", "hello, delivery for {title} {last}, I'll be there in about 10 minutes"])),
            (S, one(r, ["oh good, who is it from?", "okay, thank you"])),
            (C, one(r, ["it says it's from the pharmacy", "it's a big box from a garden store", "it's from an online bookstore"])),
            (S, one(r, ["oh that's my prescription refill", "that must be the bird feeder my son ordered", "great, I've been waiting for that"])),
            (C, one(r, ["if you're not home I can leave it with a neighbor", "I'll need a signature, it's a prescription", "I'll leave it by the front door"])),
            (S, "I'm home, just ring the bell"), (C, "perfect, see you soon")]


def medical(r, s, hard):
    kind = r.choice(["appt", "results", "pharmacy"])
    if kind == "appt":
        return [(C, "hi, this is Riverside Family Clinic, calling to reschedule your appointment with doctor Patel"), (S, "oh, what happened?"),
                (C, "the doctor is out sick on tuesday, we can do thursday at 9:30 or friday at 2"), (S, "thursday works"),
                (C, "great, please bring your medication list. your copay will be 20 dollars as usual"), (S, "thank you")]
    if kind == "results":
        return [(C, "hello, this is the nurse from doctor Patel's office about your blood test"), (S, "is everything okay?"),
                (C, "yes, everything looks fine, your cholesterol is a little high, the doctor wants to recheck in 3 months"),
                (S, "do I need to fast?"), (C, "yes, nothing to eat after midnight"), (S, "okay, thank you")]
    return [(C, "hi, this is the pharmacy on oak street, your prescription is ready for pickup"), (S, "oh good, how much is it?"),
            (C, "with your insurance it's 12 dollars"), (S, "I'll come by this afternoon"), (C, "great, we're open until 8")]


def neighbour_borrow(r, s, hard):
    s["amt"] = usd(r, [20, 40, 50, 60])
    return [(C, one(r, ["hi, it's Pat from next door", "hello, it's Gary from across the street"])), (S, "oh hi, everything okay?"),
            (C, one(r, ["I'm so embarrassed, my card got declined at the pharmacy and I need my inhaler", "the plumber is here and wants cash and I'm short"])),
            (C, "could you lend me {amt} until friday?"), (S, one(r, ["of course, come on over", "sure, I'll bring it over"])),
            (C, "thank you so much, I'll pay you back friday"), (S, "no rush, that's what neighbors are for")]


def police_real(r, s, hard):
    kind = r.choice(["witness", "wallet", "check"])
    t = [(C, "hello, this is {officer} from the {town} police department"), (S, "oh, is something wrong?")]
    if kind == "witness":
        t += [(C, "there was a break-in on your street last week and you mentioned you saw something"), (S, "yes, two young men in a gray van"),
              (C, "could you come by the station next week to give a statement?"), (S, "I can come monday morning"), (C, "thank you, ask for me at the front desk")]
    elif kind == "wallet":
        t += [(C, "someone turned in a wallet with your driver's license"), (S, "oh thank goodness, I lost it at the grocery store"),
              (C, "you can pick it up at the front desk any weekday between 8 and 6, just bring another id if you have one")]
    else:
        t += [(C, "your daughter asked us to do a wellness check because you weren't answering, are you okay?"), (S, "oh, I'm fine, my phone was on silent"),
              (C, "glad to hear it, maybe give her a call"), (S, "I will right now")]
    if hard:
        t += [(C, "if you want to verify this call, you can call the non emergency line or come to the station in person")]
    t += [(C, "have a good day"), (S, "you too")]
    return t


def handyman_real(r, s, hard):
    return [(C, "hi, this is Mike, the plumber, you called about the kitchen sink"), (S, "oh yes, when can you come?"),
            (C, "I can be there tomorrow at 9. the visit is 85 dollars and parts are extra if I need any"),
            (S, "that's fine"), (C, "I'll give you an invoice when I'm done, you can pay by check or card"), (S, "see you tomorrow")]


def church_real(r, s, hard):
    return [(C, "hello, it's Susan from saint mary's, I'm calling about the bake sale on saturday"), (S, "oh hi Susan"),
            (C, "would you be able to bring a couple of pies again? everyone loved yours"), (S, "of course, apple and pumpkin?"),
            (C, "perfect. the money goes to the food bank like last year"), (S, "wonderful, see you saturday")]


def wrong_number(r, s, hard):
    return [(C, one(r, ["hi, is this Tony's pizza?", "hello, is Brian there?", "hi, is this the dentist's office?"])), (S, "no, I think you have the wrong number"),
            (C, "oh, sorry about that"), (S, "no problem, bye")]


FAMILIES = {
    "en_grandchild": (grandchild, "scam", "grandchild"),
    "en_police": (police, "scam", "police"),
    "en_bank": (bank, "scam", "bank"),
    "en_investment": (investment, "scam", "investment"),
    "en_other_scam": (other_scam, "scam", "other"),
    "en_family_chat": (family_chat, "normal", "none"),
    "en_wrong_number": (wrong_number, "normal", "none"),
    "en_family_money": (family_money, "normal", "none"),
    "en_surprise_party": (surprise_party, "normal", "none"),
    "en_grandchild_secret": (grandchild_secret, "normal", "none"),
    "en_bank_real": (bank_real, "normal", "none"),
    "en_delivery_real": (delivery_real, "normal", "none"),
    "en_medical": (medical, "normal", "none"),
    "en_neighbour_borrow": (neighbour_borrow, "normal", "none"),
    "en_police_real": (police_real, "normal", "none"),
    "en_handyman_real": (handyman_real, "normal", "none"),
    "en_church_real": (church_real, "normal", "none"),
}
HARD_NEGATIVE_FAMILIES = {"en_family_money", "en_surprise_party", "en_grandchild_secret", "en_bank_real", "en_delivery_real", "en_medical",
                          "en_neighbour_borrow", "en_police_real", "en_handyman_real"}
