#!/usr/bin/env bash
# Official HL7 validator on every filed bundle. Prints per-file results and the total error count.
# First run downloads validator_cli.jar (needs internet, ~150 MB incl. packages). Owner: MedEng.
set -euo pipefail
cd "$(dirname "$0")/.."
JAR=tools/validator_cli.jar
mkdir -p tools var/validation
if [ ! -f "$JAR" ]; then
  curl -fL -o "$JAR" https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/download/validator_cli.jar
fi
# bundles filed by the app: local runs write var/filed, the docker app writes into its volume
if docker compose ps -q app >/dev/null 2>&1 && [ -n "$(docker compose ps -q app)" ]; then
  docker compose cp app:/data/filed/. var/filed/ 2>/dev/null || true
fi
shopt -s nullglob
files=(var/filed/*.json)
[ ${#files[@]} -gt 0 ] || { echo "no filed bundles in var/filed"; exit 1; }
total=0
for f in "${files[@]}"; do
  out="var/validation/$(basename "$f" .json).txt"
  java -jar "$JAR" "$f" -version 4.0 > "$out" 2>&1 || true
  n=$(grep -Eo '[0-9]+ errors' "$out" | tail -1 | grep -Eo '[0-9]+' || echo "?")
  echo "$f: $n errors"
  [[ "$n" =~ ^[0-9]+$ ]] && total=$((total + n))
done
echo "TOTAL_ERRORS=$total"
