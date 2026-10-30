"""Append-only, hash-chained audit log. CONTRACT: everyone calls `audit.log(...)`. Owner: MedEng.

Every entry answers who (actor), what (event + details), when (ts). Each hash covers the previous
hash, so editing or deleting a row breaks `verify_chain()`.

Details must never contain the name or birth date of a patient other than the requested one (M3).

Below the contract: read-only helpers for the /audit page (first_broken, describe, actor_label,
view). They only read; nothing there writes to the log.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import db, i18n
from app.config import settings
from app.misdelivery import misdelivery_label

# the six steps the track measures (README "Audit coverage")
REQUIRED = ("request_sent", "link_opened", "identity_checked", "answer_sent", "answer_filed", "misdelivery_caught")
# extra events we log for need-to-know, review decisions, blocked links and the engine's read-back
EXTRA = ("request_drafted", "request_parsed", "patient_revealed", "review_requested", "review_decided",
         "request_blocked", "readback_shown", "readback_confirmed")
EVENTS = REQUIRED + EXTRA

GENESIS = "0" * 64


def _digest(prev_hash: str, ts: str, event: str, request_id: str | None, actor: str, details: str) -> str:
    return hashlib.sha256("|".join([prev_hash, ts, event, request_id or "", actor, details]).encode()).hexdigest()


def log(event: str, request_id: str | None, actor: str, details: dict) -> dict:
    """actor examples: '@lena.hofer:klinikum.example', 'link ip=1.2.3.4', 'eid:<pseudonym> Eva Brandl',
    'system:befundbruecke'. Unknown event names raise, so a typo cannot silently drop a metric."""
    if event not in EVENTS:
        raise ValueError(f"unknown audit event {event!r}")
    ts = db.now()
    det = json.dumps(details, ensure_ascii=False, sort_keys=True)
    with db.conn() as c:
        c.execute("BEGIN IMMEDIATE")
        last = c.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else GENESIS
        h = _digest(prev, ts, event, request_id, actor, det)
        c.execute("INSERT INTO audit (ts, event, request_id, actor, details, prev_hash, hash) VALUES (?,?,?,?,?,?,?)",
                  (ts, event, request_id, actor, det, prev, h))
        c.execute("COMMIT")
    return {"ts": ts, "event": event, "request_id": request_id, "actor": actor, "details": details, "hash": h}


def entries(request_id: str | None = None) -> list[dict]:
    if request_id:
        rows = db.query("SELECT * FROM audit WHERE request_id = ? ORDER BY seq", (request_id,))
    else:
        rows = db.query("SELECT * FROM audit ORDER BY seq")
    for r in rows:
        try:
            r["details"] = json.loads(r["details"])
        except (TypeError, ValueError):   # a tampered row must still show up (and fail verify_chain)
            r["details"] = {"_raw": r["details"]}
    return rows


def verify_chain() -> bool:
    prev = GENESIS
    for r in db.query("SELECT * FROM audit ORDER BY seq"):
        if r["prev_hash"] != prev or r["hash"] != _digest(prev, r["ts"], r["event"], r["request_id"], r["actor"], r["details"]):
            return False
        prev = r["hash"]
    return True


def coverage(request_id: str | None = None) -> dict[str, bool]:
    seen = {e["event"] for e in entries(request_id)}
    return {ev: ev in seen for ev in REQUIRED}


# ---------------------------------------------------------------------------------------------------
# Page helpers for /audit (read-only). Owner: MedEng.

# events another branch adds (Matrix free-text parsing + read-back); described here already so the
# page speaks about them the moment that branch lands
LATER = ("request_parsed", "readback_shown", "readback_confirmed")
MISDELIVERY_CODES = ("M1", "M2", "M3")
STATUSES = ("draft", "sent", "opened", "identified", "answered", "filed", "review", "rejected", "discarded", "blocked")
_STATUS_TONE = {"filed": "ok", "review": "warn", "rejected": "bad", "blocked": "bad", "discarded": "muted"}
DESIGNS = {"standard": "/audit", "apple": "/audit/apple"}   # two looks of the same page, same data
_EN_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

try:
    TZ, TZ_NAME = ZoneInfo("Europe/Vienna"), "Europe/Vienna"
except ZoneInfoNotFoundError:   # Windows without the tzdata package: show UTC rather than crash
    TZ, TZ_NAME = timezone.utc, "UTC"


def _check_rows() -> list[tuple[int, bool]]:
    """(seq, ok) for every row, by the same rule as verify_chain()."""
    out, prev = [], GENESIS
    for r in db.query("SELECT * FROM audit ORDER BY seq"):
        ok = r["prev_hash"] == prev and r["hash"] == _digest(prev, r["ts"], r["event"], r["request_id"], r["actor"],
                                                             r["details"])
        out.append((r["seq"], ok))
        prev = r["hash"]
    return out


def first_broken() -> int | None:
    """seq of the first row whose prev_hash or hash does not verify; None when the chain is intact."""
    return next((seq for seq, ok in _check_rows() if not ok), None)


def head() -> str | None:
    """Hash of the newest row (the value to note down or anchor elsewhere); None for an empty log."""
    rows = db.query("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1")
    return rows[0]["hash"] if rows else None


def local_time(ts: str) -> datetime | None:
    """Stored UTC ISO -> Europe/Vienna (None if unparseable)."""
    try:
        dt = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(TZ)


def fmt_date(dt: datetime | None, lang: str) -> str:
    if not dt:
        return "?"
    if i18n.norm_lang(lang) == "en":
        return f"{dt.day} {_EN_MONTHS[dt.month - 1]} {dt.year}"
    return dt.strftime("%d.%m.%Y")


def actor_label(actor: str, lang: str = i18n.DEFAULT) -> str:
    """Who, for the main line: 'Dr. Hofer', 'Link (IP 1.2.3.4)', 'eID: Eva Brandl', 'System'.
    The eID pseudonym and the full Matrix ID stay in the raw row for auditors."""
    actor = (actor or "").strip()
    if actor.startswith("@") and ":" in actor:
        if actor == settings.doctor_mxid:
            parts = settings.doctor_name.split()
            titles = [p for p in parts[:-1] if p.endswith(".")]
            return " ".join(titles + parts[-1:]) if parts else actor
        local = actor[1:].split(":", 1)[0]
        return " ".join(p.capitalize() for p in local.replace("_", ".").split(".") if p) or actor
    if actor.startswith("link ip="):
        return i18n.t("audit.actor.link", lang, ip=actor.removeprefix("link ip=") or "?")
    if actor.startswith("eid:"):
        _, _, name = actor.partition(" ")
        return i18n.t("audit.actor.eid", lang, name=name.strip() or "?")
    if actor.startswith("system:"):
        return i18n.t("audit.actor.system", lang)
    return actor or "?"


def _known(prefix: str, code: object, lang: str) -> str:
    """Catalogue text for a code, or the code itself when the catalogue has none."""
    key = f"{prefix}.{code}"
    return i18n.t(key, lang) if key in i18n.MESSAGES else str(code)


def _size(n: object, lang: str) -> str:
    if not isinstance(n, int):
        return "?"
    if n < 1024:
        return f"{n} B"
    kb = f"{n / 1024:.1f}"
    return f"{kb.replace('.', ',') if i18n.norm_lang(lang) == 'de' else kb} kB"


def _describe(event: str, d: dict, lang: str) -> str:
    t = i18n.t
    if event == "request_drafted":
        text = t("audit.ev.request_drafted", lang, doc=_known("audit.doc", d.get("doc_type"), lang),
                 to=d.get("to", "?"), contact=d.get("contact", "?"))
        n = len(d.get("lint_warnings") or [])
        return text + (t("audit.ev.lint_warnings", lang, n=n) if n else "")
    if event == "request_sent":
        text = t("audit.ev.request_sent", lang, channel=_known("audit.channel", d.get("channel"), lang),
                 to=d.get("to", "?"), contact=d.get("contact", "?"))
        return text + (t("audit.ev.ttl", lang, h=d["ttl_h"]) if d.get("ttl_h") else "")
    if event == "link_opened":
        return t("audit.ev.link_opened" if d.get("status", "sent") == "sent" else "audit.ev.link_reopened", lang)
    if event == "identity_checked":
        if d.get("result") == "OK":
            return t("audit.ev.identity_ok", lang, method=_known("audit.method", d.get("method"), lang),
                     loa=_known("audit.loa", d.get("loa"), lang))
        return t("audit.ev.identity_failed", lang, attempt=d.get("attempt", "?"))
    if event == "misdelivery_caught":
        code = d.get("type")
        label = misdelivery_label(code, lang) if code in MISDELIVERY_CODES else t("audit.ev.misdelivery_other", lang,
                                                                                   code=code)
        if code == "M3":
            return t("audit.ev.misdelivery_m3", lang, label=label)
        if d.get("verified") or d.get("expected"):
            return t("audit.ev.misdelivery_names", lang, label=label, verified=d.get("verified", "?"),
                     expected=d.get("expected", "?"))
        return label
    if event == "patient_revealed":
        return t("audit.ev.patient_revealed", lang)
    if event == "answer_sent":
        return t("audit.ev.answer_sent", lang, filename=d.get("filename", "?"), size=_size(d.get("bytes"), lang))
    if event == "answer_filed":
        n = len(d.get("resources") or [])
        text = t("audit.ev.answer_filed_one" if n == 1 else "audit.ev.answer_filed", lang, n=n)
        return text + (t("audit.ev.task_completed", lang, task=d["task"]) if d.get("task") else "")
    if event == "review_requested":
        return t("audit.ev.review_requested", lang)
    if event == "review_decided":
        return t("audit.ev.review_file" if d.get("decision") == "ablegen" else "audit.ev.review_discard", lang)
    if event == "request_blocked":
        return t("audit.ev.request_blocked", lang, n=d.get("attempts", "?"))
    if event == "request_parsed":
        if d.get("doc_type") and d.get("to"):
            return t("audit.ev.request_parsed_doc", lang, doc=_known("audit.doc", d["doc_type"], lang), to=d["to"])
        return t("audit.ev.request_parsed", lang)
    if event in ("readback_shown", "readback_confirmed"):
        return t(f"audit.ev.{event}", lang)
    return t("audit.ev.unknown", lang, event=event)


def describe(entry: dict, lang: str = i18n.DEFAULT) -> str:
    """One plain sentence for an audit entry, German or English. Never raises: an unknown event or
    odd details give a generic sentence, so a new event can't break the audit page."""
    event = str(entry.get("event") or "?")
    d = entry.get("details") if isinstance(entry.get("details"), dict) else {}
    try:
        return _describe(event, d, lang)
    except Exception:   # noqa: BLE001 - the audit page must render whatever is in the log
        return i18n.t("audit.ev.unknown", lang, event=event)


