<p align="center">
  <img src="docs/img/iris-logo.png" alt="IRIS logo" width="180">
</p>

<h1 align="center">IRIS</h1>

<p align="center">
  <b>Identity-Verified Record Intake System</b><br>
  Secure document requests from outside the clinic, filed as valid FHIR R4. Verified sender, verified patient, full audit trail.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/FHIR-R4-e8562a" alt="FHIR R4">
  <img src="https://img.shields.io/badge/HL7%20validator-0%20errors-2ea44f" alt="HL7 validator: 0 errors">
  <img src="https://img.shields.io/badge/Matrix-Element%20%2B%20Synapse-0dbd8b" alt="Matrix">
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776ab" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/FastAPI-portal%20%2B%20engine-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/data-synthetic%20only-6c757d" alt="Synthetic data only">
</p>

<p align="center">
  <b>AIM Healthcare Hackathon Vienna 2026</b> · Track 2: Health Data Interoperability · partner FTAPI
</p>

---

## Overview

Austrian doctors are moving to a closed, encrypted document network on Matrix. Labs, rehab clinics and patients
outside that network are still reached by fax or plain email, and their results come back as scans that someone
retypes by hand.

**IRIS closes that gap.** A doctor requests a document from her Matrix room in one sentence. The outside person
gets a neutral one-time link, proves who they are with an electronic ID, and uploads the answer in the browser:
no account, no install. IRIS checks that it is the right person and the right patient, turns the answer into
coded FHIR R4 with a Provenance record, files it on the clinic's FHIR server, and tells the doctor in Matrix.
Every step lands in a hash-chained audit log.

| | |
|---|---|
| **6/6** | required audit steps logged, with who, what and when |
| **3/3** | misdelivery tests caught (wrong address, forwarded link, wrong patient) |
| **0 / 17** | jury-style documents filed to the wrong patient |
| **0** | patient names, birth dates or document types in 24 emails and 5 SMS |
| **0** | HL7 validator errors on the filed bundles |

## Features

- **One-sentence requests.** Dr. Hofer types or dictates the request in German or English. The AI engine extracts recipient, contact, patient and document type; every extracted value must literally occur in her text, and the patient is matched on two identifiers against the FHIR server.
- **Address lint before sending.** Look-alike domains (`labor-kanaI` with a capital I), typos and implausible phone numbers are flagged on the draft card before anything leaves the clinic.
- **Neutral delivery.** Email and SMS carry only the clinic name and a 256-bit single-use link. A test fails the build if a template could ever contain a patient name, birth date or document type.
- **Identity first, data second.** The link page shows one neutral sentence. Only after an eID login whose verified name matches the person the doctor named does the patient appear (*DemoID* simulates ID Austria; production uses the OIDC login).
- **Any document format.** PDF (exact text layer), Markdown, plain text or pasted text; photos and scans are read by a vision model and confirmed by the sender before filing.
- **Right-patient guarantee.** A calibrated Fellegi–Sunter record-linkage model compares the requested patient, the patient typed by the sender and the patient in the document. Mismatches are quarantined, borderline cases go to the doctor.
- **Standards-native output.** One FHIR R4 transaction Bundle per answer: an Observation per value with LOINC, UCUM units, reference range and interpretation, a DiagnosticReport, the original as DocumentReference, and a Provenance naming the verified sender and how they were identified. Validated with `$validate` before filing.
- **Tamper-evident audit.** Append-only log with a SHA-256 hash chain, a 6/6 coverage view and a plain-language timeline on `/audit`, in English and German.
- **Replaceable parts.** Email, SMS, eID, FHIR server, secure-transfer provider and models each sit behind one small interface.

## Screenshots

<table>
  <tr>
    <td align="center"><img src="docs/img/02-link.png" alt="Neutral link page" width="200"></td>
    <td align="center"><img src="docs/img/03-demoid.png" alt="DemoID eID login" width="200"></td>
    <td align="center"><img src="docs/img/04-answer.png" alt="Answer form after identity check" width="200"></td>
    <td align="center"><img src="docs/img/05-receipt.png" alt="Receipt" width="200"></td>
  </tr>
  <tr>
    <td align="center"><sub><b>Link page</b><br>nothing about the patient</sub></td>
    <td align="center"><sub><b>eID login</b> (DemoID)<br>name must match</sub></td>
    <td align="center"><sub><b>Answer form</b><br>shown only after identity</sub></td>
    <td align="center"><sub><b>Receipt</b><br>no account created</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/img/07-blocked.png" alt="Forwarded link blocked" width="200"></td>
    <td align="center"><img src="docs/img/08-wrong-patient.png" alt="Wrong patient not filed" width="200"></td>
    <td align="center" colspan="2"><img src="docs/img/06-report.png" alt="Filed lab result with LOINC codes" width="420"></td>
  </tr>
  <tr>
    <td align="center"><sub><b>Forwarded link</b><br>wrong person, nothing shown</sub></td>
    <td align="center"><sub><b>Wrong patient</b><br>not filed, not named</sub></td>
    <td align="center" colspan="2"><sub><b>Filed result</b>: LOINC-coded values, out-of-range flagged, link to every FHIR resource</sub></td>
  </tr>
