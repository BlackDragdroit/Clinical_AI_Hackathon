# Real reference data (no patients)

Research done on 2026-10-30. Hackathon rule: only synthetic patients. Everything below is reference data that contains no patient records: terminologies, name statistics, layout conventions and fictional sample documents. Files are in `eval/data/external/` (about 52 MB in total). The raw files are large (the biggest is 28 MB), so keep them out of git and commit only the compact CSVs.

Legend: **[verified]** means the page or file was opened and checked. **[unverified]** means it was not confirmed and should be checked before you rely on it.

---

## 1. Austrian lab terminology: ELGA_Laborparameter (LOINC with German display names)

| | |
|---|---|
| Page | https://termgit.elga.gv.at/ValueSet-elga-laborparameter.html (download links: `…/ValueSet-elga-laborparameter.download.html`) |
| What | ValueSet `elga-laborparameter`, OID 1.2.40.0.34.10.44, **version 1.11.0+20260910**, status active, publisher ELGA GmbH. It has **7,929 concepts**: about 7,000 LOINC codes (LOINC 2.83) plus about 900 ELGA supplement codes (`V…`, CodeSystem `elga-laborparameterergaenzung` 1.8.0). Each concept has a short German display (the Vienna Gesundheitsverbund catalogue), often a longer `de-AT` designation, `einheit_codiert` (UCUM) and `einheit_print` (the unit as printed), and it sits in a hierarchy of sections such as Hämatologie > Blutbild or Gerinnung/Hämostaseologie > Globaltests. [verified] |
| Formats | FHIR R4 JSON/XML, FSH, ClaML, propCSV (`;`-separated), XLSX, SVSextELGA (deprecated) and outdatedCSV. All are mirrored on public GitLab (`gitlab.com/elga-gmbh/termgit`, commit `966113e6…`) and on the Tergi FHIR server `https://tergi.elga.gv.at/fhir-server/api/v4/ValueSet/elga-laborparameter`. |
| Licence / terms | ELGA provides the terminologies free of charge ("unentgeltlich") with no warranty. The terms also say that **downloaded content may not be changed when reused**, and the licence of each terminology still applies (here the LOINC licence, see item 2). The termgit download page asks you to tick a terms checkbox. I took the files straight from the public GitLab raw URLs and kept them byte-identical. Our extract below is a separate derived file that names its source; it does not replace the ELGA file. |
| Downloaded | `eval/data/external/elga/ValueSet-elga-laborparameter.4.fhir.json` (17.8 MB) and `…1.propcsv.csv` (4.3 MB), both unmodified. |
| Extract | **`eval/data/external/elga_lab_loinc_de.csv`**, 127 common parameters, all LOINC with valid check digits. Columns: `code, display_de, unit (UCUM), source, display_de_long, unit_print, system, panel, elga_section, inactive`. Panels: coagulation (11), cbc (25), kidney (9), electrolytes (11), liver (11), pancreas_muscle (5), inflammation (4), glucose (6), lipids (8), thyroid (3), cardiac (4), iron (5), vitamins (4), tumor_markers (2), blood_gas (5), urine (11), other (3). I built it with a throwaway script that is not in the repo: it walks the FHIR `expansion.contains` tree, picks a hand-chosen list of LOINC codes, and copies the designations unchanged. |

**Findings that affect our engine**

- **ELGA does not contain 3 of our seed codes.** `6690-2` Leukozyten, `789-8` Erythrozyten and `4544-3` Hämatokrit are absent from the whole value set. ELGA uses the method-less codes **`26464-8` Leukozyten, `26453-1` Erythrozyten and `20570-8` Hämatokrit** (20570-8 is "by calculation"). It also uses `30428-7` MCV, `28539-5` MCH and `28540-3` MCHC. Austrian documents will carry these codes, so `core/loinc.py` should treat both families as synonyms.
- **Quick is in %, not seconds:** `5894-1` "PTZ (Prothrombinzeit)" in **%**. Our seed `5902-2` is the same PTZ in **s** (printed "sek"). Austria also has the Owren methods: `52753-1` **Normotest** % and `52761-4` PTZ n. Owren %. INR is `6301-6` with UCUM unit `1` and no printed unit.
- **Units as printed:** aPTT and Thrombinzeit print as `sek`. TSH is UCUM `u[iU]/mL` but prints as `µU/mL`. Cell counts print as `10^9/L` and `10^12/L`. Creatinine, glucose, cholesterol, uric acid and bilirubin are in **mg/dL**. A µmol/L variant also exists, e.g. `14682-9` Kreatinin.
- **eGFR:** `62238-1` CKD-EPI, `33914-3` MDRD and `98980-6` CKD-EPI 2021 (creatinine plus cystatin C). All print as `mL/min/1.7m2`.

