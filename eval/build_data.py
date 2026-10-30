"""Build the engine's test sets from Synthea + templates. Deterministic (seed in SEED).

  eval/data/patients.json        ~440 patients: Synthea birth dates/sex, Austrian names, plus planted namesakes
                                 (same name, other birth date) and near-twins (similar given name, same date)
  eval/data/senders.json         outside people (labs, rehab clinics) with e-mail or mobile number
  eval/data/requests_dev.jsonl   600 templated requests (DE/EN, typed/dictated, traps) with gold labels
  eval/data/documents.jsonl      120 base documents (100 lab from Synthea values, 20 discharge reports) with gold
                                 labels and the request they answer; rendered to PDF/scan/photo at eval time

The held-out request set (eval/data/requests_test.jsonl) is NOT generated here: it was written separately,
without access to the engine's code, so it does not share the templates' phrasing.

uv run python -m eval.build_data        (needs eval/data/synthea_labs.json from `python -m eval.synthea`)
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "eval" / "data"
sys.path.insert(0, str(ROOT / "core"))
from gen_pairs import FAMILY, GIVEN_F, GIVEN_M  # noqa: E402

SEED = 20261029
REQUEST_DATE = datetime(2026, 10, 29, 9, 30)
MONTHS_DE = ["Jänner", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
NEAR = {"Maria": "Marie", "Anna": "Anja", "Eva": "Evi", "Lena": "Lina", "Sophie": "Sofie", "Julia": "Julian", "Max": "Marx",
        "Stefan": "Stephan", "Thomas": "Tomas", "Michael": "Michel", "Andreas": "Andrea", "Peter": "Petra", "Lukas": "Lucas"}
COAG = ["6301-6", "14979-9", "777-3", "3255-7"]
PANEL_OF = {"718-7": "cbc", "4544-3": "cbc", "789-8": "cbc", "6690-2": "cbc", "777-3": "cbc",
            "2345-7": "glucose", "2160-0": "kidney", "3094-0": "kidney", "2951-2": "kidney", "2823-3": "kidney",
            "2093-3": "lipids", "1742-6": "liver", "1920-8": "liver"}
PANEL_WORDS = {"cbc": (["Blutbild", "kleines Blutbild"], ["blood count", "CBC"]),
               "kidney": (["Nierenwerte", "Nierenfunktion"], ["kidney function", "renal panel"]),
               "liver": (["Leberwerte"], ["liver function"]), "lipids": (["Blutfette", "Cholesterin"], ["lipids"]),
               "glucose": (["Blutzucker"], ["blood glucose"]), "coagulation": (["Gerinnung", "Gerinnungswerte"], ["coagulation", "clotting tests"])}
TEST_NAMES = {  # code -> (English, German) as labs print them
    "6301-6": ("INR", "INR"), "14979-9": ("aPTT", "aPTT"), "777-3": ("Platelets", "Thrombozyten"), "3255-7": ("Fibrinogen", "Fibrinogen"),
    "718-7": ("Hemoglobin", "Hämoglobin"), "4544-3": ("Hematocrit", "Hämatokrit"), "789-8": ("Erythrocytes", "Erythrozyten"),
    "6690-2": ("Leukocytes", "Leukozyten"), "2345-7": ("Glucose", "Glukose"), "2160-0": ("Creatinine", "Kreatinin"),
    "3094-0": ("Urea nitrogen", "Harnstoff-N"), "2951-2": ("Sodium", "Natrium"), "2823-3": ("Potassium", "Kalium"),
    "2093-3": ("Cholesterol", "Cholesterin"), "1742-6": ("ALT", "GPT"), "1920-8": ("AST", "GOT")}
REF = {"6301-6": "0.8 to 1.2", "14979-9": "25 to 37", "777-3": "150 to 400", "3255-7": "2.0 to 4.0", "718-7": "12 to 16",
       "4544-3": "36 to 46", "789-8": "4.0 to 5.2", "6690-2": "4.0 to 10.0", "2345-7": "70 to 100", "2160-0": "0.5 to 1.0",
       "3094-0": "7 to 20", "2951-2": "135 to 145", "2823-3": "3.5 to 5.1", "2093-3": "< 200", "1742-6": "< 35", "1920-8": "< 35"}
LABS = ["Labor Kanalstraße", "Labor Nord", "Zentrallabor Donau", "Labor am Ring", "Medizinisches Labor Graz-West", "Labor Dr. Wimmer"]
REHAS = ["Reha Waldblick", "Rehaklinik Seeblick", "Rehazentrum Alpenblick", "Klinik am Kurpark"]


def _slug(s: str) -> str:
    import unicodedata
    t = s.lower().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", " ": "-", ".": ""}))
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return "".join(c for c in t if c.isalnum() or c == "-").strip("-")


def build_patients(rng: random.Random, synthea: list[dict]) -> list[dict]:
    pts = [{"ref": "Patient/maria-beispiel", "name": "Maria Beispiel", "dob": "1961-03-12", "gender": "female", "labs_key": None},
           {"ref": "Patient/max-beispiel", "name": "Max Beispiel", "dob": "1960-01-01", "gender": "male", "labs_key": None}]
    used = {("Maria Beispiel", "1961-03-12")}
    for i, s in enumerate(synthea):
        g = rng.choice(GIVEN_F if s["gender"] == "female" else GIVEN_M)
        name = f"{g} {rng.choice(FAMILY)}"
        if (name, s["birthDate"]) in used:
            continue
        used.add((name, s["birthDate"]))
        pts.append({"ref": f"Patient/bb-{i:04d}", "name": name, "dob": s["birthDate"], "gender": s["gender"], "labs_key": s["synthea_id"]})
    base = list(pts[2:])
    for p in rng.sample(base, min(25, len(base))):           # namesake: same name, other birth date
        d = date.fromisoformat(p["dob"]) + timedelta(days=rng.randint(400, 9000) * rng.choice((-1, 1)))
        pts.append({"ref": p["ref"] + "-ns", "name": p["name"], "dob": d.isoformat(), "gender": p["gender"], "labs_key": None,
                    "trap_of": p["ref"], "trap": "namesake"})
    for p in rng.sample([p for p in base if p["name"].split()[0] in NEAR], 15):   # near-twin: similar name, same date
        g, fam = p["name"].split(" ", 1)
        pts.append({"ref": p["ref"] + "-tw", "name": f"{NEAR[g]} {fam}", "dob": p["dob"], "gender": p["gender"], "labs_key": None,
                    "trap_of": p["ref"], "trap": "twin"})
    return pts


def build_senders(rng: random.Random) -> list[dict]:
    out = [{"name": "Dr. Eva Brandl", "org": "Labor Kanalstraße", "kind": "lab", "email": "eva.brandl@labor-kanal.example"},
           {"name": "Stefan Kern", "org": "Reha Waldblick", "kind": "report", "phone": "+436600000101"}]
    for i in range(28):
        female = rng.random() < 0.5
        g, f = rng.choice(GIVEN_F if female else GIVEN_M), rng.choice(FAMILY)
        if i % 3 != 2:
            org = rng.choice(LABS)
            title = rng.choice(["Dr.", "Dr.", "Mag.", "Dr. med."])
            out.append({"name": f"{title} {g} {f}", "org": org, "kind": "lab",
                        "email": f"{_slug(g)}.{_slug(f)}@{_slug(org)}.example"})
        else:
            out.append({"name": f"{g} {f}", "org": rng.choice(REHAS), "kind": "report",
                        "phone": f"+43{rng.choice(['660', '664', '676', '699'])}{rng.randint(1000000, 9999999)}"})
    return out


# ---------------------------------------------------------------- requests
def _dob_text(d: date, lang: str, rng: random.Random) -> str:
    opts = [f"{d:%d.%m.%Y}", f"{d.day}.{d.month}.{d.year}"] + (
        [f"{d.day}. {MONTHS_DE[d.month - 1]} {d.year}"] if lang == "de" else [f"{d.day} {MONTHS_EN[d.month - 1]} {d.year}", f"{MONTHS_EN[d.month - 1]} {d.day}, {d.year}"])
    return rng.choice(opts)


_DIG_DE = "null eins zwei drei vier fünf sechs sieben acht neun".split()
_DIG_EN = "zero one two three four five six seven eight nine".split()


def _spoken_contact(c: str, lang: str) -> str:
    if "@" in c:
        local, dom = c.split("@")
        w = {"de": {".": " punkt ", "-": " minus ", "_": " unterstrich "}, "en": {".": " dot ", "-": " dash ", "_": " underscore "}}[lang]
        say = lambda s: "".join(w.get(ch, ch) for ch in s)
        return f"{say(local)} at {say(dom)}".replace("  ", " ")
    digits = _DIG_DE if lang == "de" else _DIG_EN
    return ("plus " if c.startswith("+") else "") + " ".join(digits[int(ch)] for ch in c.lstrip("+"))


def _typed_contact(c: str, rng: random.Random) -> str:
    if "@" in c or rng.random() < 0.4:
        return c
    n = c[3:]                                   # +43 660 1234567 or 0660 1234567
    return rng.choice([f"+43 {n[:3]} {n[3:6]} {n[6:]}", f"0{n[:3]} {n[3:]}", c])


def _person(p: dict, lang: str, rng: random.Random) -> str:
    lay = {"female": ("Frau", "Mrs"), "male": ("Herrn", "Mr")}[p.get("gender") or "female"][0 if lang == "de" else 1]
    return f"{lay} {p['name']}" if rng.random() < 0.7 else p["name"]


def _recipient(s: dict, style: str, rng: random.Random) -> str:
    n = s["name"]
    if style == "dictated":
        n = n.replace("Dr. med.", "Doktor").replace("Dr.", "Doktor").replace("Mag.", "Magister")
    elif not n.startswith(("Dr", "Mag")) and rng.random() < 0.5:
        n = ("Herrn " if n.split()[0] in GIVEN_M else "Frau ") + n
    return n


def build_requests(rng: random.Random, pts: list[dict], senders: list[dict], n: int) -> list[dict]:
    twinned = {p["trap_of"] for p in pts if p.get("trap") == "twin"}
    plain = [p for p in pts if "trap" not in p and p["ref"] not in twinned]
    by_ref = {p["ref"]: p for p in pts}
    twin_targets = [by_ref[p["trap_of"]] for p in pts if p.get("trap") == "twin"]
    ns_targets = [by_ref[p["trap_of"]] for p in pts if p.get("trap") == "namesake" and p["trap_of"] not in twinned]
    out = []
    for i in range(n):
        lang = "de" if rng.random() < 0.7 else "en"
        style = "dictated" if rng.random() < 0.4 else "typed"
        trap = rng.choices(["none", "no_dob", "no_contact", "twin", "namesake", "homoglyph", "ref"], [55, 8, 7, 8, 10, 6, 6])[0]
        s = rng.choice(senders)
        p = rng.choice(twin_targets if trap == "twin" else ns_targets if trap == "namesake" else plain)
        doc = s["kind"]
        panel = rng.choice(list(PANEL_WORDS)) if doc == "lab" else None
        contact = s.get("email") or s["phone"]
        if trap == "homoglyph" and style == "dictated":
            trap = "none"                        # a capital I cannot be spoken; the lookalike trap is for typed requests
        if trap == "homoglyph" and "@" in contact:
            contact = contact.replace("l", "I", 1) if "l" in contact.split("@")[1] else contact.replace("o", "0", 1)
        elif trap == "homoglyph":
            trap = "none"
        d = date.fromisoformat(p["dob"])
        who = _person(p, lang, rng)
        rec = _recipient(s, style, rng)
        ctext = _spoken_contact(contact, lang) if style == "dictated" else _typed_contact(contact, rng)
        dob = "" if trap == "no_dob" else _dob_text(d, lang, rng)
        if lang == "de":
            what = rng.choice(PANEL_WORDS[panel][0]) if panel else rng.choice(["den Entlassungsbericht", "den Reha-Bericht", "den Entlassungsbrief"])
            dob_part = f", geb. {dob}" if dob and rng.random() < 0.6 else (f" (*{dob})" if dob else "")
            pat = f"Patient/{p['ref'].split('/')[1]}" if trap == "ref" else f"{who}{dob_part}"
            reason = rng.choice(["", " vor dem geplanten Eingriff", " wegen Kontrolle", " vor der Operation", ""])
            org = f", {s['org']}," if rng.random() < 0.5 else ""
            c = "" if trap == "no_contact" else (f" {ctext}" if rng.random() < 0.5 else f" unter {ctext}")
            text = rng.choice([
                f"Bitte bei {rec}{org}{c} {what} von {pat} anfordern{reason}.",
                f"{what[0].upper() + what[1:]} für {pat} bei {rec}{org}{c} anfragen{reason}.",
                f"Ich brauche {what} von {pat}{reason}. Bitte {rec}{org} anschreiben{(':' + c) if c else ''}.",
            ])
        else:
            what = rng.choice(PANEL_WORDS[panel][1]) + " results" if panel else rng.choice(["the discharge report", "the rehab discharge summary"])
            dob_part = f", born {dob}" if dob and rng.random() < 0.6 else (f" (DOB {dob})" if dob else "")
            pat = f"Patient/{p['ref'].split('/')[1]}" if trap == "ref" else f"{who}{dob_part}"
            reason = rng.choice(["", " before the planned procedure", " for follow-up", ""])
            org = f" ({s['org']})" if rng.random() < 0.5 else ""
            c = "" if trap == "no_contact" else f" at {ctext}" if "@" not in contact or style == "dictated" else f", {ctext},"
            text = rng.choice([
                f"Please ask {rec}{org}{c} for {what} of {pat}{reason}.",
                f"Request {what} for {pat} from {rec}{org}{c}{reason}.",
            ])
        text = " ".join(text.split()).replace(" ,", ",").replace(",.", ".").replace(",,", ",")
        expect_ready = trap in ("none", "namesake", "homoglyph", "ref")
        out.append({"id": f"dev-{i:04d}", "lang": lang, "style": style, "trap": trap, "text": text,
                    "gold": {"recipient": s["name"], "contact": contact, "contact_kind": "email" if "@" in contact else "sms",
                             "patient_ref": p["ref"] if trap not in ("no_dob", "twin") else None, "doc_type": doc,
                             "panel": panel, "ready": expect_ready}})
    return out


# ---------------------------------------------------------------- documents
def _fmt(v: float, comma: bool) -> str:
    s = f"{v:.1f}" if abs(v) < 100 else f"{v:.0f}"
    return s.replace(".", ",") if comma else s


def build_documents(rng: random.Random, pts: list[dict], senders: list[dict], synthea: list[dict]) -> list[dict]:
    labs_of = {s["synthea_id"]: s["labs"] for s in synthea}
    with_labs = [p for p in pts if p.get("labs_key") and labs_of.get(p["labs_key"])]
    lab_senders = [s for s in senders if s["kind"] == "lab"]
    rep_senders = [s for s in senders if s["kind"] == "report"]
    out = []
    for i in range(120):
        is_lab = i < 100
        p = rng.choice(with_labs)
        trap = rng.choices(["none", "wrong_patient", "old", "implausible", "no_loinc", "namesake_doc"], [60, 12, 8, 8, 8, 4])[0]
        if not is_lab:
            trap = rng.choice(["none", "none", "none", "wrong_patient"])
        subject = p
        if trap == "wrong_patient":
            subject = rng.choice([q for q in with_labs if q["ref"] != p["ref"]])
        elif trap == "namesake_doc":
            subject = {**p, "dob": (date.fromisoformat(p["dob"]) + timedelta(days=rng.randint(500, 5000))).isoformat()}
        lang = "de" if rng.random() < 0.5 else "en"
        comma = lang == "de" and rng.random() < 0.6
        d = date.fromisoformat(subject["dob"])
        dob = _dob_text(d, lang, rng)
        age = rng.randint(40, 120) if trap == "old" else rng.randint(0, 9)
        taken = REQUEST_DATE - timedelta(days=age, hours=rng.randint(1, 6))
        taken_txt = f"{taken:%d.%m.%Y, %H:%M}" if lang == "de" or rng.random() < 0.5 else f"{taken.day} {MONTHS_EN[taken.month - 1]} {taken.year}, {taken:%H:%M}"
        if is_lab:
            s = rng.choice(lab_senders)
            groups = defaultdict(list)
            for lab in labs_of[p["labs_key"]]:
                if lab["loinc"] in TEST_NAMES and lab["value"] is not None:
                    groups[lab["date"][:10]].append(lab)
            day = max(groups, key=lambda k: (len(groups[k]), k)) if groups else None
            rows_src = {lab["loinc"]: lab for lab in groups.get(day, [])}
            if trap in ("none", "old", "no_loinc") and rng.random() < 0.35:   # some answers are the coagulation panel
                rows_src = {c: {"loinc": c, "value": v, "unit": u} for c, v, u in
                            zip(COAG, (rng.uniform(0.9, 1.15), rng.uniform(26, 36), rng.uniform(160, 380), rng.uniform(2.1, 3.9)),
                                ("", "s", "10^9/L", "g/L"))}
            rows = []
            for code, lab in list(rows_src.items())[:8]:
                v = float(lab["value"])
                unit = lab["unit"]
                rows.append({"test": TEST_NAMES[code][1 if lang == "de" else 0], "result": _fmt(v, comma), "unit": unit,
                             "reference_range": REF[code].replace("to", "bis") if lang == "de" else REF[code],
                             "loinc": "" if (trap == "no_loinc" and rng.random() < 0.6) else code, "true_loinc": code})
            if not rows:
                continue
            if trap == "implausible":
                r = rng.choice(rows)
                r["result"] = _fmt(float(r["result"].replace(",", ".")) * 100, comma)
            panel = PANEL_OF.get(rows[0]["true_loinc"]) if rows[0]["true_loinc"] not in COAG else "coagulation"
            requested = COAG if panel == "coagulation" else None
            if lang == "de":
                head = [f"# {s['org']}: Laborbefund", "", f"Patient{'in' if subject.get('gender') == 'female' else ''}: {subject['name']}, geb. {dob}",
                        f"Abnahme: {taken_txt}", f"Befundet: {(taken + timedelta(hours=3)):%d.%m.%Y, %H:%M}", "",
                        "| Parameter | Ergebnis | Einheit | Referenzbereich | LOINC |", "|---|---|---|---|---|"]
                tail = ["", f"Validiert von: {s['name']}"]
            else:
                head = [f"# {s['org']}: lab report", "", f"Patient: {subject['name']}, born {dob}", f"Sample taken: {taken_txt}",
                        f"Reported: {(taken + timedelta(hours=3)).day} {MONTHS_EN[taken.month - 1]} {taken.year}, {(taken + timedelta(hours=3)):%H:%M}", "",
                        "| Test | Result | Unit | Reference range | LOINC code |", "|---|---|---|---|---|"]
                tail = ["", f"Validated by: {s['name']}"]
            md = "\n".join(head + [f"| {r['test']} | {r['result']} | {r['unit']} | {r['reference_range']} | {r['loinc']} |" for r in rows] + tail) + "\n"
        else:
            s = rng.choice(rep_senders)
            start = REQUEST_DATE.date() - timedelta(days=rng.randint(20, 60))
            end = start + timedelta(days=21)
            if lang == "de":
                md = (f"# {s['org']}: Entlassungsbericht\n\nPatient{'in' if subject.get('gender') == 'female' else ''}: {subject['name']}, geb. {dob}\n"
                      f"Aufenthalt: {start:%d.%m.%Y} - {end:%d.%m.%Y}\nGrund: Rehabilitation nach Knie-TEP rechts\n\n## Verlauf\n"
                      "Mobilisation an zwei Unterarmstützkrücken, zuletzt Gehstrecke 400 m ohne Hilfsmittel.\n\n## Medikation bei Entlassung\n"
                      "- Enoxaparin 40 mg 1x täglich bis zum Ende der 6. postoperativen Woche\n- Paracetamol 500 mg bei Bedarf\n\n"
                      f"Verfasst von: Dr. {rng.choice(GIVEN_F)} {rng.choice(FAMILY)}, ärztliche Leitung\nGesendet von: {s['name']}, Entlassungsmanagement\n")
            else:
                md = (f"# {s['org']}: discharge report\n\nPatient: {subject['name']}, born {dob}\n"
                      f"Stay: {start.day} {MONTHS_EN[start.month - 1]} {start.year} to {end.day} {MONTHS_EN[end.month - 1]} {end.year}\n"
                      "Reason: rehabilitation after a right knee replacement\n\n## Course\nWalks 400 metres without aids at discharge.\n\n"
                      "## Medication at discharge\n- Enoxaparin 40 mg once a day until the end of week 6 after surgery\n\n"
                      f"Written by: Dr. {rng.choice(GIVEN_F)} {rng.choice(FAMILY)}, medical director\nSent by: {s['name']}, discharge management\n")
            rows, requested = [], None
        expect = "reject" if trap == "wrong_patient" else "review" if trap == "namesake_doc" else "file"
        out.append({"id": f"doc-{i:03d}", "lang": lang, "kind": "lab" if is_lab else "report", "trap": trap, "markdown": md,
                    "request": {"patient_ref": p["ref"], "patient_name": p["name"], "patient_dob": p["dob"], "sender": s["name"],
                                "doc_type": "lab" if is_lab else "report", "requested_loinc": requested,
                                "requested_at": REQUEST_DATE.isoformat()},
                    "gold": {"patient_name": subject["name"], "patient_dob": subject["dob"], "decision": expect,
                             "rows": [{k: r[k] for k in ("test", "result", "unit", "reference_range", "loinc")} for r in rows],
                             "flags": {"old": trap == "old", "implausible": trap == "implausible"}}})
    return out


def main() -> None:
    rng = random.Random(SEED)
    syn_path = DATA / "synthea_labs.json"
    if not syn_path.exists():
        sys.exit("run `python -m eval.synthea` first")
    synthea = json.loads(syn_path.read_text(encoding="utf-8"))
    pts = build_patients(rng, synthea)
    senders = build_senders(rng)
    reqs = build_requests(rng, pts, senders, 600)
    docs = build_documents(rng, pts, senders, synthea)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "patients.json").write_text(json.dumps([{k: v for k, v in p.items() if k != "labs_key"} for p in pts],
                                                   ensure_ascii=False, indent=0), encoding="utf-8")
    (DATA / "senders.json").write_text(json.dumps(senders, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, rows in (("requests_dev.jsonl", reqs), ("documents.jsonl", docs)):
        (DATA / name).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"patients {len(pts)}  senders {len(senders)}  dev requests {len(reqs)}  documents {len(docs)}")


if __name__ == "__main__":
    main()
