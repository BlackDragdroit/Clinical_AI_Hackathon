# Architecture

## Data flow

```
CSV -> ingest.read_records -> mapping.map_patient -> mapping.to_transaction_bundle
    -> validation.validate_resource -> fhir_client.FhirClient.post_bundle -> FHIR server
                                    -> api  POST /convert  -> ui (Streamlit)
```

`hackathon.pipeline.convert_records` chains mapping, bundling and validation for the script, API and UI. Rows that fail mapping are skipped and reported as `row N: ...` errors.

## Interfaces (stable)

See CLAUDE.md. Summary: `read_records`, `map_patient`, `to_transaction_bundle`, `validate_resource` / `ValidationResult`, `FhirClient.post_bundle` / `search`, `GET /health`, `POST /convert`.

## FHIR version decision

- Target server: public HAPI test server, FHIR R4 (`https://hapi.fhir.org/baseR4`).
- `fhir.resources` 8.x uses R5 by default and ships R4B as a subpackage (`fhir.resources.R4B`, FHIR 4.3.0).
- Decision: use `fhir.resources.R4B`. R4B is the closest available model to R4 and wire-compatible for the resources we use (Patient, Bundle, and most clinical resources). Plain R4 models are only in fhir.resources 6.x/7.x, which we avoided to stay on a maintained pydantic v2 release.
- Caveat: R4B differs from R4 in a few resource areas (for example subscriptions, medicinal products). Re-check if the use case touches those.

## Validation scope

Schema validation via the pydantic models (structure, types, cardinality). Not covered: profiles (e.g. IPS, MII), terminology binding, the HL7 Java validator. Note that `code` fields such as `Patient.gender` are not enum-checked by the library; `map_patient` checks gender explicitly.

## Deliberately left out

Docker, database, authentication, HL7 v2 parsing, terminology services, profile validation. Add only when the use case needs them.