**Uses:** (a) Replace or extend `core/loinc.KNOWN` and `engine/lexicon.PANELS` with the CSV, and build the synonym list from `display_de` and `display_de_long` (e.g. "PTZ", "Normotest", "Thrombozyten /B"). (b) Add `unit_print` variants (`sek`, `µU/mL`, `10^9/L`) to the `PLAUSIBLE` unit groups. (c) Let the synthetic lab generator pick codes, names and units from this table so that test documents carry real Austrian displays.

## 2. LOINC itself, and validating codes without an account

- **Full LOINC:** https://loinc.org/downloads (opened with curl; WebFetch gets a 403). **LOINC 2.83, released 2026-08-19, file `Loinc_2.83.zip`, 88.52 MB, MD5 `057ddf203164705d5a4c3604257060a4`.** The page says *"You must be logged in with your LOINC username and password"*. The account is free. There is also a download API for automated retrieval, which needs the same account. Releases move from every six months to monthly in 2027. [verified] **No account was created and nothing was downloaded.**
- **German (Austria) variant:** loinc.org/international lists **German (Austria), de-AT, ID 24, "Translated by ELGA, Austria"**. German (Germany) is de-DE, ID 15, translated by FAU Erlangen for BfArM. [verified] By LOINC's naming rule `xxYY##LinguisticVariant.csv` the file should be **`AccessoryFiles/LinguisticVariants/deAT24LinguisticVariant.csv`** inside the zip [unverified: inferred from the naming rule, I did not open the zip].
- **Licence** (https://loinc.org/kb/license): free in perpetuity for commercial and non-commercial use. Every copy must include the copyright notice, the licence and the version number. You may not change field contents. Local codes you add must start with `X`. The Linguistic Variants files are "Group 3 artifacts" (their field contents may not be changed). LOINC codes and names may appear in messages without the notice. [verified]
- **LOINC's own FHIR server** `fhir.loinc.org` answers 302 to `auth.loinc.org`, so it needs a login. [verified]
- **tx.fhir.org works without a login** and serves LOINC 2.83, including **de-AT designations**. [verified]

```bash
# lookup: display, status, all designations (de-AT = "LinguisticVariantDisplayName")
curl -H "Accept: application/fhir+json" "https://tx.fhir.org/r4/CodeSystem/\$lookup?system=http://loinc.org&code=6301-6&displayLanguage=de-AT"
#  -> display "International normalized ratio (INR)"; en-US "INR in Platelet poor plasma by Coagulation assay"
# validate a code (+ optional display)
curl -H "Accept: application/fhir+json" "https://tx.fhir.org/r4/CodeSystem/\$validate-code?url=http://loinc.org&code=6301-7"
#  -> result=false, "Unknown code '6301-7' in the CodeSystem 'http://loinc.org' version '2.83'"
curl -H "Accept: application/fhir+json" "https://tx.fhir.org/r4/CodeSystem/\$validate-code?url=http://loinc.org&code=718-7&display=H%C3%A4moglobin&displayLanguage=de-AT"
#  -> result=true, display "Hämoglobin"
```

tx.fhir.org is HL7's public **test** server. It has no SLA, so use it offline to build or check tables and never call it at runtime during the demo. **Uses:** (a) Add a one-off script that checks every code in `KNOWN`, the CSV and the generated test data against tx.fhir.org and records the de-AT display. (b) Fill `name_matches` synonyms with the de-AT display (e.g. 5894-1 gives "PTZ (Prothrombinzeit)").

## 3. Names for synthetic patients

| Source | Content | Licence | Status |
|---|---|---|---|
| Statistik Austria OGD **`OGDEXT_VORNAMEN_1`**: https://data.statistik.gv.at/web/meta.jsp?dataset=OGDEXT_VORNAMEN_1 | First names of live births by year (**1984–2025**), political district and sex. Columns `C-JAHR-0; C-WOHNBEZIRK-0; C-GESCHLECHT-0 (1=m, 2=w); F-VORNAME_NORMALISIERT; F-ANZAHL_LGEB`. 1.34 million rows, 3.21 million births. Last updated 2026-07-09. [verified] | **CC BY 4.0** (cite "Statistik Austria") | Downloaded: `eval/data/external/statistik_austria/OGDEXT_VORNAMEN_1.csv` (28 MB) plus the header and sex code files |
| Derived | **`eval/data/external/at_first_names_top50_by_decade.csv`**: top 50 per sex for each birth decade 1980s–2020s, with count and share | CC BY 4.0 (derived) | Saved |
| Land Steiermark, "Männliche Vornamen – Ranking nach Jahrzehnten seit den 1910er Jahren" (PDF, data from Statistik Austria) | Top 10 boys' names per decade. The 1930s–1960s are dominated by Franz, Johann, Josef, Karl, Peter, Alois, Walter, Rudolf, Helmut, Gerhard, Manfred and Wolfgang. [verified] | Not stated | Not downloaded. I could not find the matching girls' table. [unverified] |
| Surnames | **Statistik Austria publishes no surname ranking** (I searched and found none). The best public list is telefonabc.at/haeufigste-nachnamen.aspx (phone-directory counts, undated, no licence): Gruber, Huber, Wagner, Müller, Pichler, Moser, Bauer, Steiner, Mayer, Berger, Hofer, Leitner, Fuchs, Eder, Schmid, Winkler, Fischer, Weber, Schneider, Schwarz | Unknown | Not downloaded. A list of 20 names is a fact; quote it with attribution |

**Uses:** (a) Sample first names by sex and birth decade. Our patients are mostly born 1935–1965 and the OGD data starts in 1984, so use the Steiermark decade list (plus traditional names such as Maria, Anna, Theresia, Johanna and Elfriede for women [unverified]) for older patients. (b) Draw surnames from the top-20 list mixed with rarer real-looking names, and include hard cases for matching: hyphenated names, umlauts (Müller/Mueller), and `ß` vs `ss`. (c) Keep a fixed seed so the test sets stay reproducible.

## 4. How Austrian lab reports look: rules for synthetic documents

Sources [all verified]:
- **S1**: gesundheit.gv.at sample report `Laborbefund.pdf` (https://www.gesundheit.gv.at/dam/jcr:f497f826-378e-457d-8803-46b47728a0a5/Laborbefund.pdf). Fictional: "MUSTERMANN Max", "Prim. Univ.-Prof. Muster Mann", Mosaikstraße 1, A-1111 Wien, phone 12345-67890. Viewed but **not saved**, because its licence is unknown.
- **S2**: ELGA's fictional CDA example documents, `gitlab.com/elga-gmbh/cda/beispielbefunde`, **MIT licence**. Saved to `eval/data/external/elga_cda_examples/`: `Lab_Allgemeiner_Laborbefund_v3.xml` (current Labor- und Mikrobiologiebefund 3.0.0), `ELGA-043-Laborbefund_…_v2.06.2.xml`, `ELGA-023-Entlassungsbrief_aerztlich_…_v2.06.2.xml` and `LICENSE_MIT.txt`. The people in them are invented ("Sorgenvoll", "Mustermann").
- **S3**: gesundheit.gv.at "Normalwerte" page (https://www.gesundheit.gv.at/labor/laborbefund/normalwerte, updated 2026-04-30).
- **S4**: ELGA value set ELGA_ObservationInterpretation 1.3.0 (termgit).
- **S5**: labors.at lecture "Notfallbefunde in der Praxis" (2024, slides only).

**Rules**
1. **Header (S1):** letterhead with lab name, "Vorstand: Prim. Univ.-Prof. Dr. …", street, `A-1111 Wien` and `☎ +43 (0)1 …`. Then "An: Einsender", the patient as **`NACHNAME Vorname`**, `geb.: 31.10.1967 (M)`, `Zuweisung vom: 14.10.09/ 19:24`, `Befunddatum: 24.10.09/ 21:29` (two-digit year), `Patientenzahl`, `Labornummer`, `Kostenstelle`, `Diagnose:` and `Seite 1/3`. The header block repeats on every page, and the old footer carries `DVR: 0000191`.
2. **Sample block (S2 v3, table "Probeninformation"):** `Material-ID | Probenentnahme | Untersuchtes Material | Probenentnahme durch | Probeneingang | Bemerkung Labor`, e.g. `01.06.2021 06:35 … 01.06.2021 08:15 … leicht hämolytisch`. The ELGA stylesheet uses gender-inclusive labels: **"Zuweiser:in"**, **"Auftraggeber:in"**, **"Validiert durch:"**, **"Unterzeichnet von:"** and "Aufnahmezahl:".
3. **Sections, in ELGA order (S2):** Hämatologie (Blutbild, Differentialblutbild), Gerinnung/Hämostaseologie, Klinische Chemie/Proteindiagnostik, Hormone/Vitamine/Tumormarker, Allergiediagnostik, Infektionsserologie, Urin. At the end come "KOMMENTAR" or "Befundbewertung". S1 uses CAPS sub-headings such as `KLINISCHE CHEMIE / SERUM`, `ROTES BLUTBILD`, `WEISSES BLUTBILD`, `DIFFERENTIALBLUTBILD` and `GERINNUNG`.
4. **Columns:** S2 uses `Analyse | Ergebnis | Einheit | Referenzbereiche | Interpretation`, sometimes with `Delta` and `Externes Labor` (marked "E"). S1 uses `Analyse | <Wert> | Einheit | Normwerte`.
5. **Reference ranges:** `135-150`, `<35`, `>35.0`, `<0.50` and `0.50-1.20`, using a hyphen with no spaces. Qualitative results show `negativ` as the reference and `---` as the unit. **Footnote digits get glued to the text:** `INR | 1.11)` means 1.1 with footnote 1, and `4.6-18.72)` means 4.6–18.7 with footnote 2. Our parser must not read these as 1.11 or 18.72.
6. **Flags:** a **`+`/`-`** in an Interpretation column (S2), or **prefixed to the value** (S1: `+ 8.2`, `+ positiv`). S2 also uses `++`/`--` for strong deviations, `A` for an abnormal qualitative result and `RAST 3` for allergy classes. S3 adds that results may be bold or coloured, or marked with an arrow. The FHIR codes (S4) are `H`, `L`, `HH`, `LL`, `A`, `AA`, `N`, `POS`, `NEG`, `<`, `>`, `U` and `D` (German displays: "oberhalb des Referenzbereiches" and so on). A pending result reads **`Wert folgt`**.
7. **Decimal separator: both appear.** The tables in S1 and S2 use a **decimal point** (`0.68`, `16.9`). Prose uses a **comma** (S5 `<2,5 mmol/l`; GraSCCo, item 5). A point can also be a thousands separator (GraSCCo `2.800mg`). Generate all three variants and test the parser on `2.800` vs `2.8`.
8. **Units as printed (S1, lower-case l):** `U/l`, `mg/dl`, `mmol/l`, `µg/dl`, `ng/ml`, `µIU/ml`, `fl`, `pg`, `sec`, `T/l` (erythrocytes), and **`g/l` for leukocytes and platelets, meaning G/l (10^9/l)**. The case of g/G is unreliable, so the cell-count unit has to be resolved from context, not from case. Hb is `g/dl`. Electrolytes, Ca, Mg and P are in `mmol/l`. CRP is in `mg/l` (S1, S2). Some labs print CRP in mg/dl [unverified]. Coagulation is reported as **`Normotest %` or `PTZ/Quick %`**, with INR next to it and footnoted "nur gültig bei oraler Antikoagulation" (S2).
9. **Names on reports (S1):** `GOT`/`GPT` rather than AST/ALT, `Alk. Phosphatase`, `Chloride`, `Phosphor`, `Gesamteiweiß`, `Triglyzeride` and `Segmentkernige`. Names can be **truncated at about 30 characters** ("Thyroidea Stimulierendes Hormo"), so fuzzy name matching has to tolerate truncation.
10. **Discharge letters (S2 ELGA-023):** sections include Aufnahmegrund, Diagnosen bei Entlassung, Durchgeführte Maßnahmen, Empfohlene Medikation (`Arzneimittel | Einnahme | Dosierung | Hinweis`, dosing written as **`1-0-0-0`**), Termine/Kontrollen, Zusammenfassung des Aufenthalts, Allergien, Erhobene Befunde (with lab tables, e.g. `Quick (Prothrombinzeit) 65 % 70-150 -`, `aPTT 57.0 s 26.0-40.0 ++`) and Vitalparameter.

ÖQUASTA: its public material is limited to external quality schemes (which include PTZ, INR, aPTT, TZ, fibrinogen and AT III). I found **no public layout or unit recommendation** from it [unverified].

**Uses:** (a) Rebuild `eval/render.py` templates on rules 1–9, adding a "messy Austrian LIS" variant (point/comma, `g/l`, prefixed `+`, footnote digits, truncated names). (b) Add parser unit tests for each hazard. (c) Load the ELGA v3 XML as a fixture for a CDA → FHIR path test, since it is fictional and MIT-licensed.

## 5. Dictation conventions and German medical ASR test sets

**Conventions** (sources: Corti Med-Term transcripts [verified], Microsoft Dragon Copilot German command page [verified: only "Neuer Absatz", "Neue Zeile", "Schreib das groß/klein"], GraSCCo counts [verified], Wikipedia "Buchstabiertafel" [verified]; everything else is common practice [unverified]):
- **Spoken commands** are inline words. Med-Term raw text: `… vorgestellt neue Zeile Die Verletzung …`, `… Symptome Punkt Die …`, `neuer Absatz`. Expect also "Komma", "Doppelpunkt", "Klammer auf/zu", "Bindestrich" and "Schrägstrich" [unverified].
- **Numbers and dates:** spoken `zwei Komma fünf` is written `2,5`. `am dritten März zweitausendvierundzwanzig` is written `3. März 2024`. Austrian speakers say **"Jänner"** for January. They also say "viertel neun" (08:15) and "dreiviertel neun" (08:45) [unverified, regional]. "zwo" for zwei is mainly German usage.
- **E-mail:** "at" (pronounced "ät"), "Klammeraffe" or "Affenschwanz" for @, "Punkt", "Bindestrich"/"Minus" and "Unterstrich". Hard names get spelled out. Our `eval/voice_eval.py` prompt already covers "punkt, at, minus". For synthetic addresses use the reserved domains `example.org`, `*.example` and `.test` (RFC 2606).
- **Spelling alphabet:** DIN 5009:2022 (Germany) switched to city names. Austria's ÖNORM A 1081 was **withdrawn in 2019**, and a new Austrian table appeared in the Österreichisches Wörterbuch in 2025 (e.g. "Sarah" replaces "Siegfried", "Zita" replaces "Zürich"). Older speakers still use the classic names (Anton, Berta, Cäsar, Dora, Emil, …) [list unverified].
- **Phone numbers:** digits grouped in pairs or triples ("null sechs sechs vier …"), country code spoken as "plus vier drei". I found **no RTR range reserved for fictional numbers** [unverified], so make synthetic numbers obviously fake, e.g. `+43 1 23456-789`, the way S1 does.
- **Abbreviations (counts in the 62 GraSCCo letters):** `bds.` 65, `Pat.` 48, **`Z.n.` 41 + `Z. n.` 11**, `re.` 33 / `li.` 27, `o.B.` 17 + `o. B.` 9, **`St.p.` 15 + `St. p.` 5**, `p.o.` 14, `s.c.` 12, `DD` 10, **`V.a.` 7 + `V. a.` 3**, `i.v.` 6. In speech these are usually expanded: "Verdacht auf", "Zustand nach", "Status post", "ohne Befund", "Differentialdiagnose", "beidseits" [unverified for speech]. Normalise both the spaced and unspaced written forms.

**Test sets**

| Dataset | Content | Licence | Status |
|---|---|---|---|
| **Corti Med-Term** `huggingface.co/datasets/corti/med-term` | **Fully synthetic TTS** German/English/French medical dictation, 200 clips per language (German about 28–170 s each), 20 voices. Includes spoken-form and formatted transcripts, plus medical and formatting term lists. "No real patient data. No PHI." Not gated. [verified] | Corti ASR Evaluation Dataset Licence = CDLA-Permissive-2.0 plus a use-restrictions addendum: **evaluation and benchmarking only, no training or fine-tuning**, no voice cloning, no clinical use. Danish law. | **Not downloaded**: German parquet is 234 MB (over the 50 MB cap). Stream it via `datasets` into the voice cache (`load_dataset("corti/med-term","de")`) |
| **GraSCCo** (Zenodo 10.5281/zenodo.6539131, v1 2022) | 62 synthetic German/Austrian discharge-style letters ("all names and dates are purely fictional"), from Med Uni Graz. Text only. [verified] | **CC BY 4.0** (cite Modersohn et al. 2022). Creator's note: not medically plausible. The PHI-annotated version is Zenodo 11502329, also CC BY 4.0 | **Downloaded**: `eval/data/external/grascco/` (62 files, 372 KB) |
| MultiMed `huggingface.co/datasets/leduckhai/MultiMed` | Real-world medical speech in 5 languages, German included. MIT on the dataset card | MIT on card [the origin of the audio and whether it is free of patients are unverified] | Not downloaded. **Do not use until checked**: it is real speech |
| Common Voice DE (CC0) / TuDa (CC BY) | General German, not medical | Open | Not downloaded |
| Shaip / Macgence German medical dictation | Commercial | Paid / request form | Not usable |

**Uses:** (a) Run our ASR backends on Med-Term `de` (eval only) and report WER on `medical_terms`, comparing against `transcription_formatted` to measure our number and date normalisation. (b) Feed GraSCCo sentences through Piper TTS (`eval/tts.py`) to get Austrian-flavoured dictation, and as realistic text for the discharge-report templates. (c) Add an abbreviation and spoken-form table (V.a., Z.n., St.p., o.B., Jänner, "Komma", "Punkt", "at") to the request normaliser.

---

## Files saved (`eval/data/external/`)
- `elga/ValueSet-elga-laborparameter.4.fhir.json`, `elga/ValueSet-elga-laborparameter.1.propcsv.csv`: ELGA value set 1.11.0, unmodified
- `elga_lab_loinc_de.csv`: 127-row extract (derived)
- `statistik_austria/OGDEXT_VORNAMEN_1.csv` (+ `_HEADER.csv`, `_C-GESCHLECHT-0.csv`): CC BY 4.0
- `at_first_names_top50_by_decade.csv`: derived
- `elga_cda_examples/*.xml` + `LICENSE_MIT.txt`: fictional ELGA CDA lab and discharge examples, MIT
- `grascco/*.txt`: 62 synthetic letters, CC BY 4.0

## Not verified / open
- The `deAT24LinguisticVariant.csv` path inside the LOINC zip (inferred from the naming rule).
- The girls' decade ranking for older cohorts; an official Austrian surname statistic (none found).
- ÖQUASTA layout or unit recommendations; CRP in mg/dl at specific labs; any RTR range of fictional phone numbers; the current Austrian spelling-alphabet word list.
- The origin of MultiMed's audio.
- The ELGA "no modification" clause: our CSV extract is clearly marked as derived. If in doubt, ship only the unmodified ELGA file and build the extract at runtime.
