"""Small PNGs the bot shows inline in Matrix instead of emoji: outline icons (Heroicons-style, 24-grid, 1.6 stroke)
and the request's bridge (five stations, n done) in the design system's colours. Drawn with Pillow at 4x, then
downsampled; the bot uploads them once at start (app/bot.py) and app/matrix_format.py references the mxc URIs."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

INK = {"ok": "#17693f", "warn": "#9a6200", "bad": "#b0241c", "accent": "#1f5f8b"}
LINE, PAPER = "#cbd3d9", "#ffffff"
S = 4                       # supersampling


def _png(img: Image.Image, size: tuple[int, int]) -> bytes:
    buf = io.BytesIO()
    img.resize(size, Image.LANCZOS).save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _stroke(d: ImageDraw.ImageDraw, pts: list[tuple[float, float]], color: str, w: float = 1.6) -> None:
    """A polyline on the 24-grid with round joins and caps."""
    k, r = 4 * S, w * 4 * S / 2
    xy = [(x * k, y * k) for x, y in pts]
    d.line(xy, fill=color, width=round(2 * r), joint="curve")
    for x, y in (xy[0], xy[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)


def _circle(d: ImageDraw.ImageDraw, cx: float, cy: float, rad: float, color: str, w: float = 1.6) -> None:
    k = 4 * S
    d.ellipse(((cx - rad) * k, (cy - rad) * k, (cx + rad) * k, (cy + rad) * k), outline=color, width=round(w * k))


def icon(name: str) -> bytes:
    """40x40 PNG (shown at 18px): check (filed), x (not filed), warn, search (review), lock (blocked)."""
    img = Image.new("RGBA", (24 * 4 * S, 24 * 4 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = {"check": INK["ok"], "x": INK["bad"], "warn": INK["warn"], "search": INK["accent"], "lock": INK["bad"]}[name]
    if name in ("check", "x"):
        _circle(d, 12, 12, 9.4, color)
        if name == "check":
            _stroke(d, [(8.3, 12.4), (10.9, 15), (15.9, 9.4)], color)
        else:
            _stroke(d, [(9.3, 9.3), (14.7, 14.7)], color)
            _stroke(d, [(14.7, 9.3), (9.3, 14.7)], color)
    elif name == "warn":
        _stroke(d, [(12, 3.6), (21, 19.6), (3, 19.6), (12, 3.6)], color)
        _stroke(d, [(12, 9.4), (12, 13.6)], color)
        _stroke(d, [(12, 16.6), (12, 16.7)], color, 2)
    elif name == "search":
        _circle(d, 10.6, 10.6, 6.2, color)
        _stroke(d, [(15.2, 15.2), (20.2, 20.2)], color)
    elif name == "lock":
        _stroke(d, [(8, 10.8), (8, 8), (8.6, 6.1), (10, 4.8), (12, 4.3), (14, 4.8), (15.4, 6.1), (16, 8), (16, 10.8)], color)
        _stroke(d, [(5.2, 11), (18.8, 11), (18.8, 20.4), (5.2, 20.4), (5.2, 11)], color)
    return _png(img, (40, 40))


def bridge(done: int, tone: str) -> bytes:
    """264x36 PNG (shown at 18px high): the arch with `done` of five stations reached, in `tone`."""
    W, H, pad = 132 * 2 * S, 18 * 2 * S, 7 * 2 * S
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y0, y1 = H * .78, H * .16                       # ends low, apex high: a quadratic arch, x linear in t
    pt = lambda t: (pad + (W - 2 * pad) * t, (1 - t) ** 2 * y0 + 2 * (1 - t) * t * y1 + t ** 2 * y0)   # noqa: E731
    w = round(2.2 * 2 * S)
    curve = [pt(i / 60) for i in range(61)]
    d.line(curve, fill=LINE, width=w, joint="curve")
    if done > 1:
        d.line([pt(i / 60) for i in range(int(60 * (done - 1) / 4) + 1)], fill=INK[tone], width=w, joint="curve")
    r = 4.2 * 2 * S
    for i in range(5):
        x, y = pt(i / 4)
        if i < done:
            d.ellipse((x - r, y - r, x + r, y + r), fill=INK[tone])
        else:
            d.ellipse((x - r, y - r, x + r, y + r), fill=PAPER, outline=LINE, width=round(1.6 * 2 * S))
    return _png(img, (264, 36))


ICON_NAMES = ("check", "x", "warn", "search", "lock")
TONES = tuple(INK)
