# Engine evaluation

Synthetic data only. Results land in `eval/RESULTS.md` (generated, do not edit by hand).

| Set | File | Made by | Use |
|---|---|---|---|
| patients | `data/patients.json` | Synthea v4.0.0 (birth dates, sex, lab values) + Austrian names; 25 planted namesakes (same name, other birth date) and 15 near-twins (similar given name, same birth date) | the patient directory every request is resolved against |
| dev requests | `data/requests_dev.jsonl` (600) | templates in `build_data.py`, DE/EN, typed/dictated, traps | **tuning only**: the rules were fixed on this set, so its score says nothing about new phrasing |
| test requests | `data/requests_test.jsonl` (300) | written separately by a model that never saw the engine code or the templates | the number we report |
| human requests | `data/requests_human.jsonl` | the team, by hand (see below) | small, real phrasing |
| documents | `data/documents.jsonl` (120) | Synthea lab values in jury-style Markdown (DE/EN, comma decimals, missing LOINC, wrong patient, old sample, implausible value) + discharge reports | rendered at eval time as Markdown, PDF, fax-quality scan and phone photo (`render.py`) |

```
uv run python -m eval.synthea            # once: Java + ~200 MB jar into tools/, 400 patients
uv run python -m eval.build_data         # patients, senders, dev requests, documents
make engine-eval                         # = python -m eval.run_eval …, see the module docstring for all options
uv run python -m eval.run_eval requests --set test --rung rules
uv run python -m eval.run_eval requests --set test --rung nuextract3 --llm-url http://<vm>:8001/v1 --llm-model numind/NuExtract3 --llm-mode nuextract
uv run python -m eval.run_eval documents --forms md,pdf,scan,photo --rung gpu --ocr-url http://<vm>:8003/v1 --llm-url http://<vm>:8001/v1
```

## Adding human examples (team)
Append lines to `data/requests_human.jsonl`, one request each, written the way you would really type it to the bot.
Pick the patient from `data/patients.json` and the recipient from `data/senders.json`:

```
{"id": "human-001", "lang": "de", "style": "typed", "trap": "none", "text": "…your sentence…", "gold": {"recipient": "Dr. Eva Brandl", "contact": "eva.brandl@labor-kanal.example", "contact_kind": "email", "patient_ref": "Patient/maria-beispiel", "doc_type": "lab", "panel": "coagulation", "ready": true}}
```
`ready` is false when you leave out the birth date or the contact on purpose (`trap`: `no_dob` / `no_contact`).

## Voice
Record the *dictated* requests (style `dictated`, already written the way they are spoken) on a phone, or synthesise them
on the GPU box (Qwen3-TTS), and save them as `data/audio/<set>/<id>.wav`. Then
`uv run python -m eval.run_eval requests --set test --rung voice --audio-dir eval/data/audio/test --asr-url http://<vm>:8002/v1`.
