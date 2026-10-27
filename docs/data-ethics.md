# Data ethics

## Hackathon data rule

Only synthetic or de-identified data. No real patient data in the repo, in issues, in PRs or on the public HAPI server (it is readable by everyone).

## Data provenance

- `data/synthetic/patients_sample.csv`: hand-written fictional rows ("Test Patient N").
- `data/synthetic/synthea/`: generated with Synthea (pinned version in `scripts/generate_synthea.py`), gitignored.

## To complete on site (tie to the use case)

- **GDPR:** legal basis, data minimisation, pseudonymisation vs anonymisation, data subject rights.
- **EU AI Act / MDR:** risk class of the intended use, medical device qualification, human oversight, transparency.
- **EHDS:** primary vs secondary use, interoperability requirements, relation to the chosen FHIR profiles.
- **Bias and limits:** representativeness of the data, failure modes, who is affected.
