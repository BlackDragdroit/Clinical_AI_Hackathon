# Metrics (scenario)

Measured on the running stack (`make up`, then `scripts/dev/flow.sh r1 r2 m1 m2 m3`), written by `make metrics`. Synthetic data only.

| Metric | Result | Target |
|---|---|---|
| FHIR validation (HL7 validator) | not run on this machine: `make validate` (MedEng: 0 errors on both scenario bundles, PR #12) | 0 |
| Outside person: installs / accounts / time | 0 / 0 by design (link + simulated ID Austria in the browser) / time: not measured yet | 0 / 0 / < 2 min |
| Misdeliveries caught | 3/3 | 3/3 |
| Audit coverage | 6/6 steps with who, what, when; hash chain intact (191 entries) | 6/6 |
| Patient name, birth date or document type in email/SMS | 0 in 24 emails and 5 SMS | 0 |
| Jury-style documents (MedEng: other labs, wrong patient, namesake, typos) | 0/17 wrongly filed (95 % upper bound 19.5 %); 14/17 exactly as expected, 3 more sent to review (the safe side) | 0 wrongly filed |

## Misdelivery tests (scenario/misdelivery.md, on request 1)

| Test | Caught | Harm (M1/M2: anything shown; M3: anything filed) |
|---|---|---|
| M1 wrong address (labor-kanaI) | 4 runs | 0 |
| M2 forwarded to a colleague | 4 runs | 0 |
| M3 document of another patient | 6 runs | 0 |

## AI engine (synthetic held-out set, see eval/RESULTS.md)

| What | Result |
|---|---|
| Requests, rules only | 70.0 % [64.6, 74.9] (210/300) fully correct · 0 wrong patients · 5 silent errors |
| Requests, rules + Qwen3-1.7B (CPU) | 81.7 % [76.9, 85.6] (245/300) fully correct · 0 wrong patients · 5 silent errors |
| Answers as MD (synthetic, same format as the scenario) | read 120/120 · wrong value filed 0 · wrong patient filed 0 |
| Answers as PDF (synthetic, same format as the scenario) | read 120/120 · wrong value filed 0 · wrong patient filed 0 |

Matcher calibration and CIs: core/METRICS_matching.md. Stopwatch sheet: metrics/stopwatch.csv.
