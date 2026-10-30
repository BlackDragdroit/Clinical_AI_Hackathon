# Clinical story for the video

Voice-over for the 2-minute video. Record it in German; the English text is for subtitles and the README.
About 200 words each, which is about 90 seconds spoken, leaving room for the screens.

## Deutsch

Dr. Lena Hofer, Innere Medizin am Klinikum Beispielstadt. Maria Beispiel hat einen Eingriff vor sich. Vorher braucht Dr. Hofer die Gerinnungswerte. Die liegen in einem Labor außerhalb ihres Netzwerks.

Heute heißt das: Das Labor faxt oder schickt eine E-Mail. Jemand tippt die Werte von Hand ab. Und eine falsch adressierte E-Mail landet bei Fremden, mit Name und Befund.

Mit BefundBrücke schreibt Dr. Hofer einen Satz in Matrix. Dr. Eva Brandl bekommt eine neutrale E-Mail: kein Name, kein Befund, nur ein Link. Sie meldet sich mit ID Austria an. Erst dann sieht sie, um wen es geht. Sie lädt den Befund hoch.

Die Werte landen als strukturierte Laborwerte mit LOINC-Code bei der richtigen Patientin, mit dem Nachweis, wer sie geschickt hat. Dr. Hofer bekommt die Meldung in Matrix.

Drei Dinge gehen im echten Leben schief. Ein Tippfehler in der Adresse: Wir warnen vor dem Senden. Eine weitergeleitete E-Mail: ID Austria weist den Kollegen als jemand anderen aus, er sieht nichts. Der Befund eines anderen Patienten: Er wird nicht abgelegt. Dr. Hofer erfährt davon, ohne dass der andere Patient genannt wird.

Das gewinnt die Klinik: kein Abtippen, kein Fax, und ein Protokoll jedes Schritts.

Eine ehrliche Grenze: Wer keine eID hat, kann so nicht antworten. Für diese Fälle bleibt der bisherige Weg.

## English

Dr. Lena Hofer, internal medicine at Klinikum Beispielstadt. Maria Beispiel is due for a procedure. Before it, Dr. Hofer needs her coagulation values. They sit in a lab outside her network.

Today that means: the lab faxes or emails. Someone types the values in by hand. And a misdirected email reaches a stranger, with the name and the result.

With BefundBrücke, Dr. Hofer writes one sentence in Matrix. Dr. Eva Brandl gets a neutral email: no name, no result, just a link. She logs in with ID Austria. Only then does she see who it is about. She uploads the result.

The values arrive as structured, LOINC-coded lab results on the right patient, with proof of who sent them. Dr. Hofer is told in Matrix.

Three things go wrong in real life. A typo in the address: we warn before sending. A forwarded email: ID Austria shows the colleague is someone else, and he sees nothing. Another patient's result: it is not filed. Dr. Hofer is told, without the other patient being named.

What the clinic gains: no retyping, no fax, and a record of every step.

One honest limit: someone with no eID can't answer this way. For them, the old route stays.

## Shot list

| Seconds | Screen | Shows |
|---|---|---|
| 0–10 | Title card: "Heute: Fax, E-Mail, abtippen" | The problem |
| 10–22 | Element, Dr. Hofer's room: `!anfrage labor …`, draft card, `!senden` | One sentence, one confirmation |
| 22–30 | Mailpit: the email, zoom on the text | No patient, no document type |
| 30–42 | Link page (neutral sentence) → simulated ID Austria page → Dr. Eva Brandl | Identity before anything is shown |
| 42–52 | Answer form with the patient revealed; name, birth date, upload; receipt | Need-to-know, answer in the browser |
| 52–64 | Element ✅ message → HAPI: Observation (LOINC, UCUM, reference range), Provenance | Coded values, proof of sender |
| 64–74 | Draft card for `eva.brandl@labor-kanaI.example` with the warning | M1 caught before sending |
| 74–86 | Karl Kollege logs in → "Anfrage nicht für Sie bestimmt" page; ⚠️ in Element | M2 blocked |
| 86–98 | Max Beispiel's result uploaded → neutral receipt; ⚠️ in Element without his name | M3 quarantined |
| 98–110 | `/audit`: 6/6 events, chain intact | The record |
| 110–120 | Closing card: gains + the limit | |

