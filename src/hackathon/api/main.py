"""HTTP API: ``GET /health`` and ``POST /convert``."""

import csv
import io
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile

from hackathon.pipeline import convert_records

app = FastAPI(title="Clinical AI Hackathon API")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@app.post("/convert")
async def convert(file: Annotated[UploadFile, File()]) -> dict:
    """Convert an uploaded CSV to a FHIR transaction Bundle.

    Returns ``{"bundle": <Bundle JSON>, "validation": {"ok": bool, "errors": [str]}}``.
    """
    try:
        text = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    records = [
        {k.strip(): (v or "").strip() for k, v in row.items() if k is not None}
        for row in csv.DictReader(io.StringIO(text, newline=""))
    ]
    bundle, result = convert_records(records)
    return {
        "bundle": bundle.model_dump(mode="json", exclude_none=True),
        "validation": {"ok": result.ok, "errors": result.errors},
    }
