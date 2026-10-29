"""The only place that imports core/. core/ uses flat imports, so it goes on sys.path here once.
Do not edit core/ from the app side; changes to the matcher or FHIR builder go through the MedEng + Biostat."""
from __future__ import annotations

import sys
from pathlib import Path

_CORE = str(Path(__file__).resolve().parent.parent / "core")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from fs_matcher import Person, norm_tokens  # noqa: E402
from intake import IntakeResult, run_intake  # noqa: E402
from parse_doc import parse_markdown  # noqa: E402

__all__ = ["IntakeResult", "Person", "norm_tokens", "parse_markdown", "run_intake"]