Before recording: the 64–74 s shot needs the address-lint PR (`medeng/address-lint`) merged; without it the draft card shows no warning.

## Demo tips

### M1 shot (seconds 64–74): wrong-address warning

The eID simulation page **preselects Eva Brandl** by default (PLAYTEST O7).
For this shot you are demonstrating that a *typo in the address* is caught **before** sending —
not an identity failure — so you do not reach the eID page at all.

Steps:
1. Start from Dr. Hofer's room in Element.
2. Type `!anfrage labor eva.brandl@labor-kanaI.example …` (capital I, not lowercase l).
3. The draft card appears with a red lint warning: "Möglicher Tippfehler in der Adresse (Zeichenähnlichkeit)".
4. Do **not** type `!senden` — the shot ends on the warning card.
5. Cut to the next shot. The request is still in `draft`; you can `!verwerfen` it after recording.

> ⚠️ Prerequisite: the `medeng/address-lint` PR must be merged before recording (noted in the shot list).

---

### M2 shot (seconds 74–86): forwarded link / wrong person

The eID simulation page preselects Eva Brandl.
For this shot you must pick **Karl Kollege** instead.

Steps:
1. Copy the link from the Mailpit email as usual.
2. Open the link. On the simulated ID Austria page, change the pre-selected person to **Karl Kollege**.
3. Submit. The portal shows "Anfrage nicht für Sie bestimmt" (403); nothing else is revealed.
4. Switch to Element — Dr. Hofer's room should show the ⚠️ identity-failure ping.

---

### M3 shot (seconds 86–98): wrong patient's document uploaded

The eID simulation page preselects Eva Brandl — leave it as-is (she is the correct recipient).

Steps:
1. Complete the identity step as Eva Brandl (the correct person).
2. On the answer form, type the name and date-of-birth fields for **Maria Beispiel** (the requested patient).
3. For the file upload, choose **`scenario/documents/lab-result-max-beispiel.md`** — that is Max Beispiel's lab result, a different patient.
4. Submit. The portal shows the "Nicht zugeordnet" receipt (no tick).
5. Switch to Element — Dr. Hofer's room shows the ⚠️ quarantine ping without Max's name.

> Note: `scenario/documents/rehab-report-maria-beispiel.md` triggers the *doc-type mismatch* path (P1), not M3.
> For the pure M3 shot use the wrong-patient lab file above.

---

### Timings: what to cut if time runs short

| Cut first | Why | Impact |
|---|---|---|
| M2 (74–86 s) | M1 already covers the misdelivery concept | Loses the "forwarded email" angle |
| Audit shot (98–110 s) | Can be shown in a follow-up slide | Loses the chain-of-proof evidence |
| Closing card (110–120 s) | Can be spoken without a screen | Minimal |

Never cut M1, M3 or the HAPI structured-values shot (52–64 s) — they are the three differentiators for the jury.

---

### Common mistakes (from PLAYTEST_REPORT.md findings)

- **O7 – preselected wrong person**: the ID Austria simulation always opens with Eva Brandl selected.
  For M1/M2 you must actively choose the stranger/Karl — easy to miss under time pressure.
- **M1 needs the lint PR merged**: without `medeng/address-lint` the draft card shows no warning and the shot looks broken.
- **M3 wrong file**: uploading `rehab-report-maria-beispiel.md` triggers the doc-type-mismatch path (review ⚠️) rather than quarantine. Use `lab-result-max-beispiel.md` for the genuine M3 story.
- **DOB format on iPhone**: the phone keypad has no dot; typing `12031961` without dots is now handled (fix 1 in PLAYTEST_REPORT.md), but the read-back confirmation step may surprise a presenter who has not seen it — rehearse on a phone.
- **Audit page not behind login in the demo**: `/audit` is public in the prototype. Do not open it while a patient name is visible on screen before you mean to show the audit trail.
- **HAPI cold-start**: the first `$validate` call after a fresh `make up` can take 30–60 s (downloading IG packages). Run `scripts/dev/flow.sh r1` once before recording to warm it up.
