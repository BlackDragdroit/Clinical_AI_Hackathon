"""Write extracted fields back as a document in the scenario's Markdown shape, so core/ parses it unchanged.

Used when the input was not Markdown (PDF text layer, OCR, model fallback) and after the sender's read-back.
Only values that were grounded in the source (or confirmed by the sender) are passed in.
"""
from __future__ import annotations


def _cell(s: str | None) -> str:
    return (s or "").replace("|", "/").replace("\n", " ").strip()


def render(fields: dict) -> str:
    """fields: org, title, patient_name, patient_dob, sample_taken, reported, rows[{test,result,unit,
    reference_range,loinc}], body (free text), signed_label + signed_by (e.g. 'Validated by', 'Dr. Eva Brandl')."""
    out = []
    if fields.get("org") or fields.get("title"):
        out.append(f"# {_cell(fields.get('org')) or 'Dokument'}: {_cell(fields.get('title')) or 'Befund'}")
        out.append("")
    if fields.get("patient_name"):
        out.append(f"Patient: {_cell(fields['patient_name'])}" + (f", born {_cell(fields['patient_dob'])}" if fields.get("patient_dob") else ""))
    for key, label in (("sample_taken", "Sample taken"), ("reported", "Reported"), ("stay", "Stay"), ("reason", "Reason")):
        if fields.get(key):
            out.append(f"{label}: {_cell(fields[key])}")
    rows = fields.get("rows") or []
    if rows:
        out += ["", "| Test | Result | Unit | Reference range | LOINC code |", "|---|---|---|---|---|"]
        for r in rows:
            out.append("| " + " | ".join(_cell(r.get(k)) for k in ("test", "result", "unit", "reference_range", "loinc")) + " |")
    if fields.get("body"):
        out += ["", fields["body"].strip()]
    if fields.get("signed_by"):
        out += ["", f"{fields.get('signed_label') or 'Signed by'}: {_cell(fields['signed_by'])}"]
    return "\n".join(out).strip() + "\n"