</table>

<p align="center"><img src="docs/img/09-audit.png" alt="Audit log: hash chain intact, 6 of 6 steps, misdeliveries caught" width="860"><br>
<sub><b>Audit log</b>: chain verified, 6/6 required steps, misdeliveries M2 and M3 caught</sub></p>

## How it works

1. **Request.** Dr. Hofer writes the request in her Matrix room (Element). The bot drafts a card: patient (looked up on HAPI FHIR), recipient, contact, document type, address warnings. She confirms; IRIS creates a FHIR `Task` and sends the neutral link.
2. **Link.** The outside person opens the single-use link (only its SHA-256 is stored; 72 h, 5 identity attempts, single use).
3. **Identity.** eID login. The verified name must match the named person, otherwise nothing is shown and the misdelivery is logged and reported.
4. **Answer.** The patient and the request are revealed; the sender types the patient's name and birth date and uploads the document.
5. **Check.** The engine reads the document (exact parser for PDF/Markdown, read-back for photos); the core runs the three-way patient check and the LOINC checks and decides `file`, `review` or `reject`.
6. **File.** On `file`: FHIR transaction Bundle → `$validate` → HAPI, `Task` completed, Provenance attached. On `review`: the doctor decides in Matrix. On `reject`: quarantine.
7. **Notify.** The doctor's chat card updates with the result and links to the filed resources. Every step is in the audit chain.

## Architecture

<p align="center"><img src="docs/img/atlas-01-architecture.png" alt="IRIS architecture: clinic network, internet-facing portal, team GPU" width="900"></p>

Three trust zones. **Everything that sees patient data runs inside the clinic**: Matrix (Synapse + Element), the
IRIS app, the deterministic core, SQLite, HAPI FHIR and the AI engine. The **internet-facing** side gets only an
opaque link and a neutral page. The **GPU** only receives text through an SSH tunnel and runs open-weight models.
Full details, including the tool stack, timings and data model, in the **[IRIS System Atlas](docs/system-atlas.html)**
(open it in a browser).

<details>
<summary><b>Design patterns</b>: models read, rules decide</summary>
<br>
<img src="docs/img/atlas-03-patterns.png" alt="Twelve design patterns" width="900">
</details>

<details>
<summary><b>Request lifecycle and audit events</b></summary>
<br>
<img src="docs/img/atlas-04-lifecycle.png" alt="Request lifecycle" width="900">
</details>

<details>
<summary><b>Time per step</b></summary>
<br>
<img src="docs/img/atlas-05-timing.png" alt="Time per request step" width="900">
</details>

<details>
<summary><b>FHIR R4 resources filed for one lab answer</b></summary>
<br>
<img src="docs/img/atlas-06-fhir.png" alt="FHIR resources and references" width="900">
</details>

<details>
<summary><b>What crosses each boundary</b></summary>
<br>
<img src="docs/img/atlas-07-boundaries.png" alt="What each boundary may contain" width="900">
</details>

## Tech stack

| Layer | Tools |
|---|---|
| Clinic chat | Matrix: Synapse homeserver, Element Web, matrix-nio bot |
| Application | Python, FastAPI + Uvicorn, Jinja templates, SQLite, httpx |
| Core logic | Python standard library only: document parser, Fellegi–Sunter record linkage, LOINC checks, FHIR Bundle builder |
| Health data | HAPI FHIR R4 server, official HL7 validator, LOINC, UCUM |
| AI engine | FastAPI service; open-weight models on vLLM (one RTX A5000); CPU fallbacks (rules, Parakeet ONNX, Tesseract) |
| Identity | Simulated ID Austria assertion (*DemoID*), HMAC-signed; production: ID Austria OIDC / eIDAS |
| Delivery | SMTP (Mailpit in the demo), simulated SMS gateway; FTAPI SubmitBox adapter boundary |
| Ops and tests | Docker Compose, uv, Make, pytest, Playwright end-to-end tests, GitHub Actions |

## Run it

