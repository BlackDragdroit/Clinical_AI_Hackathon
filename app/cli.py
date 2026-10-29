"""Run doctor commands without Matrix, e.g.
  python -m app.cli '!anfrage labor "Dr. Eva Brandl" eva.brandl@labor-kanal.example Patient/maria-beispiel Grund: Gerinnung vor Eingriff'
  python -m app.cli '!senden <id>'
"""
from __future__ import annotations

import sys

from app import commands, db, notify
from app.config import settings

if __name__ == "__main__":
    db.init_db()
    print(commands.handle(" ".join(sys.argv[1:]), settings.doctor_mxid))
    for m in notify.pending():
        print(f"[MATRIX] {m['text']}")
