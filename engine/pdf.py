"""PDFs: use the text layer when there is a real one (exact characters, ~0.1 s), otherwise render pages for OCR.

The text layer is rebuilt as Markdown: lines in larger type become headings, ruled tables become pipe tables,
so the result has the shape core/parse_doc.py expects. A page counts as image-only when it has fewer than
50 characters or the text is mostly broken glyphs ((cid:NN), U+FFFD, private-use characters).
"""
from __future__ import annotations

import io
import re
import statistics
import unicodedata

BROKEN = re.compile(r"\(cid:\d+\)|�|[-]")


def _clean(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").replace(" ", " ")
    return re.sub(r"^\s*(?:\(cid:\d+\)|[•▪◦●])\s*", "- ", s)          # bullet glyphs -> Markdown list item


def _inside(obj: dict, bbox: tuple) -> bool:
    x0, top, x1, bottom = bbox
    cx, cy = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
    return x0 <= cx <= x1 and top <= cy <= bottom


def text_layer_markdown(data: bytes) -> tuple[str | None, dict]:
    """Returns (markdown, info) or (None, info) when the PDF needs OCR."""
    import pdfplumber

    info: dict = {"pages": 0, "chars": 0, "tables": 0, "broken": 0}
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        info["pages"] = len(pdf.pages)
        for page in pdf.pages:
            tables = page.find_tables()
            bboxes = [t.bbox for t in tables]
            info["tables"] += len(tables)
            lines = page.extract_text_lines(return_chars=True)
            text_chars = sum(len(ln["text"]) for ln in lines)
            info["chars"] += text_chars
            info["broken"] += sum(len(BROKEN.findall(ln["text"])) for ln in lines)
            sizes = [c["size"] for ln in lines for c in ln["chars"] if c["text"].strip()]
            body = statistics.median(sizes) if sizes else 10
            items: list[tuple[float, str]] = []
            for ln in lines:
                if any(_inside(ln, bb) for bb in bboxes):
                    continue
                size = statistics.mean(c["size"] for c in ln["chars"]) if ln["chars"] else body
                txt = _clean(ln["text"]).strip()
                if not txt:
                    continue
                if size >= body * 1.45:
                    txt = "# " + txt
                elif size >= body * 1.15 and len(txt) < 80:
                    txt = "## " + txt
                items.append((ln["top"], txt))
            for t in tables:
                rows = [[_clean(c or "").replace("\n", " ").strip() for c in row] for row in t.extract()]
                rows = [r for r in rows if any(r)]
                if not rows:
                    continue
                md = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
                md += ["| " + " | ".join(r) + " |" for r in rows[1:]]
                items.append((t.bbox[1], "\n".join(md)))
            items.sort(key=lambda x: x[0])
            parts.append("\n".join(txt for _, txt in items))
    if info["chars"] < 50 * max(info["pages"], 1) or info["broken"] > 0.05 * max(info["chars"], 1):
        return None, info
    return "\n\n".join(parts).strip() + "\n", info


def render_pages(data: bytes, dpi: int = 200, max_pages: int = 4) -> list[bytes]:
    """PNG bytes per page, for OCR."""
    import pypdfium2 as pdfium

    out = []
    doc = pdfium.PdfDocument(data)
    for i in range(min(len(doc), max_pages)):
        img = doc[i].render(scale=dpi / 72).to_pil()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out.append(buf.getvalue())
    return out
