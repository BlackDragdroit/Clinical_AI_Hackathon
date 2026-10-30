# AI engine: what to say (video, metrics slide, Q&A)

All numbers are on synthetic data and reproducible with `make engine-eval`; details in eval/RESULTS.md, eval/VOICE.md.
"Held-out" = 300 requests written by a separate model run that never saw our code or templates.

## 30 seconds in the video
1. Dr. Hofer writes or says one sentence in Element: *"Bitte bei Dr. Eva Brandl … die Gerinnung von Frau Maria Beispiel, geb. 12.3.1961, anfordern."* The bot answers with the same confirmation card as `!anfrage`. Nothing is sent without `!senden`.
2. **The model can only copy, never invent:** every value must occur in her sentence or it is dropped. *(NuExtract3 tried to invent a value once in 100 requests; Qwen3 73 times. All were dropped.)*
3. **Two identifiers or the bot asks back.** Name + birth date, ranked by our Fellegi–Sunter matcher. **0 wrong patients** in every run.
4. **The lab answers with whatever it has:** Markdown or a PDF from the lab system is read exactly; a phone photo is read by two OCR readers and the **sender confirms the values on a read-back screen**, as with a phoned-in critical value.
5. Dr. Hofer's message says whether she got what she asked for: *"4/4 angefragte Parameter · Probe vom 22.10.2026 · Werte plausibel"*.
6. Self-hosted open models on one GPU in Vienna; no document leaves our infrastructure. The EU option (Mistral) is measured, not assumed.

**Say what does not work yet:** speech-to-text on the laptop CPU loses most e-mail addresses and phone numbers (the bot asks back, and contacts from voice are always flagged); OCR and speech-to-text on the GPU were not measured (the text model uses the GPU's memory).

## Metrics slide
| | Result |
|---|---|
| Requests, held-out 300, rules only | 70 % fully correct [65, 75] |
| + small model on a laptop CPU (Qwen3-1.7B, rules first) | **82 % [77, 86]** |
| Same 100 requests: + Ministral 8B (EU, GPU) / NuExtract3 / Qwen3 / Ministral 3B (EU) | 87 % / 86 % / 83 % / 80 % (CIs overlap) |
| Wrong patient picked | **0** (600 dev + 300 held-out, every model) |
| Silent errors (card ready, wrong, not flagged) | 5 / 300 (1.7 %) |
| Answers as Markdown and as PDF (120 each) | 120/120 read, **0 wrong values filed** (≤ 3.0 %), 16/16 wrong-patient documents rejected |
| Planted problems caught in answers | old sample 13/13, implausible value 9/9, 0 false alarms |
| Voice on CPU (synthetic speech) | 23–30 % fully correct vs 40–45 % on the same text; 0 wrong patients |
| GPU: Ministral 3 8B (EU) on one A5000, held-out 300 | **85 % [80, 88]** fully correct, 0 wrong patients, 6 silent errors (2.0 %); **1.8 s** per request (p95 2.0 s) vs 22 s on the laptop CPU |

## Q&A one-liners
- **Is the AI a medical device?** It does not decide anything clinical: it copies fields from text the sender or doctor wrote; the rules and the doctor's confirmation decide.
- **What if the model hallucinates?** It cannot get a value through: every string must be a slice of the input (we count the attempts), contacts must agree with the rules or the bot asks back.
- **Why not one big model?** Measured: a 4B extraction model on a CPU already reaches 86 %, and the rules plus two identifiers keep wrong patients at 0. Smaller means it runs on a clinic's own hardware.
- **Why Mistral?** Measured, not assumed: on the same 100 held-out requests Ministral 3 8B ties NuExtract3 (87 % vs 86 %, 2 silent errors each, exact McNemar p = 1.0) and answers in 1.8 s on one GPU, so the EU model runs the demo. The 3B model alone was weaker (44 %).
- **Data protection?** Self-hosted models (Exoscale Vienna or the clinic's own GPU); voice notes are deleted after transcription, only a hash is audited.
- **Where does the test data come from?** Synthea patients and lab values, Austrian names, ELGA's lab code list; the held-out requests were written independently of our code. No real patient data anywhere.
