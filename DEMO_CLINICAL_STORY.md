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