def note(entry: dict, lang: str = i18n.DEFAULT) -> str | None:
    """Optional second line: what was filed, or that nothing was revealed."""
    ev = entry.get("event")
    d = entry.get("details") if isinstance(entry.get("details"), dict) else {}
    try:
        if ev == "answer_filed" and d.get("resources"):
            types = Counter(str(r).split("/")[0] for r in d["resources"])
            return " · ".join(f"{n}× {k}" if n > 1 else k for k, n in types.items())
        if ev == "identity_checked" and d.get("result") != "OK":
            return i18n.t("audit.note.nothing_revealed", lang)
        if ev == "misdelivery_caught" and d.get("type") == "M3":
            return i18n.t("audit.note.m3_scores", lang)
        if ev == "misdelivery_caught":
            return i18n.t("audit.note.doctor_alerted", lang, doctor=actor_label(settings.doctor_mxid, lang))
    except Exception:   # noqa: BLE001
        return None
    return None


def outcome(entry: dict) -> str:
    """Tone for colour + icon: ok (filed), warn (review), bad (identity failed), alert (misdelivery),
    pass (identity confirmed, decision taken), info (everything else)."""
    ev = entry.get("event")
    d = entry.get("details") if isinstance(entry.get("details"), dict) else {}
    if ev == "answer_filed":
        return "ok"
    if ev == "review_requested":
        return "warn"
    if ev == "misdelivery_caught":
        return "alert"
    if ev == "identity_checked":
        return "pass" if d.get("result") == "OK" else "bad"
    if ev in ("readback_confirmed", "review_decided"):
        return "pass"
    return "info"


