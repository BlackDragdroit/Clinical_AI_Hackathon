"""The engine's only door into core/ (flat imports, so core/ goes on sys.path once)."""
from __future__ import annotations

import sys
from pathlib import Path

_CORE = str(Path(__file__).resolve().parent.parent / "core")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from fs_matcher import DEFAULT, Person, Weights, compare, norm_tokens, parse_dob, split_name  # noqa: E402
from loinc import KNOWN, is_valid, resolve  # noqa: E402
from parse_doc import ParsedDoc, interpret, parse_datetime, parse_markdown  # noqa: E402

_W = Path(_CORE) / "weights.json"
WEIGHTS = Weights.load(str(_W)) if _W.exists() else DEFAULT

__all__ = ["KNOWN", "WEIGHTS", "ParsedDoc", "Person", "compare", "interpret", "is_valid", "norm_tokens",
           "parse_datetime", "parse_dob", "parse_markdown", "resolve", "split_name"]
