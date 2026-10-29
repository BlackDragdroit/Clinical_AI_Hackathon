"""Hard rule 1: emails/SMS contain no patient name, birth date or document type."""
import re

import pytest

from app.delivery.base import MESSAGE_TEMPLATES, render_message

FORBIDDEN = [
    "maria", "beispiel", "max", "1961", "1960", "12.03", "03.12", "12 march", "12. märz", "märz", "march",
    "labor", "lab", "befund", "bericht", "report", "entlass", "discharge", "reha", "gerinnung", "clotting",
    "inr", "aptt", "patient",
]
LINK = "http://localhost:8000/r/AbCdEf0123456789"


@pytest.mark.parametrize("template", MESSAGE_TEMPLATES)
def test_message_has_no_forbidden_tokens(template):
    text = render_message(template, LINK).replace(LINK, "").lower()
    hits = [t for t in FORBIDDEN if re.search(rf"\b{re.escape(t)}\b", text)]
    assert not hits, f"{template} leaks {hits}"