def _href(request_id: str | None, lang: str | None, path: str = "/audit") -> str:
    params = {k: v for k, v in (("request_id", request_id), ("lang", lang)) if v}
    return f"{path}?{urlencode(params)}" if params else path


def view(request_id: str | None = None, lang: str = i18n.DEFAULT, base: str = "/audit") -> dict:
    """Everything the /audit page shows, already privacy-filtered: patients by reference only, contacts
    masked, no answer content. M3 entries hold only scores, so nothing about the other patient is here.
    `base` is the page the filter and language links point to (/audit, or the /audit/apple design)."""
    from app.requests_service import mask   # late import: requests_service imports this module

    lang = i18n.norm_lang(lang)
    request_id = (request_id or "").strip() or None
    checks = _check_rows()
    broken = {seq for seq, ok in checks if not ok}
    all_entries = entries()
    by_request: dict[str, list[dict]] = {}
    for e in all_entries:
        if e["request_id"]:
            by_request.setdefault(e["request_id"], []).append(e)
    scope = by_request.get(request_id, []) if request_id else all_entries

    rows = []
    for e in scope:
        dt = local_time(e["ts"])
        rows.append({
            "seq": e["seq"], "event": e["event"], "request_id": e["request_id"], "ts": e["ts"],
            "iso_local": dt.isoformat() if dt else e["ts"], "day": fmt_date(dt, lang),
            "time": dt.strftime("%H:%M:%S") if dt else e["ts"],
            "who": actor_label(e["actor"], lang), "actor": e["actor"],
            "what": describe(e, lang), "note": note(e, lang), "tone": outcome(e),
            "details_json": json.dumps(e["details"], ensure_ascii=False, indent=2, sort_keys=True),
            "hash": e["hash"], "prev_hash": e["prev_hash"], "broken": e["seq"] in broken,
            "href": _href(e["request_id"], lang, base) if e["request_id"] else None,
        })

    requests = []
    for r in db.query("SELECT * FROM requests ORDER BY created_at, rowid"):
        evs = by_request.get(r["id"], [])
        seen = {e["event"] for e in evs}
        created = local_time(r["created_at"])
        requests.append({
            "id": r["id"], "doc": _known("audit.doc", r["doc_type"], lang), "expected_name": r["expected_name"],
            "contact": mask(r["contact"]), "channel": _known("audit.channel", r["contact_kind"], lang),
            "patient_ref": r["patient_ref"], "status": r["status"],
            "status_label": _known("audit.status", r["status"], lang),
            "status_tone": _STATUS_TONE.get(r["status"], "info"),
            "covered": sum(ev in seen for ev in REQUIRED),
            "misdelivery": sorted({str(e["details"].get("type")) for e in evs if e["event"] == "misdelivery_caught"}),
            "created": f"{fmt_date(created, lang)} {created:%H:%M}" if created else r["created_at"],
            "href": _href(r["id"], lang, base), "selected": r["id"] == request_id,
        })

    seen = {e["event"] for e in scope}
    caught: dict[str, list[dict]] = {code: [] for code in MISDELIVERY_CODES}
    for row, e in zip(rows, scope):
        code = e["details"].get("type") if e["event"] == "misdelivery_caught" else None
        if code in caught:
            caught[code].append({"day": row["day"], "time": row["time"], "request_id": e["request_id"],
                                 "href": row["href"], "seq": e["seq"]})

    last = head()
    return {
        "lang": lang, "request_id": request_id, "tz": TZ_NAME,
        "chain_ok": not broken, "first_broken": min(broken) if broken else None, "broken_count": len(broken),
        "entry_count": len(checks), "scope_count": len(scope), "head": last, "head_short": (last or "")[:12],
        "coverage": {ev: ev in seen for ev in REQUIRED}, "covered": sum(ev in seen for ev in REQUIRED),
        "entries": rows, "requests": requests, "misdelivery": caught,
        "known_request": request_id is None or request_id in by_request or any(r["selected"] for r in requests),
        "links": {"all": _href(None, lang, base), "json": _href(request_id, None, "/audit.json"),
                  "toggle": _href(request_id, i18n.other_lang(lang), base),
                  # same filter and language, other design; and one link per language for a segmented control
                  "design": {name: _href(request_id, lang, path) for name, path in DESIGNS.items()},
                  "lang": {code: _href(request_id, code, base) for code in i18n.LANGS}},
        # every row of the whole chain (seq, verifies?), for the chain strip on /audit/apple
        "chain": [{"seq": seq, "ok": ok} for seq, ok in checks],
    }
