"""Render a scenario-shaped Markdown document as a PDF, a fax-quality scan and a phone photo.

The correct answer is the Markdown we started from, so every rendering has an exact ground truth.
  pdf    reportlab, real text layer, ruled results table (like a lab system's export)
  scan   200 dpi, grey, slight rotation, blur, speckle noise, JPEG artefacts (fax/scanner)
  photo  perspective warp, uneven lighting, shadow, blur, JPEG (phone on a desk)
"""
from __future__ import annotations

import io
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def md_to_pdf(md: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    st = getSampleStyleSheet()
    font = _unicode_font()
    if font:                                   # built-in Helvetica cannot encode ş, ć, ž (names become "Ayne")
        for name in ("BodyText", "Heading1", "Heading3"):
            st[name].fontName = font
    body = st["BodyText"]
    flow, table = [], []

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def flush():
        if table:
            t = Table(table, repeatRows=1)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9),
                                   ("FONTNAME", (0, 0), (-1, -1), font or "Helvetica"),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke)]))
            flow.extend([t, Spacer(1, 0.3 * cm)])
            table.clear()

    for line in md.splitlines():
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                table.append(cells)
            continue
        flush()
        if not s:
            flow.append(Spacer(1, 0.2 * cm))
        elif s.startswith("# "):
            flow.append(Paragraph(esc(s[2:]), st["Heading1"]))
        elif s.startswith("## "):
            flow.append(Paragraph(esc(s[3:]), st["Heading3"]))
        elif s.startswith("- "):
            flow.append(Paragraph("• " + esc(s[2:]), body))
        else:
            flow.append(Paragraph(esc(s), body))
    flush()
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm).build(flow)
    return buf.getvalue()


def _unicode_font() -> str | None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for path in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/Library/Fonts/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if Path(path).exists():
            if "Uni" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("Uni", path))
            return "Uni"
    return None


def pdf_to_image(pdf: bytes, dpi: int = 200) -> Image.Image:
    import pypdfium2 as pdfium
    return pdfium.PdfDocument(pdf)[0].render(scale=dpi / 72).to_pil().convert("RGB")


def _jpeg(img: Image.Image, q: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=q)
    return buf.getvalue()


def scan(pdf: bytes, seed: int = 0) -> bytes:
    rng = random.Random(seed)
    img = pdf_to_image(pdf, 200).convert("L")
    img = img.rotate(rng.uniform(-1.8, 1.8), expand=True, fillcolor=255, resample=Image.BICUBIC)
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 0.9)))
    px = img.load()
    w, h = img.size
    for _ in range(int(w * h * 0.0015)):
        px[rng.randrange(w), rng.randrange(h)] = rng.choice((0, 255))
    return _jpeg(img.convert("RGB"), rng.randint(45, 70))


def photo(pdf: bytes, seed: int = 0) -> bytes:
    rng = random.Random(seed)
    page = pdf_to_image(pdf, 170)
    w, h = page.size
    d = lambda: rng.uniform(0.02, 0.07)
    # perspective: map page corners to a slightly skewed quad on a desk-coloured canvas
    canvas = Image.new("RGB", (int(w * 1.15), int(h * 1.12)), (rng.randint(90, 140), rng.randint(80, 120), rng.randint(60, 100)))
    quad = [(w * d(), h * d()), (w * (1 - d()), h * d()), (w * (1 - d()), h * (1 - d())), (w * d(), h * (1 - d()))]
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    coeffs = _perspective(quad, src)
    warped = page.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC, fillcolor=(0, 0, 0))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(quad, fill=255)
    canvas.paste(warped, (int(w * 0.07), int(h * 0.05)), mask)
    # lighting gradient + a soft shadow
    grad = Image.linear_gradient("L").resize(canvas.size).rotate(rng.uniform(0, 360))
    canvas = Image.composite(canvas, Image.new("RGB", canvas.size, (40, 40, 40)), grad.point(lambda v: 170 + v // 3))
    canvas = canvas.filter(ImageFilter.GaussianBlur(rng.uniform(0.6, 1.3)))
    return _jpeg(canvas, rng.randint(60, 82))


def _perspective(dst: list[tuple[float, float]], src: list[tuple[float, float]]) -> list[float]:
    """Coefficients for PIL's PERSPECTIVE transform (output point -> input point)."""
    import numpy as np
    a, b = [], []
    for (x, y), (u, v) in zip(dst, src):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    return list(np.linalg.solve(np.array(a, float), np.array(b, float)))
