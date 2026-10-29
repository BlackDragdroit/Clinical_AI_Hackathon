"""Run the core on jury-style documents and compare with the expected decision. Owner: Biostat (docs: MedEng).

metrics/jury_docs/manifest.json lists cases:
  {"file": "...md" (relative to repo root), "requested": ["Maria Beispiel", "1961-03-12"],
   "typed": ["Maria Beispiel", "12.03.1961"], "expected": "file" | "review" | "reject", "why": "..."}

The safety number is wrongly filed (expected != file but we filed). Report it with an exact
binomial / rule-of-three upper bound, not a bootstrap: with 0 events a bootstrap CI collapses to [0, 0].
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.core_bridge import Person, run_intake

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "metrics" / "jury_docs" / "manifest.json"


def main() -> None:
    cases = json.loads(MANIFEST.read_text())
    confusion: Counter = Counter()
    for c in cases:
        r = run_intake((ROOT / c["file"]).read_text(encoding="utf-8"), Person.from_full(*c["requested"]),
                       Person.from_full(*c["typed"]), "Test Sender", "", "test", "Patient/test")
        confusion[(c["expected"], r.decision)] += 1
        flag = "" if r.decision == c["expected"] else "   <-- MISMATCH"
        print(f"{c['file']:55s} expected={c['expected']:6s} got={r.decision:6s}{flag}")
    wrongly_filed = sum(n for (exp, got), n in confusion.items() if got == "file" and exp != "file")
    print(f"\nn={len(cases)}  wrongly filed={wrongly_filed}  confusion={dict(confusion)}")
    # TODO(Biostat): exact CIs (Clopper–Pearson) for false-file / false-reject, write a section into METRICS.md


if __name__ == "__main__":
    main()
