"""Plain-text bot messages -> Matrix HTML (formatted_body). Owner: SWE 1.

Messages stay plain text everywhere (CLI, outbox, tests); the bot adds HTML on the way out:
first line bold (it says what happened), URLs clickable, `!commands` as code so they can be
copied exactly. Only tags from the Matrix spec's recommended HTML subset are used.
"""
from __future__ import annotations

import html
import re

_URL = re.compile(r"https?://[^\s<>()]+")
_CMD = re.compile(r"(?<![\w/])(![a-zäöü]+(?: [a-z0-9]{6,})?)")


def _inline(line: str) -> str:
    out, pos = [], 0
    for m in _URL.finditer(line):
        out.append(_cmd(html.escape(line[pos:m.start()])))
        url = m.group(0).rstrip(".,;")
        out.append(f'<a href="{html.escape(url)}">{html.escape(_label(url))}</a>')
        pos = m.start() + len(url)
    out.append(_cmd(html.escape(line[pos:])))
    return "".join(out)


def _cmd(escaped: str) -> str:
    return _CMD.sub(r"<code>\1</code>", escaped)


def _label(url: str) -> str:
    """'http://host/fhir/DiagnosticReport/9ae0…' -> 'DiagnosticReport/9ae0…' (readable, still unique)."""
    m = re.search(r"/fhir/([A-Za-z]+/[^/]+)$", url)
    return m.group(1) if m else url


def to_html(text: str) -> str:
    lines = text.strip().split("\n")
    head, rest = lines[0], lines[1:]
    parts = [f"<strong>{_inline(head)}</strong>"] + [_inline(l) for l in rest]
    return "<br>".join(parts)


def content(text: str) -> dict:
    return {"msgtype": "m.text", "body": text, "format": "org.matrix.custom.html", "formatted_body": to_html(text)}
