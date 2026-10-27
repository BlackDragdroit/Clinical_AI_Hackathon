"""Streamlit demo: upload CSV, show mapped FHIR JSON and validation status.

Run with: streamlit run src/hackathon/ui/app.py
"""

import csv
import io
import os

import streamlit as st
from dotenv import load_dotenv

from hackathon.fhir_client.client import FhirClient
from hackathon.pipeline import convert_records

load_dotenv()

st.title("CSV to FHIR demo")
st.caption("Synthetic data only. The public HAPI test server is readable by everyone.")

uploaded = st.file_uploader("Upload a CSV file", type="csv")
if uploaded is not None:
    text = uploaded.getvalue().decode("utf-8-sig")
    records = [
        {k.strip(): (v or "").strip() for k, v in row.items() if k is not None}
        for row in csv.DictReader(io.StringIO(text, newline=""))
    ]
    bundle, result = convert_records(records)
    bundle_json = bundle.model_dump(mode="json", exclude_none=True)

    if result.ok:
        st.success(f"Valid: {len(records)} rows mapped.")
    else:
        st.error("Validation problems:")
        for error in result.errors:
            st.write(f"- {error}")
    st.json(bundle_json)

    base_url = os.getenv("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4")
    if st.button(f"Send to FHIR server ({base_url})", disabled=not result.ok):
        try:
            response = FhirClient(base_url).post_bundle(bundle_json)
        except Exception as exc:  # demo UI: show any failure instead of crashing
            st.error(f"Request failed: {exc}")
        else:
            st.success("Bundle accepted.")
            st.json(response)
