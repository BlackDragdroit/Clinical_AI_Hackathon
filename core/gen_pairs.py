"""Synthetic labelled identity pairs for calibrating/evaluating fs_matcher.

Match pairs: same person with realistic corruptions (typos, umlaut spellings,
titles, double names, swapped day/month, digit typos, missing DOB).
Non-match pairs (how misdeliveries really happen): random other patient,
same family name (relatives), same full name different DOB (namesake),
same DOB different name (twin / coincidence), same family+given with corrupted DOB.

Usage: python gen_pairs.py --n 6000 --seed 7 --out pairs.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta

GIVEN_F = ["Maria", "Anna", "Eva", "Lena", "Sophie", "Johanna", "Katharina", "Elisabeth", "Sabine", "Petra",
           "Christina", "Barbara", "Andrea", "Monika", "Claudia", "Theresa", "Julia", "Lisa", "Hannah", "Nina",
           "Gertrude", "Margarethe", "Ingrid", "Renate", "Jasmin", "Ayşe", "Fatma", "Emine", "Zoë", "Chloé"]
GIVEN_M = ["Max", "Stefan", "Thomas", "Michael", "Andreas", "Christian", "Martin", "Markus", "Peter", "Johann",
           "Josef", "Franz", "Georg", "Lukas", "Daniel", "David", "Florian", "Paul", "Felix", "Jakob",
           "Karl", "Wolfgang", "Günther", "Jürgen", "Mehmet", "Ali", "Mustafa", "Dragan", "Zoran", "Jürgen"]
FAMILY = ["Beispiel", "Huber", "Gruber", "Bauer", "Wagner", "Müller", "Pichler", "Steiner", "Moser", "Mayer",
          "Hofer", "Leitner", "Berger", "Fuchs", "Eder", "Fischer", "Schmid", "Winkler", "Weber", "Schwarz",
          "Maier", "Schneider", "Reiter", "Mayr", "Schmidt", "Wimmer", "Egger", "Brunner", "Lang", "Baumgartner",
          "Auer", "Binder", "Lechner", "Wolf", "Wallner", "Aigner", "Ebner", "Koller", "Lehner", "Haas",
          "Schuster", "Yilmaz", "Kaya", "Demir", "Novak", "Horvath", "Kovacs", "Jovanović", "Petrović", "Ćosić"]
TITLES = ["Dr.", "Dr. med.", "Mag.", "DI", "Prof.", "Dr. med. univ.", "OÄ Dr.", "Ing."]
UML = {"ä": ["ae", "a"], "ö": ["oe", "o"], "ü": ["ue", "u"], "ß": ["ss"], "é": ["e"], "ć": ["c"], "ş": ["s"], "ë": ["e"]}
KEYS = "abcdefghijklmnopqrstuvwxyz"


def rand_person(rng: random.Random) -> dict:
    female = rng.random() < 0.5
    given = rng.choice(GIVEN_F if female else GIVEN_M)
    if rng.random() < 0.15:                                   # double given name
        given += " " + rng.choice(GIVEN_F if female else GIVEN_M)
    family = rng.choice(FAMILY)
    if rng.random() < 0.07:                                   # hyphenated family name
        family += "-" + rng.choice(FAMILY)
    dob = date(1930, 1, 1) + timedelta(days=rng.randrange(0, 365 * 90))
    return {"given": given, "family": family, "dob": dob}


def typo(s: str, rng: random.Random) -> str:
    if len(s) < 3:
        return s
    i = rng.randrange(len(s))
    op = rng.choice(["sub", "del", "ins", "swap"])
    if op == "sub":
        return s[:i] + rng.choice(KEYS) + s[i + 1:]
    if op == "del":
        return s[:i] + s[i + 1:]
    if op == "ins":
        return s[:i] + rng.choice(KEYS) + s[i:]
    if i < len(s) - 1:
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    return s


def corrupt_name(s: str, rng: random.Random) -> str:
    r = rng.random()
    if r < 0.35:
        return typo(s, rng)
    if r < 0.60:
        for k, vs in UML.items():
            if k in s:
                return s.replace(k, rng.choice(vs))
        return s.upper() if rng.random() < 0.5 else s.lower()
    if r < 0.75:
        return rng.choice(TITLES) + " " + s
    if r < 0.85 and " " in s:                                 # drop second given name
        return s.split(" ")[0]
    if r < 0.95 and "-" in s:                                 # drop second family name
        return s.split("-")[0]
    return s


def corrupt_dob(d: date | None, rng: random.Random) -> date | None:
    if d is None:
        return None
    r = rng.random()
    if r < 0.45:
        return d
    if r < 0.60 and d.day <= 12 and d.day != d.month:         # swapped day/month
        return date(d.year, d.day, d.month)
    if r < 0.80:                                              # one digit typo
        s = list(d.strftime("%Y%m%d"))
        i = rng.choice([2, 3, 6, 7])                          # decade/year or day digit
        s[i] = str((int(s[i]) + rng.choice([1, -1, 10])) % 10)
        try:
            return date(int("".join(s[:4])), int("".join(s[4:6])), int("".join(s[6:])))
        except ValueError:
            return d
    if r < 0.88:
        return d + timedelta(days=rng.choice([-1, 1]))
    if r < 0.93:
        return None                                           # DOB missing
    return d


def make_match(p: dict, rng: random.Random) -> dict:
    q = dict(p)
    n_corr = rng.choice([0, 0, 1, 1, 2])
    for _ in range(n_corr):
        f = rng.choice(["given", "family", "dob"])
        if f == "dob":
            q["dob"] = corrupt_dob(q["dob"], rng)
        else:
            q[f] = corrupt_name(q[f], rng)
    return q


def make_nonmatch(p: dict, rng: random.Random) -> dict:
    # mix reflects how misdeliveries actually happen (random other patient dominates)
    r = rng.random()
    if r < 0.70:                                              # random other patient
        q = rand_person(rng)
    elif r < 0.90:                                            # relative: same family name
        q = rand_person(rng)
        q["family"] = p["family"]
    elif r < 0.97:                                            # namesake: same full name, other DOB
        q = dict(p)
        q["dob"] = date(1930, 1, 1) + timedelta(days=rng.randrange(0, 365 * 90))
    elif r < 0.99:                                            # same DOB, different person (coincidence)
        q = rand_person(rng)
        q["dob"] = p["dob"]
    else:                                                     # twin: same family name and DOB
        q = rand_person(rng)
        q["family"], q["dob"] = p["family"], p["dob"]
    if q["given"] == p["given"] and q["family"] == p["family"] and q["dob"] == p["dob"]:
        q["dob"] = q["dob"] + timedelta(days=rng.choice([400, -400, 3650]))   # must differ
    if rng.random() < 0.3:                                    # non-matches get typos too
        q[rng.choice(["given", "family"])] = corrupt_name(q[rng.choice(["given", "family"])], rng)
    return q


def fmt_dob(d: date | None, rng: random.Random) -> str:
    if d is None:
        return ""
    return rng.choice([d.isoformat(), d.strftime("%d.%m.%Y"), d.strftime("%-d %B %Y"), d.strftime("%d.%m.%Y")])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="pairs.jsonl")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    with open(a.out, "w") as fh:
        for i in range(a.n):
            p = rand_person(rng)
            y = 1 if i % 2 == 0 else 0
            q = make_match(p, rng) if y else make_nonmatch(p, rng)
            fh.write(json.dumps({
                "a_given": p["given"], "a_family": p["family"], "a_dob": p["dob"].isoformat(),
                "b_given": q["given"], "b_family": q["family"], "b_dob": fmt_dob(q["dob"], rng),
                "label": y}, ensure_ascii=False) + "\n")
    print(f"wrote {a.n} pairs to {a.out}")


if __name__ == "__main__":
    main()
