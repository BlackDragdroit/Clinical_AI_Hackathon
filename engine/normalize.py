"""Turn dictated text into its written form before anything is extracted.

Speech-to-text writes 'eva punkt brandl at labor minus kanal punkt example' or 'plus vier drei sechs sechs null …'.
Only unambiguous dictation is rewritten: a spoken 'at' needs a dotted domain after it, a digit run needs at least
six digits. The normalized text is what the rules and the model read, what every value is grounded in, and what
Dr. Hofer sees on the confirmation card ("verstanden: …"), so a wrong rewrite is visible before anything is sent.
"""
from __future__ import annotations

import re
import unicodedata

AT = {"at", "ät", "@", "klammeraffe", "affenschwanz", "at-zeichen"}
JOIN = {"punkt": ".", "dot": ".", ".": ".",
        "minus": "-", "bindestrich": "-", "strich": "-", "dash": "-", "hyphen": "-", "-": "-",
        "unterstrich": "_", "underscore": "_", "_": "_"}
DIGITS = {"null": "0", "zero": "0", "oh": "0", "eins": "1", "ein": "1", "one": "1", "zwei": "2", "zwo": "2",
          "two": "2", "drei": "3", "three": "3", "vier": "4", "four": "4", "fünf": "5", "fuenf": "5", "five": "5",
          "sechs": "6", "six": "6", "sieben": "7", "seven": "7", "acht": "8", "eight": "8", "neun": "9", "nine": "9"}
_PARTS = re.compile(r"^([(\[\"'„“]*)(.*?)([)\]\"'“”,;:!?.]*)$", re.S)
_WORD = re.compile(r"[0-9A-Za-zÄÖÜäöüß](?:[0-9A-Za-zÄÖÜäöüß._-]*[0-9A-Za-zÄÖÜäöüß])?")


def _parts(tok: str) -> tuple[str, str, str]:
    lead, core, trail = _PARTS.match(tok).groups()
    return (lead, trail, "") if not core and trail else (lead, core, trail)


def _wordlike(core: str) -> bool:
    return bool(_WORD.fullmatch(core)) and core.lower() not in AT and core.lower() not in JOIN


def _join_emails(toks: list[str]) -> list[str]:
    p = [_parts(t) for t in toks]
    n, spans, floor, i = len(toks), [], 0, 0
    while i < n:
        if (p[i][1].lower() in AT and i - 1 >= floor and i + 1 < n and _wordlike(p[i - 1][1]) and not p[i - 1][2]
                and _wordlike(p[i + 1][1]) and not p[i + 1][0]):
            start = i - 1                                   # left: "word (connector word)*"
            while (start - 2 >= floor and p[start - 1][1].lower() in JOIN and _wordlike(p[start - 2][1])
                   and not p[start - 1][2] and not p[start - 2][2] and not p[start - 1][0] and not p[start][0]):
                start -= 2
            end = i + 1                                     # right: "word (connector word)*"
            while (end + 2 < n and p[end + 1][1].lower() in JOIN and _wordlike(p[end + 2][1])
                   and not p[end][2] and not p[end + 1][2] and not p[end + 1][0] and not p[end + 2][0]):
                end += 2
            right = range(i + 1, end + 1)
            dotted = any("." in p[k][1] or JOIN.get(p[k][1].lower()) == "." for k in right)
            tld = p[end][1].split(".")[-1]
            if dotted and tld.isalpha() and len(tld) >= 2:
                spans.append((start, i, end))
                floor = i = end + 1
                continue
        i += 1
    out, k = [], 0
    for start, at, end in spans:
        out.extend(toks[k:start])
        local = "".join(JOIN.get(p[j][1].lower(), p[j][1]) for j in range(start, at))
        domain = "".join(JOIN.get(p[j][1].lower(), p[j][1]) for j in range(at + 1, end + 1))
        out.append(p[start][0] + f"{local}@{domain}".lower() + p[end][2])   # dictation carries no case
        k = end + 1
    return out + toks[k:]


def _digit(core: str) -> str | None:
    if re.fullmatch(r"\+?\d{1,4}", core):
        return core
    return DIGITS.get(core.lower())


def _join_numbers(toks: list[str]) -> list[str]:
    p = [_parts(t) for t in toks]
    out, i, n = [], 0, len(toks)
    while i < n:
        plus = p[i][1].lower() == "plus" and not p[i][2]
        j = i + 1 if plus else i
        run: list[str] = []
        while j < n and _digit(p[j][1]) is not None and (j == i or not p[j][0]):
            run.append(_digit(p[j][1]))
            if p[j][2]:            # punctuation ends the number
                j += 1
                break
            j += 1
        digits = "".join(run)
        spoken = any(not re.fullmatch(r"\+?\d+", d) for d in [p[k][1] for k in range((i + 1) if plus else i, j)])
        if len(run) >= 3 and len(digits.lstrip("+")) >= 6 and (spoken or plus):
            out.append(p[i][0] + ("+" if plus and not digits.startswith("+") else "") + digits + p[j - 1][2])
            i = j
            continue
        out.append(toks[i])
        i += 1
    return out


def normalize(text: str) -> str:
    """NFC, single spaces, dictated e-mail addresses and phone numbers written out."""
    text = unicodedata.normalize("NFC", text or "").replace(" ", " ")
    lines = []
    for line in text.splitlines():
        toks = line.split()
        lines.append(" ".join(_join_numbers(_join_emails(toks))))
    return "\n".join(lines).strip()


_DE = {"bitte", "und", "der", "die", "das", "von", "bei", "für", "mit", "anfordern", "anfragen", "geb", "frau", "herrn",
       "herr", "ich", "brauche", "aktuelle", "aktuellen", "befund", "wegen", "vor", "eingriff", "den", "dem", "ist"}
_EN = {"please", "and", "the", "from", "for", "with", "request", "ask", "born", "mrs", "mr", "ms", "need", "latest",
       "results", "report", "because", "before", "procedure", "of", "to", "is", "her", "his"}


def language(text: str) -> str:
    toks = re.findall(r"[a-zäöüß]+", text.lower())
    de, en = sum(t in _DE for t in toks), sum(t in _EN for t in toks)
    return "en" if en > de else "de"