Needs Docker, [uv](https://docs.astral.sh/uv/), Java 17+ (only for the HL7 validator).

```
make install      # python deps
make test         # unit + end-to-end flow tests, no Docker
make up           # Synapse + Element + HAPI + Mailpit + app, users/room/patient set up
```

| What | Where |
|---|---|
| Element (Dr. Hofer) | http://localhost:8080 — user `lena.hofer`, password in `.env` |
| Mailpit (emails) | http://localhost:8025 |
| SMS (simulated) | http://localhost:8000/sms |
| Audit log | http://localhost:8000/audit |
| HAPI FHIR | http://localhost:8090/fhir |

In the room, write the request in plain English or German, for example *"Please ask Dr. Eva Brandl at
eva.brandl@labor-kanal.example for the coagulation values of Maria Beispiel, born 12 March 1961"*, and confirm the
card (a patient is picked only with two identifiers: name and birth date). The exact command
form also works: `!anfrage labor "Dr. Eva Brandl" eva.brandl@labor-kanal.example Patient/maria-beispiel Grund: coagulation before procedure`,
then `!senden <id>` (`!anfrage` = request, `labor` = lab, `Grund` = reason, `!senden` = send).

The portal accepts PDF (read from its text layer), Markdown or plain-text files, pasted text, and photos or scans
(those are read back to the sender for confirmation, never filed straight away).

Browser end-to-end test of the portal (request 1 timed, request 2 via `/sms`, M1–M3), JSON on stdout and in `var/e2e.json`:

```
uv run python scripts/e2e.py            # against the running stack (make up)
uv run python scripts/e2e.py --local    # no Docker: app in-process, fake HAPI
```

It needs a Chromium: `uv run playwright install chromium`, or a system `chromium` on the PATH.

## Components in detail
IRIS has a deterministic core, a FastAPI service around it, and five off-the-shelf services.

**Models and services.** Every decision is deterministic or statistical: patient matching is a calibrated record-linkage model (Fellegi–Sunter, weights estimated on synthetic labelled pairs, `core/weights.json`); parsing of the scenario format, LOINC checks, FHIR building and the identity policy are rules. Models only *read* (see [AI engine](#ai-engine)): Dr. Hofer's typed or spoken request, and answers that arrive as PDF, scan or phone photo. They run self-hosted on one GPU (vLLM), every value they return must be a slice of the input, and the rules above still decide. Services we run but did not write: Synapse, Element Web, HAPI FHIR R4, Mailpit, SQLite.

| Component | Built / used | Role |
|---|---|---|
| `core/` (stdlib only) | built | `parse_doc.py`: Markdown parser (EN + DE). `fs_matcher.py`: Fellegi–Sunter check of the patient, three ways: requested ↔ typed ↔ document. `loinc.py`: check digit and code/name consistency, never invents a code. `fhir_build.py`: transaction Bundle (lab: Observation per row with LOINC, UCUM, reference range, interpretation; DiagnosticReport; DocumentReference with the original; Provenance. Rehab report: DocumentReference LOINC 18842-5 + Provenance). Provenance agents: the verified sender and our Device. `intake.py` returns the decision file / review / reject. |
| `app/` (FastAPI) | built | Public portal and clinic-side logic: `commands.py` (doctor commands, shared by bot and CLI), `bot.py` (matrix-nio), `requests_service.py` (draft → send: single-use link, channel, FHIR Task), `misdelivery.py`, `intake_service.py` (core decision → HAPI `$validate` → transaction → Task completed; review → `!ablegen` / `!verwerfen` (file / discard); reject → quarantine), `fhir_client.py`, `db.py`. |
| `app/tokens.py` | built | 256-bit random link token, only its SHA-256 is stored, TTL 72 h, max 5 identity attempts, single use. |
| `app/delivery/` | built | `Channel` interface: `send(to, link)` receives only recipient and link, so no patient data can reach a channel. Implementations: `smtp_mailpit`, `sms_inbox` (simulated SMS page), `ftapi_submitbox` (stub). |
| `app/identity/` | built | `eid_mock.py`: simulated ID Austria assertion (name, birth date, bPK-like pseudonym, level of assurance), HMAC-signed, shown to testers as *DemoID*. `policy.py`: name binding, the eID name must equal the person Dr. Hofer named. |
| `app/misdelivery.py` | built | Address lint on the draft card: look-alike characters (I/l/1, O/0, rn/m), capitals or non-ASCII in the domain, typos within 2 characters of a known domain, implausible phone numbers. Warns, never blocks. |
| `app/audit.py` | built | Append-only log, SHA-256 hash chain; the 6 required events (request_sent, link_opened, identity_checked, answer_sent, answer_filed, misdelivery_caught) plus extra events. The `/audit` page shows chain status, 6/6 coverage, requests, a plain-language timeline and the misdelivery panel, in English and German. |
| `app/notify.py` | built | Outbox table that the bot drains into the Matrix room. |
| `engine/` (FastAPI, :8100) | built | AI engine, see [AI engine](#ai-engine): request job (typed/spoken DE+EN → checked request) and document job (Markdown/PDF/scan/photo → scenario-shaped Markdown + completeness/recency/plausibility checks). Stateless; the app calls it over HTTP (`ENGINE_URL`). |
| vLLM: NuExtract3 4B, Qwen3-ASR 1.7B, PaddleOCR-VL 1.6 | used | Open-weight models on one A5000 (`deploy/gpu/`). Each is optional: without it the engine falls back to rules / CPU (Tesseract, Parakeet ONNX). |
| Synapse + Element Web | used | Matrix homeserver (`klinikum.example`) and Dr. Hofer's client. |
| HAPI FHIR R4 | used | Patient source, Task lifecycle, `$validate`, store for filed resources. |
| Mailpit | used | Catches the outgoing emails. |
| SQLite | used | Requests, tokens, answers, audit, outboxes (only `app/db.py` imports it). |

Request 1 (lab values), happy path. Every step is written to the audit log.

```mermaid
sequenceDiagram
  actor D as Dr. Hofer
  participant B as Bot (Matrix)
  participant H as HAPI FHIR
  participant C as Channel (email)
  actor E as Outside person
  participant P as Portal
  participant K as core
  D->>B: request in one sentence (or !anfrage)
  B->>H: read Patient (name, DOB)
  B-->>D: draft card with address check, then send
  B->>C: send(recipient, link)
  B->>H: create Task (requested)
  E->>P: open link (neutral page only)
  P->>E: eID login (DemoID / ID Austria)
  E->>P: assertion (name, DOB, pseudonym, LoA)
  P->>P: eID name = named person?
  P->>E: patient and request revealed
  E->>P: types patient name + DOB, uploads document
  P->>K: three-way check, parse, build Bundle
  K-->>P: decision file
  P->>H: $validate, transaction, Task completed
  P-->>D: Matrix message via notify outbox
```

**Trust boundaries**

- Patient name and birth date stay in the clinic-side service until the outside person has passed the identity check. Before that, the link page shows only a neutral sentence with the clinic name.
- Delivery channels see only the recipient and the opaque link (`Channel.send(to, link)`). The message templates can use only the link and the clinic name.
- Nothing is written to HAPI unless the core decides `file` and HAPI `$validate` reports no errors, or Dr. Hofer confirms a `review` with `!ablegen` (file). A `reject` (document is about another patient) is quarantined, not filed.
- Unknown, expired, used and exhausted links all get the same neutral answer, so a guesser learns nothing.
- Only Matrix IDs in `AUTHORIZED_SENDERS` (the clinic directory; default Dr. Hofer) can make the bot request documents or file answers. Anyone else in the room gets "Keine Berechtigung" (no permission) and nothing happens.
- The public portal is the part that faces the internet. In the prototype we host it ourselves. In production it can move to a third-party trust provider such as FTAPI SubmitBox, behind the `Channel` and portal boundary, because it needs no patient data before the identity check. The prototype does not use FTAPI (see below).

## AI engine

One service, two jobs, one rule: **models read, rules decide, and every value must be a slice of the input.**

```mermaid
flowchart LR
  subgraph IN[Input]
    T["Typed request (DE/EN)"]
    V["Voice note (Element)"]
    MD["Markdown / text"]
    PDF["PDF"]
    IMG["Scan / phone photo"]
  end
  V -->|"Qwen3-ASR 1.7B (vLLM) · CPU: Parakeet"| N
  T --> N["normalize dictation: 'dot' → '.', 'at' → '@', spoken digits"]
  N --> R["rules (always)"] & L["NuExtract3 4B (vLLM, JSON schema)"]
  R & L --> G["ground: value must occur in the text, else dropped"]
  G --> P["patient: name + birth date → FHIR search → Fellegi–Sunter rank"]
  P --> CARD["draft card → send"]
  MD --> CP["core parser (exact)"]
  PDF -->|"text layer"| CP
  PDF -->|"image only"| O
  IMG --> O["PaddleOCR-VL + Tesseract (two readers)"]
  CP -->|"parser fails"| L2["NuExtract3, grounded"]
  O --> RB["read-back: sender confirms values; disagreements highlighted"]
  CP & L2 & RB --> CK["checks: completeness, recency, plausibility, document type"]
  CK --> INTAKE["core intake: 3-way patient check → FHIR"]
```

| Job | Input | Models (GPU) | CPU fallback | What is guaranteed |
|---|---|---|---|---|
| Request | typed or spoken German/English | Qwen3-ASR 1.7B, NuExtract3 4B | rules (regex, cue words), Parakeet TDT 0.6B v3 ONNX | every field is a slice of the transcript; contact disagreements between rules and model are asked back; a patient is picked only with two identifiers and a ≥6-bit margin |
| Document | Markdown, text | — (core parser) | — | identical to the scenario path |
| Document | PDF with text layer | — | pdfplumber | exact characters; same parser |
| Document | unusual text shape | NuExtract3 4B | — | only values that occur verbatim survive; numbers must match exactly |
| Document | scan, photo, image PDF | PaddleOCR-VL 1.6 | Tesseract (always runs, second reader) | never filed directly: the sender confirms a read-back screen; Provenance records it |

Checks on every answer (deterministic, never change a value): requested tests delivered (e.g. "4/4 requested parameters"), sample age vs. request date, unit and physical plausibility per LOINC, document type vs. request. They appear in Dr. Hofer's message.

Run it: `make engine` (local, rules + CPU), `make gpu-up` on the A5000 VM, then `ENGINE=http://<vm>:8100 make gpu-smoke`; point the app at it with `ENGINE_URL`. Model choices and the research behind them: DECISIONS.md.

## Design answers
### 1. How does an outside person prove who they are without a directory?
There is no directory of outside people, so Dr. Hofer's request takes its place: she names who must answer and one contact. The outside person then proves two things, and sees nothing about the patient until both hold. No account, no password, no app: a browser and the eID they already have.

1. **Possession of the contact.** The email or SMS carries a single-use link: a 256-bit random token (`app/tokens.py`). Only its SHA-256 hash is stored, together with the one request and the contact it was sent to. It expires after 72 h, stops working after 5 failed identity checks and is spent when the answer is submitted. Before login the page shows one neutral sentence with the clinic name; unknown, expired, used and exhausted links all get the same neutral page.
2. **Identity.** The person logs in with ID Austria, which returns name, birth date, a sector-specific pseudonym (bPK) and the level of assurance. The prototype simulates this with an HMAC-signed assertion carrying the same fields (`app/identity/eid_mock.py`), shown to testers as *DemoID* and clearly marked as a simulation; production uses the ID Austria OIDC login. People outside Austria use their own national EU eID through eIDAS (see answer 2).
3. **Binding.** The verified name must match the name Dr. Hofer typed (`policy.names_match`): titles, case and umlaut spelling are ignored, hyphen and space count the same, the eID may carry extra given names ("Eva Maria Brandl" matches "Dr. Eva Brandl"), and the family name must match in full. If it doesn't match, nothing is shown, the attempt is counted, `identity_checked FAILED` and `misdelivery_caught` go to the audit log, and Dr. Hofer gets a warning in Matrix.
4. **Need-to-know reveal.** Only after both proofs does the portal show the patient's name, birth date and what is requested, logged as `patient_revealed`.
5. **Record.** The audit log names `eid:<pseudonym> <name>` as the actor of `identity_checked`, `patient_revealed` and `answer_sent`. In FHIR, `Provenance.agent.who` is the verified sender, and its role text states both proofs (in German: "ID Austria (simuliert, LoA high), Namensabgleich OK; Besitz der Kontaktadresse über Einmal-Link", i.e. ID Austria (simulated, high assurance), name match OK, possession of the contact via the one-time link). The pseudonym stays in the audit log; it is not written to FHIR.

What this does not prove: that the person holds a role or licence. The eID proves *who* they are; that this person is the right one to send a lab result rests on Dr. Hofer's choice, as it does today when she picks up the phone. A lookup in a professional register is not built.
### 2. Which identity check per document type, and why?
Every answer needs two proofs: **possession** of the single-use link sent to the contact Dr. Hofer typed, and **identity** through ID Austria, with the verified name matching the person she named. What differs per document type is what we record and why the check matters. The rules live in `app/identity/policy.py`.

| Document | Required check | Filed automatically when | Why |
|---|---|---|---|
| Lab result | Link + ID Austria + name match with the requested person | The patient check says `file` (exact birth date, matching family name, W ≥ 4 bits) | Lab values drive a clinical decision, here coagulation before a procedure. A wrong value from the wrong sender is the costliest error, so the sender must be the named person. |
| Rehab discharge report | Link + ID Austria + name match; the report's author is recorded separately, as stated in the document | Same patient check | Discharge managers or admin staff often send reports on behalf of the physician who wrote them. We verify who sent it and keep the author from the document, so Provenance shows both. |

In every case a borderline patient match goes to Dr. Hofer (`review`, she confirms in Matrix), and a mismatch is quarantined (`reject`). Nothing reaches the FHIR server without the core's `file` decision or her confirmation.

**Without ID Austria.** People abroad log in with their own national eID: ID Austria accepts the eIDs that other EU states have notified under eIDAS (for example the German eID card), so a rehab clinic in Bavaria answers the same way. The prototype simulates this in `eid_mock.py`; production uses the same OIDC handoff.

**Deliberately not offered: link possession alone.** It can't tell the named person from a colleague she forwarded the email to (misdelivery M2), so the patient's data would be shown to whoever holds the link. People with no eID at all (most people outside the EU) can't answer through this service; for them the clinic stays on its current channel.
### 3. Which FHIR resources, and how do they reference each other and the patient?
The Patient already exists on the clinic's FHIR server; we read it, never create it. Sending a request creates a **Task**. An accepted answer is filed as one **transaction Bundle** (`core/fhir_build.py`): every new resource has a `urn:uuid` fullUrl, the server resolves the references, and either all resources are stored or none. Before that, HAPI `$validate` must report no errors (`intake_service._file`), and the Task is then set to `completed` with every filed resource in `Task.output`. Edge labels below are the FHIR elements as filed.

Request 1, lab result (10 resources in the Bundle, plus the Task):

```mermaid
flowchart LR
  PAT["Patient<br/>maria-beispiel<br/>(existing)"]
  TASK["Task<br/>requested → completed<br/>input: LOINC 11502-2"]
  OBS["Observation × 4<br/>INR · aPTT · platelets · fibrinogen"]
  DR["DiagnosticReport<br/>LAB, LOINC 11502-2"]
  DOC["DocumentReference<br/>LOINC 11502-2<br/>original file"]
  PROV["Provenance"]
  PRAC["Practitioner<br/>Dr. Eva Brandl<br/>(verified sender)"]
  ORG["Organization<br/>Labor Kanalstraße"]
  DEV["Device<br/>IRIS intake"]

  TASK -->|for| PAT
  TASK -.->|"output.valueReference<br/>(every filed resource)"| DR
  OBS -->|subject| PAT
  DR -->|subject| PAT
  DOC -->|subject| PAT
  DR -->|result| OBS
  OBS -->|performer| PRAC
  OBS -->|performer| ORG
  DR -->|performer| PRAC
  DR -->|performer| ORG
  DOC -->|author| PRAC
  DOC -->|custodian| ORG
  PROV -->|target| OBS
  PROV -->|target| DR
  PROV -->|target| DOC
  PROV -->|"entity.what (role source)"| DOC
  PROV -->|"agent.who (author)"| PRAC
  PROV -->|"agent.onBehalfOf"| ORG
  PROV -->|"agent.who (assembler)"| DEV
```

Request 2, rehab discharge report (6 resources, plus the Task). The report's author comes from the document and is not identity-checked; the sender is.

```mermaid
flowchart LR
  PAT["Patient<br/>maria-beispiel<br/>(existing)"]
  TASK["Task<br/>requested → completed<br/>input: LOINC 18842-5"]
  DOC["DocumentReference<br/>LOINC 18842-5 discharge summary<br/>context.period = stay"]
  PROV["Provenance"]
  AUTH["Practitioner<br/>Dr. Johanna Leitner<br/>(author per document)"]
  SEND["Practitioner<br/>Stefan Kern<br/>(verified sender)"]
  ORG["Organization<br/>Reha Waldblick"]
  DEV["Device<br/>IRIS intake"]

  TASK -->|for| PAT
  TASK -.->|"output.valueReference<br/>(every filed resource)"| DOC
  DOC -->|subject| PAT
  DOC -->|"author (1st)"| AUTH
  DOC -->|"author (2nd)"| SEND
  DOC -->|custodian| ORG
  PROV -->|target| DOC
  PROV -->|"agent.who (author)"| SEND
  PROV -->|"agent.onBehalfOf"| ORG
  PROV -->|"agent.who (assembler)"| DEV
```

| Resource | Purpose | Key elements and codes |
|---|---|---|
| Patient | Who it is about (existing record) | Read for name and birth date, the "requested" side of the three-way patient check |
| Task | The open request and its outcome | `status` requested → completed (filed) or → in-progress (wrong patient, still waiting); `intent` order; `for` Patient; `input` = requested document type (LOINC 11502-2 / 18842-5); `executionPeriod` start at sending, end at closing; `restriction.period.end` = link expiry; `requester` / `owner` as display names; `output` = filed resources |
| Observation | One per lab value, so values are queryable, not just a PDF | `category` laboratory; `code` LOINC (INR 6301-6, aPTT 14979-9, platelets 777-3, fibrinogen 3255-7) plus the lab's own label; `valueQuantity` with UCUM (`s`, `10*9/L`, `g/L`; INR has no unit); `referenceRange` low/high + the lab's text; `interpretation` (v3 ObservationInterpretation, here all `N`); `effectiveDateTime` = sample taken, `issued` = reported |
| DiagnosticReport | The lab report as a whole | `category` v2-0074 LAB; `code` LOINC 11502-2; `result` → Observations; `presentedForm` = original; `conclusion` = the lab's comment |
| DocumentReference | The original, unchanged | Lab: type LOINC 11502-2. Rehab: LOINC 18842-5, `context.period` = stay. Original file as attachment with size and SHA-1 hash; `author`, `custodian` |
| Provenance | Who sent it, how that was checked, what software filed it | `target` = the clinical resources (Observations, DiagnosticReport, DocumentReference); `occurredDateTime` / `recorded`; `policy` → answer 2; agent `author` = verified sender, `role.text` = both identity proofs, `onBehalfOf` = their organisation; agent `assembler` = Device; lab only: `entity` (source) = the original DocumentReference |
| Practitioner, Organization, Device | Targets of the references above | Name only, no identifier |

The filed resources do not point back at the Task (no `basedOn`); `Task.output` is the link from request to answer. FHIR timestamps are Europe/Vienna, so offsets are correct across daylight saving time.

**Validation.** The official HL7 validator (`make validate`, `-version 4.0`) reports **0 errors** on both scenario bundles built by `core/` (10 and 6 warnings, all dom-6 "resource should have narrative", a best-practice hint).
### 4. How do we notice a misdelivery?
Three independent checks, one per way a document goes astray (`scenario/misdelivery.md`):

| Test | Caught by | When | Result (METRICS.md) |
|---|---|---|---|
| **M1** wrong address (`labor-kanaI`) | Address lint on the draft card (look-alike characters, typos, capitals or non-ASCII in the domain), then the identity binding if it is sent anyway | Before sending; again at login | Caught in 4/4 runs, nothing shown |
| **M2** forwarded to a colleague | Identity binding: the eID name must be the person Dr. Hofer named | At login, before anything is shown | Caught in 4/4 runs, nothing shown |
| **M3** document about another patient | Three-way Fellegi–Sunter record linkage: requested patient ↔ name and birth date typed by the sender ↔ patient in the document | After upload, before filing | Caught in 6/6 runs, nothing filed |

The patient check scores each pair of records in bits (log₂ of how much more likely the agreement pattern is for the same person than for different people). Auto-filing needs W ≥ 4 bits **and** an exact birth date **and** a matching family name; W ≤ −6 is rejected; anything in between goes to Dr. Hofer. On 3,000 held-out synthetic pairs: **0 wrongly filed**, 0.07 % wrongly rejected, 8 % sent to review, AUC 0.9999 ([core/METRICS_matching.md](core/METRICS_matching.md)). On 17 jury-style documents (other labs, German labels, missing or wrong LOINC codes, wrong patient, namesake, name typo): **0/17 wrongly filed**, 14 exactly as expected, 3 more sent to review, the safe side. Every catch is logged as `misdelivery_caught` with M1/M2/M3, and Dr. Hofer is warned without the other patient ever being named.
### 5. Where does the service run?
Mostly at the clinic. Only the link page and the answer form face the internet, and the outside organisation runs nothing.

| Part | Runs at | Sees patient data |
|---|---|---|
| Matrix (Synapse), bot, request and intake logic, `core/` (patient check, FHIR building), HAPI, audit log, SQLite | Clinic, inside its network | Yes. The clinic is the controller, and the data stays there. |
| Portal: link page, eID login, answer form | Internet-facing. Prototype: hosted by us. Production: the clinic's DMZ, or a third-party trust provider such as FTAPI SubmitBox | Nothing before the identity check. After it: the requested patient's name and birth date, the request, and the uploaded answer in transit. |
| Email / SMS delivery | Any SMTP relay or SMS gateway | No: recipient and link only |
| ID Austria / eIDAS eID | The eID provider | No: it only sees that the person logs in to the service |
| Outside organisation | Nothing to install: a browser and their eID | Only the request addressed to them, after identity |

In the prototype, one FastAPI process serves the portal and the clinic side (`app/main.py`). The split above is the boundary we built for (`Channel.send(to, link)` and `EidAssertion`, see [Every component is replaceable](#every-component-is-replaceable)); it is not yet two separate deployments.

Data protection, as designed (a design, not a legal assessment; a DPIA would come before production):
- **Minimisation.** Emails and SMS carry only the link and the clinic name; `tests/test_template_leak.py` fails if a template contains a patient name, birth date or document-type word. The audit log stores contacts masked (`e***@labor-kanal.example`), and for a wrong-patient answer (M3) only match scores, never the other patient's name or birth date.
- **Roles.** The clinic is the controller. Whoever hosts the portal or delivers the messages (us, FTAPI, an SMS gateway) is a processor and needs a processor agreement (Art. 28 GDPR).
- **Retention.** Production needs retention periods per kind of record, starting with deleting quarantined answers once Dr. Hofer has dealt with them; the prototype keeps everything.
- **Accountability.** The audit log is append-only with a SHA-256 hash chain: editing a row, or deleting one before the newest, breaks `verify_chain()`. Tampering becomes visible; keeping the latest hash outside the database as well would also expose a cut-off tail. In production the `/audit` page sits behind the clinic login.

## Every component is replaceable
Each simulated part sits behind one small interface. Swapping it touches the file named in the right column, not the rest.

| Simulated / chosen here | Production replacement | Interface that stays the same |
|---|---|---|
| Mailpit (catches emails) | Any SMTP relay | `Channel.send(to, link)` in `app/delivery/base.py`; `smtp_mailpit.py` only needs `SMTP_HOST` / `SMTP_PORT` changed |
| SMS inbox page (`/sms`) | An SMS gateway | `Channel.send(to, link)`; a new `Channel` with `kind = "sms"` replaces `sms_inbox.py` |
| Mock eID, *DemoID* (`identity/eid_mock.py`) | ID Austria via OIDC | `EidAssertion` returned by `eid_mock.verify()`: name, birth date, pseudonym (bPK), level of assurance. The portal consumes only this object. |
| HAPI FHIR server | Any FHIR R4 server | `app/fhir_client.py` uses plain FHIR REST (read Patient, create Task, `$validate`, transaction) |
| Our own upload portal + Mailpit | A secure-transfer provider such as FTAPI SubmitBox | `Channel.send(to, link)`; `EMAIL_CHANNEL` selects the channel. **Not used in the prototype.** FTAPI states that a REST API exists but publishes no reference (access is licence-gated), and we did not invent endpoints. `app/delivery/ftapi_submitbox.py` marks where the adapter goes. |
| Synapse + Element | Any Matrix homeserver and client, or PGK | `bot.py` speaks the Matrix client-server API (matrix-nio) and calls `commands.handle(text, sender)` |
| SQLite | Postgres | Only `app/db.py` imports `sqlite3` |

## Metrics
See [METRICS.md](METRICS.md) (generated by `make metrics`) and [core/METRICS_matching.md](core/METRICS_matching.md).

| Track metric | Result | Target |
|---|---|---|
| FHIR validation (HL7 validator) | 0 errors on both scenario bundles | 0 |
| Outside person: installs / accounts | 0 / 0 (a link and an eID in the browser) | 0 / 0, under 2 min |
| Misdeliveries caught | 3/3 | 3/3 |
| Audit coverage | 6/6 steps with who, what, when; hash chain intact | 6/6 |
| Patient data in email/SMS | 0 in 24 emails and 5 SMS | 0 |

## What works / what doesn't

**Works**
- The whole flow on the scenario: request in one sentence → neutral link → eID → upload (PDF, Markdown, text, photo with read-back) → valid FHIR on HAPI → message in Matrix.
- All three misdelivery tests (M1 warned before sending and blocked at login, M2 blocked, M3 quarantined without naming the other patient), each logged.
- Audit log with all 6 required events and a SHA-256 hash chain; `/audit` page in English and German.
- HL7 validator: 0 errors on both scenario bundles.

**Simulated or not built**
- ID Austria is simulated (*DemoID*); production uses the OIDC login. People without any eID can't answer this way; for them the existing route stays.
- FTAPI SubmitBox is not wired (no public API reference); the adapter boundary is there.
- Each answer creates a new Practitioner and Organization without an identifier (no de-duplication). No retention or deletion of stored answers yet.

## Team
See [TEAM.md](TEAM.md).
