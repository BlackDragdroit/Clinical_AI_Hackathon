# Decisions

Append one line per decision: what, why, who. Placeholders that still need verifying are marked **VERIFY**.

- core/ is imported unchanged via `app/core_bridge.py` (flat imports put core/ on sys.path). — setup
- Doctor commands go through one function (`commands.handle`) shared by the Matrix bot and `python -m app.cli`, so the flow works without Synapse. — setup
- Matrix notifications go through an outbox table (`matrix_outbox`); the bot drains it, or the console does with `MATRIX_ENABLED=0`. — setup
- Channels receive only `(to, link)`; message texts may use only `link` and `clinic`. That makes Hard rule 1 structural, and a test checks it. — setup
- Mock eID assertion = HMAC-signed JSON with the ID Austria fields (name, birth date, bPK-like pseudonym, LoA). The real path is OIDC; only `eid_mock.py` changes. — setup
- Identity binding: the eID name must equal the expected person's name (titles, case and umlaut spelling ignored). On a mismatch, nothing is revealed, `identity_checked FAILED` + `misdelivery_caught` are logged, and Dr. Hofer is alerted. — setup
- On M3 (reject) the Task goes back to `in-progress` (still waiting for the right document), and the answer is kept in `answers` as quarantined. — setup
- Audit timestamps are UTC; FHIR timestamps are Europe/Vienna (core). — setup
- **VERIFY** `IDENTITY_POLICY_URI` in core/fhir_build.py points at example.org; point it at the README anchor.
- Docker image tags pinned and run on 2026-10-29: synapse v1.120.0, element-web v1.11.85, hapi v7.4.0, mailpit v1.21.5. — SWE 1
- FTAPI is not used in the prototype (the track allows any replaceable product). FTAPI publishes no API reference, so we did not invent endpoints. Uploads go through our own portal; `ftapi_submitbox.py` marks where a provider adapter would go. README tagline and architecture say this explicitly. — SWE 1
- Address lint warns only about near-misses of KNOWN_DOMAINS and never blocks; an unknown domain that resembles none of them gives no warning (we can't know every lab). — MedEng
- Misdelivery codes in the audit log are `M1` / `M2` / `M3`; the human label lives in `app/i18n.py` and says "wahrscheinlich" for M1/M2, because a failed eID can't tell a wrong address from a forward with certainty. — MedEng
- UI texts go through `app/i18n.py` (German default and fallback, English second). Stored texts (`lint_warnings`, audit details) stay German for the record; pages that need another language render from codes (`lint_findings`, `misdelivery_label`). — MedEng
