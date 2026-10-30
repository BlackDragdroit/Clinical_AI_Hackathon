"""Engine units: dictation normalization, grounding, request job (rules + fake model), patient lookup, document job."""
import dataclasses
from datetime import datetime

import httpx
import pytest

from engine import document_job, request_job
from engine.backends import llm
from engine.ground import locate
from engine.normalize import normalize
from engine.patients import MemoryDirectory
from eval.render import md_to_pdf
from tests.conftest import doc

MARIA = {"ref": "Patient/maria-beispiel", "name": "Maria Beispiel", "dob": "1961-03-12"}
PATIENTS = MemoryDirectory([MARIA, {"ref": "Patient/max", "name": "Max Beispiel", "dob": "1960-01-01"},
                            {"ref": "Patient/maria-1985", "name": "Maria Beispiel", "dob": "1985-07-02"}])
COAG = ["6301-6", "14979-9", "777-3", "3255-7"]
SPOKEN_1 = ("Bitte bei Doktor Eva Brandl, eva punkt brandl at labor minus kanal punkt example, die aktuelle Gerinnung "
            "von Frau Maria Beispiel, geboren 12.3.1961, anfordern, vor dem geplanten Eingriff.")


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the model call; tests set .data to what the 'model' answers."""
    class Fake:
        data: dict | None = None
    f = Fake()
    monkeypatch.setattr(llm, "extract", lambda text, fields, instr, **kw: llm.LlmResult(f.data, "fake-model", 3))
    return f


# ---------------------------------------------------------------- normalization
@pytest.mark.parametrize("spoken, written", [
    ("eva punkt brandl at labor minus kanal punkt example", "eva.brandl@labor-kanal.example"),
    ("stefan unterstrich kern ät reha minus waldblick punkt example.", "stefan_kern@reha-waldblick.example."),
    ("plus vier drei sechs sechs null null null null null eins null eins", "+436600000101"),
    ("null sechs sechs null null null null null eins null eins", "06600000101"),
    ("Doktor Eder at elisabeth dot eder at labor dash am dash ring dot example", "Doktor Eder at elisabeth.eder@labor-am-ring.example"),
])
def test_dictation_is_written_out(spoken, written):
    assert normalize(spoken) == written


@pytest.mark.parametrize("text", [
    "ask Dr. Brandl at the lab for INR results",          # English 'at' without a domain stays
    "eva.brandl@labor-kanaI.example",                      # typed address keeps its capital I for the lint
    "Probe vom 22.10.2026, 08:10",
])
def test_ordinary_text_is_untouched(text):
    assert normalize(text) == text


def test_grounding_returns_the_source_slice():
    text = "bei Dr. Eva Brandl, Labor Kanalstraße"
    assert locate("Dr Eva Brandl", text).value == "Dr. Eva Brandl"
    assert locate("dr. eva   brandl", text).level == "case_space"
    assert locate("Dr. Anna Brandl", text) is None


# ---------------------------------------------------------------- request job (rules only)
def test_spoken_request_1_rules_only():
    r = request_job.run(SPOKEN_1, PATIENTS, use_llm=False)
    assert r["ready"], r["ask_de"]
    assert r["recipient"] == "Dr. Eva Brandl"                     # dictated "Doktor" written as the eID-comparable title
    assert r["contact"] == {"kind": "email", "value": "eva.brandl@labor-kanal.example"}
    assert r["doc_type"] == "lab" and r["panel"]["loinc"] == COAG
    assert r["patient"]["status"] == "unique" and r["patient"]["ref"] == "Patient/maria-beispiel"
    assert "Eingriff" in r["reason"]


def test_request_2_report_by_phone():
    r = request_job.run("Entlassungsbericht von Frau Maria Beispiel (*12.03.1961) bei Herrn Stefan Kern, "
                        "Reha Waldblick, Handy 0660 000 0101.", PATIENTS, use_llm=False)
    assert r["ready"] and r["doc_type"] == "report"
    assert r["recipient"] == "Stefan Kern"                       # lay title removed: eID name match needs it
    assert r["contact"] == {"kind": "sms", "value": "+436600000101"}


def test_english_request():
    r = request_job.run("Please ask Dr. Eva Brandl (eva.brandl@labor-kanal.example) for the latest coagulation "
                        "results of Maria Beispiel, born 12 March 1961, before her planned procedure.", PATIENTS, use_llm=False)
    assert r["ready"] and r["input"]["language"] == "en" and r["panel"]["key"] == "coagulation"


def test_no_birth_date_asks_instead_of_guessing():
    r = request_job.run("Bitte bei Dr. Eva Brandl eva.brandl@labor-kanal.example die Gerinnung von Frau Maria Beispiel anfordern.",
                        PATIENTS, use_llm=False)
    assert not r["ready"] and r["patient"]["status"] == "need_dob" and "Geburtsdatum" in r["ask_de"]


def test_near_twin_is_ambiguous():
    twins = MemoryDirectory([MARIA, {"ref": "Patient/marie", "name": "Marie Beispiel", "dob": "1961-03-12"}])
    r = request_job.run("Gerinnung von Frau Maria Beispiel, geb. 12.03.1961, bei Dr. Eva Brandl eva.brandl@labor-kanal.example",
                        twins, use_llm=False)
    assert r["patient"]["status"] == "ambiguous" and not r["ready"]


def test_missing_contact_is_asked():
    r = request_job.run("Gerinnung von Frau Maria Beispiel, geb. 12.03.1961, bei Dr. Eva Brandl anfordern", PATIENTS, use_llm=False)
    assert "contact" in r["missing"] and "Kontakt" in r["ask_de"]


# ---------------------------------------------------------------- request job with a (fake) model
def test_model_value_not_in_text_is_dropped(fake_llm):
    fake_llm.data = {"recipient_name": "Dr. Eva Brandl", "contact": "eva.brandl@labor-kanal.example",
                     "patient_name": "Maria Beispiel", "patient_birth_date": "12.03.1961",
                     "document_type": "lab_result", "requested_tests": "Gerinnung", "reason": "Herzoperation",
                     "recipient_organisation": "Labor Kanalstraße"}
    r = request_job.run("Gerinnung von Frau Maria Beispiel, geb. 12.03.1961, bei Dr. Eva Brandl eva.brandl@labor-kanal.example",
                        PATIENTS)
    assert set(r["dropped_ungrounded"]) == {"reason", "recipient_org"}       # invented, so gone
    assert r["fields"]["recipient_name"]["source"] == "rules+llm" and r["ready"]


def test_contact_disagreement_blocks(fake_llm):
    fake_llm.data = {"recipient_name": "Dr. Eva Brandl", "contact": "info@labor-kanal.example", "patient_name": None,
                     "patient_birth_date": None, "document_type": None, "requested_tests": None, "reason": None,
                     "recipient_organisation": None}
    r = request_job.run("Bei Dr. Eva Brandl eva.brandl@labor-kanal.example (Sekretariat info@labor-kanal.example) "
                        "Gerinnung von Frau Maria Beispiel, geb. 12.03.1961", PATIENTS)
    assert r["fields"]["contact"] is None and "contact" in r["missing"]


def test_model_is_asked_for_all_fields_unless_core(monkeypatch):
    asked = []
    monkeypatch.setattr(llm, "extract", lambda text, fields, instr, **kw: asked.append(set(fields)) or llm.LlmResult(None, "m", 1))
    for setting in ("all", "core"):
        monkeypatch.setattr(request_job, "settings", dataclasses.replace(request_job.settings, llm_fields=setting))
        request_job.run(SPOKEN_1, PATIENTS)
    assert asked == [set(request_job.FIELDS), set(request_job.CORE)]
    assert type(request_job.settings)().llm_fields == "all"     # the default


def test_api_key_is_sent_only_when_set(monkeypatch):
    seen = []

    def post(url, json=None, headers=None, timeout=None):   # noqa: A002 - mirrors httpx.post
        seen.append(headers)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", post)
    monkeypatch.delenv("ENGINE_LLM_CACHE", raising=False)
    base = dataclasses.replace(llm.settings, llm_url="http://gpu.example/v1")
    for key in ("", "k"):
        monkeypatch.setattr(llm, "settings", dataclasses.replace(base, llm_api_key=key))
        assert llm.extract("x", {"a": "string"}, "i").error is None
    assert seen == [{}, {"Authorization": "Bearer k"}]


def test_no_chat_template_kwargs_for_mistral_models(monkeypatch):
    bodies = []

    def post(url, json=None, headers=None, timeout=None):   # noqa: A002 - mirrors httpx.post
        bodies.append(json)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", post)
    monkeypatch.delenv("ENGINE_LLM_CACHE", raising=False)
    for model in ("ministral-8b", "Qwen/Qwen3-1.7B"):
        llm.extract("x", {"a": "string"}, "i", url="http://gpu.example/v1", model=model, mode="json_schema")
    assert "chat_template_kwargs" not in bodies[0] and bodies[1]["chat_template_kwargs"] == {"enable_thinking": False}


def test_model_down_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(llm, "extract", lambda *a, **k: llm.LlmResult(None, "m", 5, "ConnectError"))
    r = request_job.run(SPOKEN_1, PATIENTS)
    assert r["ready"] and r["models"]["llm_error"] == "ConnectError"


# ---------------------------------------------------------------- document job
@pytest.mark.parametrize("name", ["lab-result-maria-beispiel.md", "rehab-report-maria-beispiel.md"])
def test_markdown_passes_through_unchanged(name):
    r = document_job.read(doc(name).encode(), name)
    assert r["path"] == "markdown" and r["canonical_markdown"] == doc(name)


def test_pdf_text_layer_gives_the_same_values():
    md = doc("lab-result-maria-beispiel.md")
    r = document_job.read(md_to_pdf(md), "befund.pdf", requested_loinc=COAG, requested_doc_type="lab",
                          requested_at=datetime(2026, 10, 29, 9, 0))
    assert r["path"] == "pdf-text"
    rows = r["parsed"]["rows"]
    assert [(x["result"], x["unit"], x["loinc"]) for x in rows] == [("1.0", "", "6301-6"), ("31", "s", "14979-9"),
                                                                    ("245", "10^9/L", "777-3"), ("3.1", "g/L", "3255-7")]
    assert r["check_lines_de"] == ["Werte plausibel", "4/4 angefragte Parameter", "Probe vom 22.10.2026"]


def test_checks_flag_missing_old_and_implausible():
    md = doc("lab-result-maria-beispiel.md").replace("| Fibrinogen | 3.1 | g/L | 2.0 to 4.0 | 3255-7 |\n", "") \
        .replace("| 245 | 10^9/L |", "| 245 | mg |").replace("| 1.0 |", "| 10.0 |").replace("| 31 |", "| 3100 |")
    r = document_job.read(md.encode(), "x.md", requested_loinc=COAG, requested_at=datetime(2026, 12, 20), requested_doc_type="lab")
    flags = " ".join(r["flags"])
    assert "3/4" in flags and "Fibrinogen" in flags
    assert "Einheit „mg“ passt nicht zu Platelets" in flags and "aPTT 3100 s unplausibel" in flags
    assert "59 Tage alt" in flags


def test_wrong_document_type_is_flagged():
    r = document_job.read(doc("rehab-report-maria-beispiel.md").encode(), "r.md", requested_doc_type="lab")
    assert any("Angefragt: Laborbefund, erhalten: Bericht" in f for f in r["flags"])


def test_model_fallback_keeps_only_grounded_rows(fake_llm):
    text = ("Labor Nord – Befund\nName: Maria Beispiel  Geb.: 12.03.1961\nINR 1,0 (0,8-1,2)\nThrombozyten 245 G/l (150-400)\n")
    fake_llm.data = {"organisation": "Labor Nord", "title": "Befund", "patient_name": "Maria Beispiel",
                     "patient_birth_date": "12.03.1961", "sample_taken": None, "reported": None, "signed_by": None,
                     "rows": [{"test": "INR", "result": "1,0", "unit": None, "reference_range": "0,8-1,2", "loinc": None},
                              {"test": "Thrombozyten", "result": "245", "unit": "G/l", "reference_range": "150-400", "loinc": None},
                              {"test": "Fibrinogen", "result": "3,1", "unit": "g/l", "reference_range": None, "loinc": None}]}
    r = document_job.read(text.encode(), "befund.txt")
    assert r["path"] == "model-fallback"
    assert [x["test"] for x in r["parsed"]["rows"]] == ["INR", "Thrombozyten"]        # Fibrinogen was invented
    assert r["parsed"]["patient_dob"] == "1961-03-12"


def test_readback_rebuilds_with_corrections():
    md = doc("lab-result-maria-beispiel.md")
    out = document_job.apply_readback(md, {"rows.0.result": "1.1"})
    assert "| INR (prothrombin time) | 1.1 |" in out and "Patient: Maria Beispiel, born 12 March 1961" in out


# ---------------------------------------------------------------- HTTP API (what the app calls with ENGINE_URL)
def test_engine_api_request_and_document():
    from fastapi.testclient import TestClient
    from engine.api import app
    with TestClient(app) as c:
        assert c.get("/health").json()["ok"]
        r = c.post("/v1/request", json={"text": SPOKEN_1, "use_llm": False}).json()
        assert r["contact"]["value"] == "eva.brandl@labor-kanal.example" and r["patient"]["status"] == "need_dob" or r["ready"] is False
        pdf = md_to_pdf(doc("lab-result-maria-beispiel.md"))
        d = c.post("/v1/document", files={"file": ("b.pdf", pdf, "application/pdf")},
                   data={"requested_loinc": ",".join(COAG), "requested_doc_type": "lab"}).json()
        assert d["path"] == "pdf-text" and d["check_lines_de"][:2] == ["Werte plausibel", "4/4 angefragte Parameter"]


def test_photo_rendering_is_an_image_the_engine_routes_to_ocr():
    from eval.render import photo, scan
    pdf = md_to_pdf(doc("lab-result-maria-beispiel.md"))
    for img in (photo(pdf, seed=3), scan(pdf, seed=3)):
        r = document_job.read(img, "foto.jpg", use_models=False)
        assert r["input"]["kind"] == "image" and not r["ok"]          # no OCR configured -> asks for another format


# ---------------------------------------------------------------- ELGA (Austrian lab codes)
def test_elga_codes_have_valid_check_digits_and_names():
    from engine._core import is_valid
    from engine.lexicon import ELGA, EQUIV_GROUPS
    assert len(ELGA) > 100 and all(is_valid(c) for c in ELGA)
    assert all(is_valid(c) for g in EQUIV_GROUPS for c in g)
    assert ELGA["26464-8"][0] == "Leukozyten"


def test_austrian_codes_count_for_completeness():
    md = doc("lab-result-maria-beispiel.md").replace("| INR (prothrombin time) | 1.0 | | 0.8 to 1.2 | 6301-6 |",
                                                     "| PTZ (Quick) | 95 | % | 70 to 120 | 5894-1 |")
    r = document_job.read(md.encode(), "x.md", requested_loinc=COAG)
    assert "4/4 angefragte Parameter" in r["check_lines_de"]


def test_new_panels_and_single_tests_in_requests():
    r = request_job.run("Bitte bei Dr. Eva Brandl eva.brandl@labor-kanal.example die Schilddrüsenwerte von Frau Maria Beispiel, "
                        "geb. 12.03.1961, anfordern.", PATIENTS, use_llm=False)
    assert r["panel"]["key"] == "thyroid" and "3016-3" in r["panel"]["loinc"]
    r = request_job.run("Gamma-GT von Frau Maria Beispiel, geb. 12.03.1961, bei Dr. Eva Brandl eva.brandl@labor-kanal.example",
                        PATIENTS, use_llm=False)
    assert r["panel"]["loinc"] == ["2324-2"]
