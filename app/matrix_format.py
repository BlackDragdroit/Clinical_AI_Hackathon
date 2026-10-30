"""Plain-text bot messages -> Matrix HTML (formatted_body). Owner: SWE 1.

Messages stay plain text everywhere (CLI, outbox, tests); the bot adds HTML on the way out:
first line bold (it says what happened), URLs clickable, `!commands` as code so they can be
copied exactly. Only tags from the Matrix spec's recommended HTML subset are used.
"""
from __future__ import annotations

import html
import re

_URL = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)|https?://[^\s<>()]+")   # [label](url) or a bare url
_CMD = re.compile(r"(?<![\w/])(![a-zäöü]+(?: [a-z0-9]{6,})?)")


def _inline(line: str) -> str:
    out, pos = [], 0
    for m in _URL.finditer(line):
        out.append(_cmd(html.escape(line[pos:m.start()])))
        if m.group(1):
            url, label, end = m.group(2), m.group(1), m.end()
        else:
            url = m.group(0).rstrip(".,;")
            label, end = _label(url), m.start() + len(url)
        out.append(f'<a href="{html.escape(url)}">{html.escape(label)}</a>')
        pos = end
    out.append(_cmd(html.escape(line[pos:])))
    return "".join(out)


def _cmd(escaped: str) -> str:
    return _CMD.sub(r"<code>\1</code>", escaped)


def _label(url: str) -> str:
    """'http://host/fhir/DiagnosticReport/9ae0…' -> 'DiagnosticReport/9ae0…' (readable, still unique)."""
    m = re.search(r"/fhir/([A-Za-z]+/[^/]+)$", url)
    return m.group(1) if m else url


_CLAUSE = re.compile(r"( – |: |\. )")


def _headline(line: str) -> str:
    """Bold what happened, not a whole paragraph: a long first line is bolded up to its first clause."""
    if len(line) > 90:
        m = _CLAUSE.search(line, 15)
        if m and m.start() < 90:
            cut = m.end() if m.group(1) == ". " else m.start()
            head = line[:cut].rstrip()
            return f"<strong>{_inline(head)}</strong>{line[len(head):cut]}{_inline(line[cut:])}"   # keep the space
    return f"<strong>{_inline(line)}</strong>"


def to_html(text: str) -> str:
    lines = text.strip().split("\n")
    return "<br>".join([_headline(lines[0])] + [_inline(l) for l in lines[1:]])


def content(text: str) -> dict:
    return {"msgtype": "m.text", "body": text, "format": "org.matrix.custom.html", "formatted_body": to_html(text)}


def edit(event_id: str, text: str) -> dict:
    """Replaces the message `event_id` in place (m.replace); clients without edit support show the '* ' fallback."""
    new = content(text)
    return {**content(f"* {text}"), "m.new_content": new, "m.relates_to": {"rel_type": "m.replace", "event_id": event_id}}
