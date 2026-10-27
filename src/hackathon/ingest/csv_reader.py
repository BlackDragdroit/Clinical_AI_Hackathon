"""CSV ingestion."""

import csv
from pathlib import Path


def read_records(path: Path) -> list[dict[str, str]]:
    """Read a CSV file into a list of rows keyed by the header line.

    Values are returned as stripped strings; empty cells become empty strings.
    """
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return [
            {key.strip(): (value or "").strip() for key, value in row.items() if key is not None}
            for row in csv.DictReader(handle)
        ]
