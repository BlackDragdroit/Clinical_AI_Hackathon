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


# What Element shows is minimal and has no emoji: lines shrink to what Dr. Hofer needs, a leading emoji and the ●○
# dots give way to the status colour. With CHAT_IMAGES=1 the bot uploads app/chat_icons.py's drawn icons and bridge
# images and fills these maps; that needs a homeserver serving inline media without a login (Synapse's
# enable_authenticated_media: false), because an <img> in message HTML cannot send one. The plain body is unchanged.
ICONS: dict[str, str] = {}                  # icon name -> mxc URI
BRIDGES: dict[tuple[int, str], str] = {}    # (stations done, tone) -> mxc URI
_EMOJI = {"✅": "check", "⛔": "x", "⚠️": "warn", "🔍": "search", "🔒": "lock"}
_DOTS = re.compile(r"^([●○]{5})\s+(.*?)(?: – .*?)?((?: · \d\d:\d\d)?)$")
_GREY = "#5d6b76"
_COLOR = {"check": "#17693f", "x": "#b0241c", "warn": "#9a6200", "search": "#1f5f8b", "lock": "#b0241c",
          "ok": "#17693f", "bad": "#b0241c", "accent": "#1f5f8b"}   # icon names and tones share "warn"


def _tone(phase: str) -> str:
    if phase.startswith(("Nicht abgelegt", "Falsche Person", "Gesperrt", "Verworfen",
                         "Not filed", "Wrong person", "Blocked", "Discarded")):
        return "bad"
    if phase.startswith(("Abgelegt", "Filed")):
        return "ok"
    return "warn" if "prüf" in phase or "review" in phase else "accent"


def _compact(line: str) -> str:
    """Only what Dr. Hofer needs: a status line up to its first clause, an alert up to its first sentence."""
    if m := _DOTS.match(line):
        return f"{m.group(1)} {m.group(2)}{m.group(3)}"
    if line.startswith(tuple(_EMOJI)) and ". " in line:
        cut = line.index(". ") + 1
        links = [m.group(0).rstrip(".,;") for m in _URL.finditer(line[cut:])]   # links always stay
        return " ".join([line[:cut]] + links)
    return line


def _img(uri: str, alt: str) -> str:
    return f'<img src="{uri}" alt="{html.escape(alt)}" title="{html.escape(alt)}" height="18" data-mx-emoticon>'


def _rich(line_html: str, plain: str) -> str:
    for emoji, name in _EMOJI.items():
        for lead in ("", "<strong>"):
            if line_html.startswith(lead + emoji):
                rest = line_html[len(lead + emoji):].lstrip()
                line_html = (lead + _img(ICONS[name], name) + " " + rest if name in ICONS
                             else f'<font color="{_COLOR[name]}">{lead}{rest}</font>')
    if m := _DOTS.match(plain):
        key = (m.group(1).count("●"), _tone(m.group(2)))
        line_html = (line_html.replace(m.group(1), _img(BRIDGES[key], f"{key[0]}/5"), 1) if key in BRIDGES
                     else f'<font color="{_COLOR[key[1]]}">{line_html.replace(m.group(1), "", 1).lstrip()}</font>')
    if plain.startswith(("Verstanden aus", "Understood from")):
        line_html = f'<font color="{_GREY}">{line_html}</font>'
    return line_html


def to_html(text: str) -> str:
    lines = [_compact(l) for l in text.strip().split("\n")]
    out = [_headline(lines[0])] + [_inline(l) for l in lines[1:]]
    return "<br>".join(_rich(h, p) for h, p in zip(out, lines))


def content(text: str, reply_to: str | None = None) -> dict:
    c = {"msgtype": "m.text", "body": text, "format": "org.matrix.custom.html", "formatted_body": to_html(text)}
    if reply_to:     # Element shows the message as a reply to `reply_to`, with a link to jump there
        c["m.relates_to"] = {"m.in_reply_to": {"event_id": reply_to}}
    return c


def edit(event_id: str, text: str) -> dict:
    """Replaces the message `event_id` in place (m.replace); clients without edit support show the '* ' fallback."""
    new = content(text)
    return {**content(f"* {text}"), "m.new_content": new, "m.relates_to": {"rel_type": "m.replace", "event_id": event_id}}
