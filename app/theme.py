"""Light / dark / system appearance for clinic pages, chosen like the language (app/i18n.py). Owner: MedEng.

Order: `?theme=light|dark|system`, the `theme` cookie, else "system" (follow the operating system).
Pages put `data-theme="{{ theme }}"` on <html> for light/dark; their CSS keeps the
`prefers-color-scheme` rules for "system" and adds `:root[data-theme=…]` overrides.
"""
from __future__ import annotations

from typing import Any

THEMES = ("light", "dark", "system")
DEFAULT = "system"
COOKIE = "theme"


def norm_theme(theme: str | None) -> str:
    t = (theme or "").strip().lower()
    return t if t in THEMES else DEFAULT


def resolve_theme(request: Any) -> str:
    q = request.query_params.get("theme")
    if q:
        return norm_theme(q)
    return norm_theme(request.cookies.get(COOKIE))


def remember(response: Any, theme: str) -> None:
    response.set_cookie(COOKIE, norm_theme(theme), max_age=365 * 24 * 3600, samesite="lax")


def links(request: Any) -> dict[str, str]:
    """The current URL with each theme, keeping request_id / lang."""
    out = {}
    for t in THEMES:
        url = request.url.include_query_params(theme=t)
        out[t] = f"{url.path}?{url.query}"
    return out
